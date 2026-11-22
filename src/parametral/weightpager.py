"""mmap-first weight pager for the 80B / REAP experiments (phase 6.1).

Design notes that matter for the speed budget:

* **Hash once per cold page-in, not per read.** A 48 GB train step would otherwise spend
  24-120 s in SHA-256 before the model sees a byte. The cold hash is stored in
  `HashCache` keyed by `(block_id, shard, size, mtime_ns)`; warm reads reuse it.
  The hash is always taken over the *mmap region* (one disk read), never by reading the
  block a second time with `pread`.
* **Blocks stop at tensor boundaries.** A fixed 256 MB cut can bisect an AWQ tensor
  (packed int32 + scales + zeros) and make dequantisation impossible. The manifest
  builder groups whole tensors up to the target size and lets a single larger tensor
  stand alone.
* `mmap(O_RDONLY)` is the primary path: two processes share the same physical pages.
  O_DIRECT is deliberately not used. `pread` remains a measured fallback.
* Hot/cold is two-tier: active-step blocks are pinned, the rest are LRU. On a model
  larger than RAM this cannot create capacity; measure hit rate and page-in latency.

Audit domain: `parametral-block-v1` (see `blockaudit.py`).
"""
from __future__ import annotations

import hashlib
import json
import mmap
import os
import struct
import threading
import time
from collections import Counter, OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable

from . import util
from .blockaudit import BlockAuditLog, BlockAuditError

ALIGN = mmap.ALLOCATIONGRANULARITY
DEFAULT_BLOCK_SIZE = 256 * 1024 * 1024
HASH_ALGOS = ("sha256", "blake3")


class WeightPagerError(RuntimeError):
    def __init__(self, code: str, message: str, detail=None):
        super().__init__(message)
        self.code = code
        self.detail = detail


def _hash_bytes(data: bytes, algo: str = "sha256") -> str:
    if algo == "sha256":
        return "sha256:" + hashlib.sha256(data).hexdigest()
    if algo == "blake3":
        try:
            from blake3 import blake3  # optional dependency
        except ImportError as exc:
            raise WeightPagerError(
                "HASH_UNAVAILABLE",
                "blake3 requested but the blake3 module is not installed") from exc
        return "blake3:" + blake3(data).hexdigest()
    raise WeightPagerError("HASH_UNSUPPORTED", f"unknown hash algorithm {algo!r}")


def _sha_bytes(data: bytes) -> str:
    return _hash_bytes(data, "sha256")


def _valid_tag(tag: str) -> bool:
    if not isinstance(tag, str) or ":" not in tag:
        return False
    algo, raw = tag.split(":", 1)
    return algo in HASH_ALGOS and len(raw) == 64 and all(
        char in "0123456789abcdef" for char in raw)


@dataclass(frozen=True)
class Block:
    block_id: str
    shard: str
    offset: int
    length: int
    sha256: str
    layer: str = ""
    tensor: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        try:
            block = cls(
                block_id=str(data["block_id"]),
                shard=str(data["shard"]),
                offset=int(data["offset"]),
                length=int(data["length"]),
                sha256=str(data["sha256"]),
                layer=str(data.get("layer", "")),
                tensor=str(data.get("tensor", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WeightPagerError("INVALID_MANIFEST", f"bad block entry: {exc}") from exc
        if block.offset % ALIGN:
            raise WeightPagerError(
                "INVALID_MANIFEST",
                f"{block.block_id}: offset {block.offset} is not {ALIGN}-aligned")
        if block.length <= 0:
            raise WeightPagerError("INVALID_MANIFEST", f"{block.block_id}: empty block")
        if not _valid_tag(block.sha256):
            raise WeightPagerError("INVALID_MANIFEST",
                                   f"{block.block_id}: hash must be <algo>:<64 hex>")
        return block


class HashCache:
    """Persistent cold-hash cache.

    Shards are immutable, so `(block_id, shard, size, mtime_ns)` is enough to reuse a
    verified hash. A changed shard or a different block size misses the cache and is
    hashed again. The cache is deliberately separate from the audit chain: it is a
    performance memo, not evidence.
    """

    def __init__(self, path: str | None = None):
        self.path = os.path.abspath(path) if path else None
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path, "rb") as handle:
                    raw = json.load(handle)
                if isinstance(raw, dict):
                    self._data = raw
            except (OSError, json.JSONDecodeError):
                self._data = {}

    @staticmethod
    def _key(block: Block) -> str:
        return f"{block.block_id}\0{block.shard}"

    def get(self, block: Block, *, size: int, mtime_ns: int) -> str | None:
        key = self._key(block)
        with self._lock:
            entry = self._data.get(key)
        if not entry:
            return None
        if (entry.get("shard") == block.shard and entry.get("size") == size
                and entry.get("mtime_ns") == mtime_ns and entry.get("offset") == block.offset
                and entry.get("length") == block.length):
            return str(entry.get("hash"))
        return None

    def put(self, block: Block, *, size: int, mtime_ns: int, digest: str) -> None:
        with self._lock:
            self._data[self._key(block)] = {
                "block_id": block.block_id, "shard": block.shard,
                "offset": block.offset, "length": block.length,
                "size": size, "mtime_ns": mtime_ns, "hash": digest,
            }
            if self.path:
                util.write_json(self.path, self._data, mode=0o600)


class WeightManifest:
    def __init__(self, data: dict, base_dir: str = "."):
        if not isinstance(data, dict):
            raise WeightPagerError("INVALID_MANIFEST", "manifest must be an object")
        self.base_dir = os.path.abspath(base_dir)
        self.version = int(data.get("version", 1))
        self.model = str(data.get("model", "unknown"))
        self.block_size = int(data.get("block_size", DEFAULT_BLOCK_SIZE))
        self.hash_algo = str(data.get("hash_algo", "sha256"))
        if self.hash_algo not in HASH_ALGOS:
            raise WeightPagerError("INVALID_MANIFEST",
                                   f"unsupported hash_algo {self.hash_algo!r}")
        shards = data.get("shards", {})
        if isinstance(shards, list):
            shards = {str(item["name"]): item for item in shards}
        if not isinstance(shards, dict) or not shards:
            raise WeightPagerError("INVALID_MANIFEST", "shards must be a non-empty map/list")
        self.shards: dict[str, dict] = {}
        for name, spec in shards.items():
            if isinstance(spec, str):
                spec = {"path": spec}
            path = spec.get("path", name)
            self.shards[str(name)] = {
                "path": os.path.abspath(os.path.join(self.base_dir, path)),
                "sha256": spec.get("sha256"),
            }
        self.blocks: dict[str, Block] = {}
        for entry in data.get("blocks", []):
            block = Block.from_dict(entry)
            if block.block_id in self.blocks:
                raise WeightPagerError("INVALID_MANIFEST",
                                       f"duplicate block {block.block_id}")
            if block.shard not in self.shards:
                raise WeightPagerError("INVALID_MANIFEST",
                                       f"{block.block_id}: unknown shard {block.shard}")
            if not block.sha256.startswith(self.hash_algo + ":"):
                raise WeightPagerError(
                    "INVALID_MANIFEST",
                    f"{block.block_id}: hash {block.sha256.split(':', 1)[0]} "
                    f"does not match manifest hash_algo {self.hash_algo}")
            self.blocks[block.block_id] = block
        self.tensors: dict[str, list[str]] = {
            str(name): [str(block) for block in blocks]
            for name, blocks in (data.get("tensors") or {}).items()
        }
        for tensor, ids in self.tensors.items():
            missing = [block for block in ids if block not in self.blocks]
            if missing:
                raise WeightPagerError("INVALID_MANIFEST",
                                       f"tensor {tensor}: unknown blocks {missing[:3]}")
        self.tensor_ranges: dict[str, list[dict]] = {}
        for tensor, ranges in (data.get("tensor_ranges") or {}).items():
            clean = []
            for item in ranges:
                try:
                    block_id = str(item["block_id"])
                    offset = int(item["offset"])
                    length = int(item["length"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise WeightPagerError("INVALID_MANIFEST",
                                           f"tensor {tensor}: bad range: {exc}") from exc
                block = self.blocks.get(block_id)
                if block is None:
                    raise WeightPagerError("INVALID_MANIFEST",
                                           f"tensor {tensor}: unknown block {block_id}")
                if offset < 0 or length <= 0 or offset + length > block.length:
                    raise WeightPagerError(
                        "INVALID_MANIFEST",
                        f"tensor {tensor}: range {offset}+{length} outside {block_id}")
                clean.append({"block_id": block_id, "offset": offset, "length": length})
            self.tensor_ranges[str(tensor)] = clean

    @classmethod
    def load(cls, path: str) -> "WeightManifest":
        try:
            with open(path, "rb") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise WeightPagerError("INVALID_MANIFEST", str(exc)) from exc
        return cls(data, os.path.dirname(os.path.abspath(path)))

    def shard_path(self, name: str) -> str:
        try:
            return self.shards[name]["path"]
        except KeyError as exc:
            raise WeightPagerError("INVALID_MANIFEST", f"unknown shard {name}") from exc


@dataclass
class Stats:
    hits: int = 0
    misses: int = 0
    bytes_read: int = 0
    evictions: int = 0
    pageins: int = 0
    pagein_bytes: int = 0
    hash_computed: int = 0
    hash_skipped: int = 0
    hash_ms: float = 0.0
    audit_errors: int = 0
    read_ms_total: float = 0.0

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "bytes_read": self.bytes_read,
            "evictions": self.evictions,
            "pageins": self.pageins,
            "pagein_bytes": self.pagein_bytes,
            "hash_computed": self.hash_computed,
            "hash_skipped": self.hash_skipped,
            "hash_ms": round(self.hash_ms, 3),
            "audit_errors": self.audit_errors,
            "read_ms_total": round(self.read_ms_total, 3),
        }


class WeightPager:
    def __init__(self, manifest: WeightManifest, audit: BlockAuditLog | None = None,
                 max_resident_bytes: int | None = None, prefetch_distance: int = 2,
                 node_id: str = "local", hash_cache: HashCache | None = None):
        self.manifest = manifest
        self.audit = audit
        self.node_id = node_id
        self.prefetch_distance = max(0, int(prefetch_distance))
        self.max_resident_bytes = max_resident_bytes
        self.hash_cache = hash_cache if hash_cache is not None else HashCache()
        self._fds: dict[str, int] = {}
        self._maps: "OrderedDict[str, mmap.mmap]" = OrderedDict()
        self._pins: Counter[str] = Counter()
        self._lock = threading.RLock()
        self._closed = False
        self.stats = Stats()

    # ------------------------------------------------------------------ open

    def _fd(self, shard: str) -> int:
        if shard not in self._fds:
            path = self.manifest.shard_path(shard)
            try:
                self._fds[shard] = os.open(path, os.O_RDONLY)
            except OSError as exc:
                raise WeightPagerError("SHARD_UNAVAILABLE",
                                       f"cannot open {path}: {exc}", {"shard": shard}) from exc
        return self._fds[shard]

    def _stat(self, block: Block) -> tuple[int, int]:
        try:
            st = os.stat(self.manifest.shard_path(block.shard))
        except OSError as exc:
            raise WeightPagerError("SHARD_UNAVAILABLE", str(exc)) from exc
        return st.st_size, st.st_mtime_ns

    def _map(self, block: Block) -> mmap.mmap:
        fd = self._fd(block.shard)
        try:
            mapped = mmap.mmap(fd, block.length, offset=block.offset, access=mmap.ACCESS_READ)
        except (OSError, ValueError) as exc:
            raise WeightPagerError("BLOCK_UNAVAILABLE",
                                   f"{block.block_id}: {exc}",
                                   {"block_id": block.block_id}) from exc
        try:
            mapped.madvise(mmap.MADV_SEQUENTIAL)
            mapped.madvise(mmap.MADV_WILLNEED)
        except (AttributeError, OSError):
            pass
        return mapped

    def _audit(self, event: str, **kwargs) -> None:
        if self.audit is None:
            return
        try:
            self.audit.append(event, **kwargs)
        except BlockAuditError:
            self.stats.audit_errors += 1
            raise

    def _prefetch(self, block: Block) -> None:
        try:
            os.posix_fadvise(self._fd(block.shard), block.offset, block.length,
                             os.POSIX_FADV_WILLNEED)
        except (AttributeError, OSError):
            pass

    def _resident_bytes(self) -> int:
        return sum(len(mapped) for mapped in self._maps.values())

    def _evict_one(self, *, req_id: str, keep: str | None = None) -> bool:
        for block_id, mapped in list(self._maps.items()):
            if block_id == keep or self._pins.get(block_id, 0):
                continue
            block = self.manifest.blocks[block_id]
            del self._maps[block_id]
            mapped.close()
            self.stats.evictions += 1
            self._audit("weight.block.evict", req_id=req_id, block_id=block_id,
                        shard=block.shard, offset=block.offset, length=block.length,
                        content_sha256=block.sha256,
                        detail={"reason": "capacity", "resident": False})
            return True
        return False

    def _enforce_capacity(self, req_id: str, keep: str | None = None) -> None:
        if self.max_resident_bytes is None:
            return
        while self._resident_bytes() > self.max_resident_bytes:
            if not self._evict_one(req_id=req_id, keep=keep):
                raise WeightPagerError(
                    "PINNED_LIMIT",
                    "resident bytes exceed the limit but every block is pinned",
                    {"resident_bytes": self._resident_bytes(),
                     "limit": self.max_resident_bytes})

    def _verify_hash(self, block: Block, mapped: mmap.mmap) -> str:
        size, mtime_ns = self._stat(block)
        cached = self.hash_cache.get(block, size=size, mtime_ns=mtime_ns)
        if cached is not None:
            self.stats.hash_skipped += 1
            return cached
        started = time.perf_counter()
        digest = _hash_bytes(mapped, self.manifest.hash_algo)
        self.stats.hash_ms += (time.perf_counter() - started) * 1000
        self.stats.hash_computed += 1
        if digest != block.sha256:
            raise WeightPagerError(
                "BLOCK_HASH_MISMATCH",
                f"{block.block_id}: expected {block.sha256}, got {digest}",
                {"block_id": block.block_id})
        self.hash_cache.put(block, size=size, mtime_ns=mtime_ns, digest=digest)
        return digest

    # --------------------------------------------------------------- public

    def read_block(self, block_id: str, *, req_id: str, pin: bool = False,
                   copy: bool = True) -> bytes | memoryview:
        if self._closed:
            raise WeightPagerError("CLOSED", "pager is closed")
        try:
            block = self.manifest.blocks[block_id]
        except KeyError as exc:
            raise WeightPagerError("UNKNOWN_BLOCK", f"unknown block {block_id}") from exc
        started = time.perf_counter()
        with self._lock:
            mapped = self._maps.get(block_id)
            resident = mapped is not None
            digest = block.sha256
            if mapped is None:
                mapped = self._map(block)
                self._maps[block_id] = mapped
                self.stats.misses += 1
                try:
                    digest = self._verify_hash(block, mapped)
                except BaseException:
                    self._maps.pop(block_id, None)
                    mapped.close()
                    raise
                if self.prefetch_distance:
                    siblings = [item for item in self.manifest.blocks.values()
                                if item.layer == block.layer]
                    try:
                        index = siblings.index(block)
                        after = siblings[index + 1:index + 1 + self.prefetch_distance]
                    except ValueError:
                        after = []
                    for next_block in after:
                        if next_block.block_id not in self._maps:
                            self._prefetch(next_block)
            else:
                self.stats.hits += 1
                self._maps.move_to_end(block_id)
            if pin:
                self._pins[block_id] += 1
            data = bytes(mapped) if copy else memoryview(mapped)
            elapsed_ms = (time.perf_counter() - started) * 1000
            self.stats.bytes_read += len(data)
            self.stats.read_ms_total += elapsed_ms
            try:
                self._enforce_capacity(req_id, keep=block_id)
            except BaseException:
                if pin:
                    self._pins[block_id] -= 1
                raise
            self._audit("weight.block.read", req_id=req_id, block_id=block_id,
                        shard=block.shard, offset=block.offset, length=block.length,
                        resident=resident, latency_ms=elapsed_ms,
                        content_sha256=digest,
                        detail={"layer": block.layer, "tensor": block.tensor,
                                "node_id": self.node_id})
            return data

    def prefetch(self, block_ids: Iterable[str], *, req_id: str) -> dict:
        ids = [block_id for block_id in block_ids if block_id in self.manifest.blocks]
        if not ids:
            raise WeightPagerError("UNKNOWN_BLOCK", "no known blocks in prefetch batch")
        started = time.perf_counter()
        total = 0
        with self._lock:
            for block_id in ids:
                block = self.manifest.blocks[block_id]
                total += block.length
                if block_id not in self._maps:
                    self._prefetch(block)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.stats.pageins += len(ids)
        self.stats.pagein_bytes += total
        self._audit("weight.pagein.batch", req_id=req_id, block_ids=ids,
                    bytes_read=total, latency_ms=elapsed_ms,
                    detail={"node_id": self.node_id, "count": len(ids)})
        return {"block_ids": ids, "bytes": total, "latency_ms": round(elapsed_ms, 3)}

    @contextmanager
    def pinned(self, block_ids: Iterable[str]):
        ids = list(block_ids)
        with self._lock:
            for block_id in ids:
                self._pins[block_id] += 1
        try:
            yield
        finally:
            with self._lock:
                for block_id in ids:
                    self._pins[block_id] -= 1
                    if self._pins[block_id] <= 0:
                        self._pins.pop(block_id, None)

    def evict(self, block_id: str, *, req_id: str) -> bool:
        with self._lock:
            if block_id not in self._maps:
                return False
            if self._pins.get(block_id, 0):
                raise WeightPagerError("PINNED", f"{block_id} is pinned",
                                       {"block_id": block_id})
            mapped = self._maps.pop(block_id)
            mapped.close()
            self.stats.evictions += 1
            block = self.manifest.blocks[block_id]
            self._audit("weight.block.evict", req_id=req_id, block_id=block_id,
                        shard=block.shard, offset=block.offset, length=block.length,
                        content_sha256=block.sha256,
                        detail={"reason": "explicit", "resident": False})
            return True

    def read_tensor(self, tensor: str, *, req_id: str) -> bytes:
        try:
            ids = self.manifest.tensors[tensor]
        except KeyError as exc:
            raise WeightPagerError("UNKNOWN_TENSOR", f"unknown tensor {tensor}") from exc
        ranges = self.manifest.tensor_ranges.get(tensor)
        if not ranges:
            return b"".join(self.read_block(block_id, req_id=req_id) for block_id in ids)
        out = bytearray()
        for item in ranges:
            data = self.read_block(item["block_id"], req_id=req_id)
            start = item["offset"]
            out += data[start:start + item["length"]]
        return bytes(out)

    def snapshot_stats(self) -> dict:
        with self._lock:
            data = self.stats.to_dict()
            data["resident_blocks"] = len(self._maps)
            data["resident_bytes"] = self._resident_bytes()
            data["pinned_blocks"] = len(self._pins)
            data["hash_algo"] = self.manifest.hash_algo
            return data

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for mapped in self._maps.values():
                try:
                    mapped.close()
                except BufferError:
                    pass
            self._maps.clear()
            for fd in self._fds.values():
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._fds.clear()


def _safetensors_header(path: str) -> tuple[dict, int]:
    with open(path, "rb") as handle:
        raw = handle.read(8)
        if len(raw) != 8:
            raise WeightPagerError("INVALID_MANIFEST", f"{path}: short safetensors header")
        length = struct.unpack("<Q", raw)[0]
        if length <= 0 or length > 256 * 1024 * 1024:
            raise WeightPagerError("INVALID_MANIFEST", f"{path}: bad header length")
        header = handle.read(length)
    try:
        return json.loads(header), 8 + length
    except json.JSONDecodeError as exc:
        raise WeightPagerError("INVALID_MANIFEST", f"{path}: {exc}") from exc


def build_manifest_from_safetensors(shard_path: str, *, max_block_size: int = DEFAULT_BLOCK_SIZE,
                                   model: str = "unknown",
                                   hash_algo: str = "sha256") -> dict:
    """Build a manifest whose blocks never cut a tensor.

    A block is a group of consecutive tensors in file order, up to `max_block_size`.
    A single tensor larger than the target becomes its own block. The shard header is
    parsed with the safetensors layout (8-byte length + JSON), so the result works on a
    real AWQ checkpoint rather than only on a synthetic file.
    """
    if hash_algo not in HASH_ALGOS:
        raise WeightPagerError("INVALID_MANIFEST", f"unsupported hash_algo {hash_algo!r}")
    path = os.path.abspath(shard_path)
    file_size = os.path.getsize(path)
    header, data_start = _safetensors_header(path)
    tensors = []
    for name, spec in header.items():
        if name == "__metadata__" or not isinstance(spec, dict):
            continue
        offsets = spec.get("data_offsets")
        if not isinstance(offsets, list) or len(offsets) != 2:
            continue
        begin, end = int(offsets[0]), int(offsets[1])
        if end <= begin:
            continue
        tensors.append((data_start + begin, end - begin, name))
    tensors.sort()
    blocks = []
    mapping: dict[str, list[str]] = {}
    ranges: dict[str, list[dict]] = {}
    with open(path, "rb") as handle:
        group: list[tuple[int, int, str]] = []
        group_bytes = 0
        index = 0

        def flush() -> None:
            nonlocal group, group_bytes, index
            if not group:
                return
            block_id = f"layer.block.{index:05d}"
            raw_begin = group[0][0]
            raw_end = group[-1][0] + group[-1][1]
            # The pager maps with 4 KiB alignment, but a safetensors data section is only
            # 8-byte aligned. Round the physical block out; the tensor range stays exact
            # and the model can address it from the shard header.
            begin = raw_begin - (raw_begin % ALIGN)
            end = min(file_size, ((raw_end + ALIGN - 1) // ALIGN) * ALIGN)
            length = end - begin
            handle.seek(begin)
            data = handle.read(length)
            digest = _hash_bytes(data, hash_algo)
            blocks.append({
                "block_id": block_id,
                "shard": os.path.basename(path),
                "offset": begin,
                "length": length,
                "sha256": digest,
                "layer": os.path.dirname(group[0][2]).replace(".", "/") or "root",
                "tensor": group[0][2] if len(group) == 1 else "",
            })
            for tensor_offset, tensor_length, tensor in group:
                mapping.setdefault(tensor, []).append(block_id)
                ranges.setdefault(tensor, []).append({
                    "block_id": block_id,
                    "offset": tensor_offset - begin,
                    "length": tensor_length,
                })
            index += 1
            group = []
            group_bytes = 0

        for offset, length, name in tensors:
            if group and group_bytes + length > max_block_size:
                flush()
            group.append((offset, length, name))
            group_bytes += length
        flush()
    return {
        "version": 1,
        "model": model,
        "block_size": int(max_block_size),
        "hash_algo": hash_algo,
        "shards": {os.path.basename(path): {"path": os.path.basename(path)}},
        "blocks": blocks,
        "tensors": mapping,
        "tensor_ranges": ranges,
    }


def build_manifest_from_index(index_path: str, *,
                              max_block_size: int = DEFAULT_BLOCK_SIZE,
                              model: str | None = None,
                              hash_algo: str = "sha256") -> dict:
    """Build one manifest for every shard named by model.safetensors.index.json.

    The index maps each tensor to a shard; each shard is parsed with its own header and
    blocks are grouped inside that shard. Block ids are renumbered globally so a tensor
    map and the pager can address all shards through one manifest.
    """
    index_path = os.path.abspath(index_path)
    base = os.path.dirname(index_path)
    try:
        with open(index_path, "rb") as handle:
            index = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise WeightPagerError("INVALID_MANIFEST", str(exc)) from exc
    weight_map = index.get("weight_map") if isinstance(index, dict) else None
    if not isinstance(weight_map, dict) or not weight_map:
        raise WeightPagerError("INVALID_MANIFEST",
                               f"{index_path}: no weight_map")
    shard_names = sorted({str(name) for name in weight_map.values()})
    parts = []
    for name in shard_names:
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            raise WeightPagerError("SHARD_MISSING", f"shard not found: {path}")
        parts.append(build_manifest_from_safetensors(
            path, max_block_size=max_block_size,
            model=model or os.path.basename(base), hash_algo=hash_algo))
    blocks: list[dict] = []
    shards: dict[str, dict] = {}
    tensors: dict[str, list[str]] = {}
    ranges: dict[str, list[dict]] = {}
    next_index = 0
    for name, part in zip(shard_names, parts):
        for key, spec in part["shards"].items():
            entry = dict(spec)
            entry["path"] = os.path.abspath(os.path.join(base, name))
            shards[key] = entry
        mapping: dict[str, str] = {}
        for block in part["blocks"]:
            old = block["block_id"]
            new = f"block.{next_index:06d}"
            next_index += 1
            mapping[old] = new
            block = dict(block)
            block["block_id"] = new
            blocks.append(block)
        for tensor, ids in part.get("tensors", {}).items():
            tensors.setdefault(tensor, []).extend(mapping.get(item, item) for item in ids)
        for tensor, items in part.get("tensor_ranges", {}).items():
            for item in items:
                ranges.setdefault(tensor, []).append({
                    "block_id": mapping.get(item["block_id"], item["block_id"]),
                    "offset": item["offset"],
                    "length": item["length"],
                })
    return {
        "version": 1,
        "model": model or os.path.basename(base),
        "block_size": int(max_block_size),
        "hash_algo": hash_algo,
        "shards": shards,
        "blocks": blocks,
        "tensors": tensors,
        "tensor_ranges": ranges,
    }


def build_manifest(shard_path: str, *, block_size: int = DEFAULT_BLOCK_SIZE,
                   model: str = "synthetic", hash_algo: str = "sha256") -> dict:
    """Create a manifest for a raw shard file (development/benchmark helper).

    This is intentionally not a safetensors parser; use
    `build_manifest_from_safetensors` for a real checkpoint.
    """
    if hash_algo not in HASH_ALGOS:
        raise WeightPagerError("INVALID_MANIFEST", f"unsupported hash_algo {hash_algo!r}")
    path = os.path.abspath(shard_path)
    size = os.path.getsize(path)
    blocks = []
    with open(path, "rb") as handle:
        offset = 0
        index = 0
        while offset < size:
            length = min(block_size, size - offset)
            if offset % ALIGN:
                raise WeightPagerError("INVALID_MANIFEST", "shard offset is not aligned")
            handle.seek(offset)
            data = handle.read(length)
            blocks.append({
                "block_id": f"block.{index:05d}",
                "shard": os.path.basename(path),
                "offset": offset,
                "length": len(data),
                "sha256": _hash_bytes(data, hash_algo),
                "layer": "layer.0",
                "tensor": f"synthetic.{index:05d}",
            })
            offset += length
            index += 1
    return {
        "version": 1,
        "model": model,
        "block_size": block_size,
        "hash_algo": hash_algo,
        "shards": {os.path.basename(path): {"path": os.path.basename(path)}},
        "blocks": blocks,
        "tensors": {"synthetic.weight": [block["block_id"] for block in blocks]},
        "tensor_ranges": {
            "synthetic.weight": [
                {"block_id": block["block_id"], "offset": 0, "length": block["length"]}
                for block in blocks
            ]
        },
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="parametral-weight",
                                     description="mmap weight pager (phase 6.1)")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--audit", default=None,
                        help="block audit JSONL (default: state/blockaudit.jsonl)")
    parser.add_argument("--hash-cache", default=None,
                        help="cold-hash cache JSON (default: in-memory)")
    parser.add_argument("--max-resident-mb", type=int, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("stats").set_defaults(command="stats")
    read = sub.add_parser("read")
    read.add_argument("block_id")
    read.add_argument("--req-id", default="cli")
    read.set_defaults(command="read")
    pre = sub.add_parser("prefetch")
    pre.add_argument("block_ids", nargs="+")
    pre.add_argument("--req-id", default="cli")
    pre.set_defaults(command="prefetch")
    sub.add_parser("audit-verify").set_defaults(command="audit-verify")
    build = sub.add_parser("build-manifest")
    build.add_argument("--index", required=True,
                       help="model.safetensors.index.json")
    build.add_argument("--out", required=True)
    build.add_argument("--max-block-mb", type=int, default=256)
    build.add_argument("--model", default=None)
    build.add_argument("--hash-algo", choices=HASH_ALGOS, default="sha256")
    build.set_defaults(command="build-manifest")
    args = parser.parse_args(argv)

    if args.command == "build-manifest":
        data = build_manifest_from_index(
            args.index, max_block_size=args.max_block_mb * 1024 * 1024,
            model=args.model, hash_algo=args.hash_algo)
        util.write_json(args.out, data, mode=0o644)
        sizes = [block["length"] for block in data["blocks"]]
        print(json.dumps({
            "manifest": os.path.abspath(args.out),
            "model": data["model"],
            "blocks": len(sizes),
            "total_gb": round(sum(sizes) / 1024 ** 3, 3),
            "average_block_mb": round(sum(sizes) / len(sizes) / 1024 ** 2, 3) if sizes else 0,
            "largest_block_mb": round(max(sizes) / 1024 ** 2, 3) if sizes else 0,
            "tensors": len(data["tensors"]),
        }, indent=2, sort_keys=True))
        return 0
    if not args.manifest:
        parser.error("--manifest is required for pager commands")
    manifest = WeightManifest.load(args.manifest)
    audit_path = args.audit or os.path.join(util.state_dir(), "blockaudit.jsonl")
    audit = BlockAuditLog(audit_path)
    if args.command == "audit-verify":
        print(json.dumps(audit.verify(), indent=2, sort_keys=True))
        return 0 if audit.verify()["verified"] else 1
    pager = WeightPager(manifest, audit=audit,
                        hash_cache=HashCache(args.hash_cache),
                        max_resident_bytes=(args.max_resident_mb * 1024 * 1024
                                            if args.max_resident_mb else None))
    try:
        if args.command == "stats":
            print(json.dumps(pager.snapshot_stats(), indent=2, sort_keys=True))
        elif args.command == "read":
            data = pager.read_block(args.block_id, req_id=args.req_id)
            print(json.dumps({"block_id": args.block_id, "bytes": len(data),
                              "sha256": _sha_bytes(data)}, indent=2, sort_keys=True))
        elif args.command == "prefetch":
            print(json.dumps(pager.prefetch(args.block_ids, req_id=args.req_id),
                             indent=2, sort_keys=True))
    finally:
        pager.close()
    return 0

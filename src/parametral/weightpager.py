"""mmap-first weight pager for the 80B / REAP experiments (phase 6.1).

The unit is one *block*: 256 MB by default, 4 KiB aligned, identified by
`(layer, part)` and stored in a model shard. The pager does not know how to
dequantise or run a model; it knows which bytes are hot, maps the cold ones with
`mmap(O_RDONLY)` so two processes share the same physical pages, verifies the
manifest hash before serving a block, and writes one hash-chained audit record.

Why mmap and not O_DIRECT: O_DIRECT throws away the page cache, which is exactly
the cache that makes a second client nearly free. `pread` remains available as a
measured fallback when a mmap fault storm is worse than a copy.

The hot/cold policy is deliberately two-tier:
  1. blocks touched by the active step are pinned (never evicted),
  2. the rest are plain LRU.
On a model larger than RAM this cannot invent capacity; the measured numbers are
hit rate, page-in latency and the shared-page RSS result, not a promise.
"""
from __future__ import annotations

import hashlib
import json
import mmap
import os
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Iterable

from . import util
from .blockaudit import BlockAuditLog, BlockAuditError

ALIGN = mmap.ALLOCATIONGRANULARITY
DEFAULT_BLOCK_SIZE = 256 * 1024 * 1024


class WeightPagerError(RuntimeError):
    def __init__(self, code: str, message: str, detail=None):
        super().__init__(message)
        self.code = code
        self.detail = detail


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Block:
    block_id: str
    shard: str
    offset: int
    length: int
    sha256: str
    layer: str = ""

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
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WeightPagerError("INVALID_MANIFEST", f"bad block entry: {exc}") from exc
        if block.offset % ALIGN:
            raise WeightPagerError(
                "INVALID_MANIFEST",
                f"{block.block_id}: offset {block.offset} is not {ALIGN}-aligned")
        if block.length <= 0:
            raise WeightPagerError("INVALID_MANIFEST", f"{block.block_id}: empty block")
        if not block.sha256.startswith("sha256:") or len(block.sha256) != 71:
            raise WeightPagerError("INVALID_MANIFEST",
                                   f"{block.block_id}: sha256 must be sha256:<64 hex>")
        return block


class WeightManifest:
    def __init__(self, data: dict, base_dir: str = "."):
        if not isinstance(data, dict):
            raise WeightPagerError("INVALID_MANIFEST", "manifest must be an object")
        self.base_dir = os.path.abspath(base_dir)
        self.version = int(data.get("version", 1))
        self.model = str(data.get("model", "unknown"))
        self.block_size = int(data.get("block_size", DEFAULT_BLOCK_SIZE))
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
        blocks = data.get("blocks", [])
        self.blocks: dict[str, Block] = {}
        for entry in blocks:
            block = Block.from_dict(entry)
            if block.block_id in self.blocks:
                raise WeightPagerError("INVALID_MANIFEST",
                                       f"duplicate block {block.block_id}")
            if block.shard not in self.shards:
                raise WeightPagerError("INVALID_MANIFEST",
                                       f"{block.block_id}: unknown shard {block.shard}")
            self.blocks[block.block_id] = block
        self.tensors: dict[str, list[str]] = {
            str(name): [str(block) for block in ids]
            for name, ids in (data.get("tensors") or {}).items()
        }
        for tensor, ids in self.tensors.items():
            missing = [block for block in ids if block not in self.blocks]
            if missing:
                raise WeightPagerError("INVALID_MANIFEST",
                                       f"tensor {tensor}: unknown blocks {missing[:3]}")

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
            "audit_errors": self.audit_errors,
            "read_ms_total": round(self.read_ms_total, 3),
            "resident_blocks": None,
            "resident_bytes": None,
        }


class WeightPager:
    def __init__(self, manifest: WeightManifest, audit: BlockAuditLog | None = None,
                 max_resident_bytes: int | None = None, prefetch_distance: int = 2,
                 node_id: str = "local"):
        self.manifest = manifest
        self.audit = audit
        self.node_id = node_id
        self.prefetch_distance = max(0, int(prefetch_distance))
        self.max_resident_bytes = max_resident_bytes
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

    def _map(self, block: Block) -> mmap.mmap:
        fd = self._fd(block.shard)
        try:
            mapped = mmap.mmap(fd, block.length, offset=block.offset, access=mmap.ACCESS_READ)
        except (OSError, ValueError) as exc:
            raise WeightPagerError("BLOCK_UNAVAILABLE",
                                   f"{block.block_id}: {exc}", {"block_id": block.block_id}) from exc
        try:
            mapped.madvise(mmap.MADV_SEQUENTIAL)
            mapped.madvise(mmap.MADV_WILLNEED)
        except (AttributeError, OSError):
            pass  # old kernel/libc: correctness does not depend on the hint
        digest = _sha(mapped)
        if digest != block.sha256:
            mapped.close()
            raise WeightPagerError(
                "BLOCK_HASH_MISMATCH",
                f"{block.block_id}: expected {block.sha256}, got {digest}",
                {"block_id": block.block_id})
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

    # --------------------------------------------------------------- public

    def read_block(self, block_id: str, *, req_id: str, pin: bool = False) -> bytes:
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
            if mapped is None:
                mapped = self._map(block)
                self._maps[block_id] = mapped
                self.stats.misses += 1
                if self.prefetch_distance:
                    # Warm the two following parts in the same layer, not a random block.
                    siblings = [item for item in self.manifest.blocks.values()
                                if item.layer == block.layer]
                    try:
                        after = siblings[siblings.index(block) + 1:
                                         siblings.index(block) + 1 + self.prefetch_distance]
                    except (ValueError, AttributeError):
                        after = []
                    for next_block in after:
                        if next_block.block_id not in self._maps:
                            self._prefetch(next_block)
            else:
                self.stats.hits += 1
                self._maps.move_to_end(block_id)
            if pin:
                self._pins[block_id] += 1
            data = bytes(mapped)
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
                        content_sha256=block.sha256,
                        detail={"layer": block.layer, "node_id": self.node_id})
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
        return b"".join(self.read_block(block_id, req_id=req_id) for block_id in ids)

    def snapshot_stats(self) -> dict:
        with self._lock:
            data = self.stats.to_dict()
            data["resident_blocks"] = len(self._maps)
            data["resident_bytes"] = self._resident_bytes()
            data["pinned_blocks"] = len(self._pins)
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


def build_manifest(shard_path: str, *, block_size: int = DEFAULT_BLOCK_SIZE,
                   model: str = "synthetic") -> dict:
    """Create a manifest for a raw shard file (development/benchmark helper).

    Each block is aligned to 4 KiB and hashed from the file. This is not a
    safetensors parser; the real 80B manifest is produced by the model loader.
    """
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
                "sha256": _sha(data),
                "layer": "layer.0",
            })
            offset += length
            index += 1
    return {
        "version": 1,
        "model": model,
        "block_size": block_size,
        "shards": {os.path.basename(path): {"path": os.path.basename(path)}},
        "blocks": blocks,
        "tensors": {"synthetic.weight": [block["block_id"] for block in blocks]},
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="parametral-weight",
                                     description="mmap weight pager (phase 6.1)")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--audit", default=None,
                        help="block audit JSONL (default: state/blockaudit.jsonl)")
    parser.add_argument("--max-resident-mb", type=int, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    stats = sub.add_parser("stats")
    stats.set_defaults(command="stats")
    read = sub.add_parser("read")
    read.add_argument("block_id")
    read.add_argument("--req-id", default="cli")
    read.set_defaults(command="read")
    pre = sub.add_parser("prefetch")
    pre.add_argument("block_ids", nargs="+")
    pre.add_argument("--req-id", default="cli")
    pre.set_defaults(command="prefetch")
    verify = sub.add_parser("audit-verify")
    verify.set_defaults(command="audit-verify")
    args = parser.parse_args(argv)

    manifest = WeightManifest.load(args.manifest)
    audit_path = args.audit or os.path.join(util.state_dir(), "blockaudit.jsonl")
    audit = BlockAuditLog(audit_path)
    if args.command == "audit-verify":
        print(json.dumps(audit.verify(), indent=2, sort_keys=True))
        return 0 if audit.verify()["verified"] else 1
    pager = WeightPager(manifest, audit=audit,
                        max_resident_bytes=(args.max_resident_mb * 1024 * 1024
                                            if args.max_resident_mb else None))
    try:
        if args.command == "stats":
            print(json.dumps(pager.snapshot_stats(), indent=2, sort_keys=True))
        elif args.command == "read":
            data = pager.read_block(args.block_id, req_id=args.req_id)
            print(json.dumps({"block_id": args.block_id, "bytes": len(data),
                              "sha256": _sha(data)}, indent=2, sort_keys=True))
        elif args.command == "prefetch":
            print(json.dumps(pager.prefetch(args.block_ids, req_id=args.req_id),
                             indent=2, sort_keys=True))
    finally:
        pager.close()
    return 0

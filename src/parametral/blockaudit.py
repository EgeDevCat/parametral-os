"""Hash-chained audit for weight-block I/O (domain `parametral-block-v1`).

The operating-system half of the weight pager is only useful if a replay can prove
which bytes were served. Every `weight.block.read` record therefore carries the
SHA-256 of the block content, and the record itself is linked to the previous one.
A missing content hash is not a warning: it is a refused append.

Records are deliberately independent of the JSON-RPC audit (`audit.jsonl`); the
daemon forwards these events into the main chain, while a standalone pager (tiny
model, CI, a VM experiment) remains auditable without a daemon.
"""
from __future__ import annotations

import json
import os
import threading

from . import util

DOMAIN = "parametral-block-v1"
GENESIS = "sha256:" + "0" * 64

READ = "weight.block.read"
EVICT = "weight.block.evict"
PAGEIN = "weight.pagein.batch"
EVENTS = (READ, EVICT, PAGEIN)


class BlockAuditError(RuntimeError):
    pass


def _content_tag(value: str | None) -> str:
    if not isinstance(value, str):
        raise BlockAuditError("content_sha256 is required")
    raw = value[7:] if value.startswith("sha256:") else value
    if len(raw) != 64 or any(char not in "0123456789abcdef" for char in raw):
        raise BlockAuditError(f"bad content_sha256 {value!r}")
    return "sha256:" + raw


class BlockAuditLog:
    def __init__(self, path: str, node_id: str = "local"):
        self.path = os.path.abspath(path)
        util.ensure_dir(os.path.dirname(self.path) or ".", 0o700)
        self.node_id = node_id
        self._lock = threading.Lock()
        self._seq, self._head = self._load()

    def _load(self) -> tuple[int, str]:
        if not os.path.exists(self.path):
            return 0, GENESIS
        seq, head = 0, GENESIS
        with open(self.path, "rb") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise BlockAuditError(f"record {number} is not JSON: {exc}") from exc
                if record.get("domain") != DOMAIN:
                    raise BlockAuditError(f"record {number} has wrong domain")
                seq, head = int(record["seq"]), str(record["hash"])
        return seq, head

    def append(self, event: str, *, req_id: str, block_id: str | None = None,
               shard: str | None = None, offset: int | None = None,
               length: int | None = None, resident: bool | None = None,
               latency_ms: float | None = None, content_sha256: str | None = None,
               block_ids: list[str] | None = None, bytes_read: int | None = None,
               detail: dict | None = None) -> dict:
        if event not in EVENTS:
            raise BlockAuditError(f"unknown block audit event {event!r}")
        if not isinstance(req_id, str) or not req_id:
            raise BlockAuditError("req_id is required")
        if event == READ:
            if not block_id or not shard or offset is None or length is None:
                raise BlockAuditError("weight.block.read needs block_id, shard, offset, length")
            content = _content_tag(content_sha256)
        elif event == PAGEIN:
            if not block_ids:
                raise BlockAuditError("weight.pagein.batch needs block_ids")
            content = _content_tag(content_sha256) if content_sha256 else None
        else:
            if not block_id:
                raise BlockAuditError("weight.block.evict needs block_id")
            content = _content_tag(content_sha256) if content_sha256 else None

        record: dict = {
            "domain": DOMAIN,
            "node_id": self.node_id,
            "event": event,
            "req_id": req_id,
            "block_id": block_id,
            "shard": shard,
            "offset": offset,
            "len": length,
            "resident": resident,
            "latency_ms": round(float(latency_ms), 3) if latency_ms is not None else None,
            "content_sha256": content,
            "block_ids": block_ids,
            "bytes": bytes_read,
            "detail": detail or {},
        }
        # Drop nulls to keep the line small, but never drop the content hash of a read.
        record = {key: value for key, value in record.items() if value is not None}
        with self._lock:
            record["seq"] = self._seq + 1
            record["ts"] = util.iso()
            record["prev_hash"] = self._head
            digest = util.sha256_tag(util.canonical_json(record))
            record["hash"] = digest
            line = json.dumps(record, ensure_ascii=False, sort_keys=True).encode() + b"\n"
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
            try:
                os.write(fd, line)
                os.fsync(fd)
            finally:
                os.close(fd)
            self._seq, self._head = record["seq"], digest
            return record

    def verify(self) -> dict:
        try:
            with open(self.path, "rb") as handle:
                records = [json.loads(line) for line in handle if line.strip()]
        except (OSError, json.JSONDecodeError) as exc:
            return {"verified": False, "records": 0, "reason": str(exc)}
        prev = GENESIS
        for index, record in enumerate(records, start=1):
            if record.get("seq") != index:
                return {"verified": False, "records": len(records),
                        "first_broken_seq": index, "reason": "sequence gap"}
            if record.get("prev_hash") != prev:
                return {"verified": False, "records": len(records),
                        "first_broken_seq": index, "reason": "prev_hash mismatch"}
            claimed = record.get("hash")
            body = {key: value for key, value in record.items() if key != "hash"}
            if util.sha256_tag(util.canonical_json(body)) != claimed:
                return {"verified": False, "records": len(records),
                        "first_broken_seq": index, "reason": "record hash mismatch"}
            prev = claimed
        return {"verified": True, "records": len(records), "head": self._head,
                "first_broken_seq": None, "reason": None}

    def query(self, limit: int = 50) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, "rb") as handle:
            for line in handle:
                if line.strip():
                    out.append(json.loads(line))
        return out[-max(1, min(int(limit), 500)):]


class MainAuditSink:
    """Adapter from the block chain to the daemon's global `audit.jsonl`.

    The daemon's AuditLog has a different contract (method/actor/params). Passing this
    object to WeightPager(audit=...) gives phase 6.3 the same event stream in the main
    hash chain without coupling the pager to the daemon.
    """

    def __init__(self, audit, actor: str = "weightpager"):
        self.audit = audit
        self.actor = actor

    def append(self, event: str, **kwargs) -> dict:
        detail = {"domain": DOMAIN, **kwargs}
        return self.audit.append(method=event, actor=self.actor,
                                 params={key: value for key, value in kwargs.items()
                                         if key != "content_sha256"},
                                 detail=detail)

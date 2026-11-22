#!/usr/bin/env python3
"""Tiny synthetic benchmark for the phase 6.1 weight pager.

Answers the three numbers the plan asks for before a 9B run:
  * cold page-in ms per block,
  * hot read ms per block and sequential MB/s,
  * RSS growth when a second pager maps the same shard (shared pages).

It is deliberately synthetic: the real acceptance number comes from the 9B AWQ
shard. Run it on this machine with `python3 scripts/bench_weightpager.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from parametral.blockaudit import BlockAuditLog
from parametral.util import ensure_dir
from parametral.weightpager import (HashCache, WeightManifest, WeightPager,
                                    build_manifest)


def rss_kb() -> int:
    with open("/proc/self/status", "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0


def timed_read(pager: WeightPager, block_id: str, req_id: str) -> float:
    started = time.perf_counter()
    view = pager.read_block(block_id, req_id=req_id, copy=False)
    view.release()
    return (time.perf_counter() - started) * 1000


def drop_cache(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        finally:
            os.close(fd)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mb", type=int, default=128)
    parser.add_argument("--block-mb", type=int, default=16)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="parametral-bench-") as tmp:
        root = Path(tmp)
        shard = root / "synthetic.safetensors"
        block_bytes = args.block_mb * 1024 * 1024
        size = args.size_mb * 1024 * 1024
        shard.write_bytes((bytes(range(256)) * ((size // 256) + 1))[:size])
        drop_cache(str(shard))
        manifest_data = build_manifest(str(shard), block_size=block_bytes,
                                       model="synthetic-bench")
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))
        manifest = WeightManifest.load(str(manifest_path))
        ids = list(manifest.blocks)
        audit = BlockAuditLog(str(root / "blockaudit.jsonl"))
        cache = HashCache(str(root / "hashcache.json"))

        pager = WeightPager(manifest, audit=audit, hash_cache=cache)
        cold = []
        for block_id in ids:
            cold.append(timed_read(pager, block_id, "cold"))
        hot = []
        for block_id in ids:
            hot.append(timed_read(pager, block_id, "hot"))
        rss_one = rss_kb()

        second = WeightPager(manifest, audit=audit, hash_cache=cache)
        for block_id in ids:
            view = second.read_block(block_id, req_id="second", copy=False)
            view.release()
        rss_two = rss_kb()

        total_bytes = sum(block.length for block in manifest.blocks.values())
        result = {
            "model": "synthetic",
            "shard_mb": round(size / 1024 / 1024, 3),
            "block_mb": args.block_mb,
            "blocks": len(ids),
            "cold_ms_per_block": {
                "mean": round(statistics.mean(cold), 3),
                "median": round(statistics.median(cold), 3),
                "max": round(max(cold), 3),
            },
            "hot_ms_per_block": {
                "mean": round(statistics.mean(hot), 3),
                "median": round(statistics.median(hot), 3),
                "max": round(max(hot), 3),
            },
            "cold_sequential_mb_s": round(total_bytes / (sum(cold) / 1000) / 1024 / 1024, 3),
            "hot_sequential_mb_s": round(total_bytes / (sum(hot) / 1000) / 1024 / 1024, 3),
            "rss_kb_one_pager": rss_one,
            "rss_kb_two_pagers": rss_two,
            "rss_delta_kb_second_pager": rss_two - rss_one,
            "hash": pager.snapshot_stats(),
            "audit": audit.verify(),
        }
        second.close()
        pager.close()
        text = json.dumps(result, indent=2, sort_keys=True)
        print(text)
        if args.out:
            ensure_dir(os.path.dirname(os.path.abspath(args.out)) or ".", 0o700)
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

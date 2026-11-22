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
import multiprocessing
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


def smaps_rollup() -> dict[str, int]:
    """RSS alone cannot show sharing: shared pages count in every process' RSS."""
    wanted = {"Rss", "Pss", "Shared_Clean", "Shared_Dirty", "Private_Clean",
              "Private_Dirty", "RssAnon", "RssFile"}
    out: dict[str, int] = {}
    try:
        with open("/proc/self/smaps_rollup", "r", encoding="utf-8") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in wanted:
                    out[key] = int(rest.split()[0])
    except OSError:
        pass
    return out


def touch_view(view: memoryview) -> int:
    """Force one real pass over the bytes, not just the page-table lookup."""
    buffer = bytearray(len(view))
    buffer[:] = view
    return len(buffer)


def timed_read(pager: WeightPager, block_id: str, req_id: str) -> float:
    started = time.perf_counter()
    view = pager.read_block(block_id, req_id=req_id, copy=False)
    touch_view(view)
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


def _worker(manifest_path: str, ids: list[str], cache_path: str, conn) -> None:
    manifest = WeightManifest.load(manifest_path)
    pager = WeightPager(manifest, audit=None, hash_cache=HashCache(cache_path))
    conn.send({"phase": "ready", "smaps": smaps_rollup()})
    conn.recv()
    for block_id in ids:
        view = pager.read_block(block_id, req_id="worker", copy=False)
        touch_view(view)
        view.release()
    conn.send({"phase": "done", "smaps": smaps_rollup()})
    conn.recv()
    pager.close()


def two_process_sharing(manifest_path: str, ids: list[str], cache_path: str) -> dict:
    """Keep client 1's maps open while client 2 touches the same shard."""
    context = multiprocessing.get_context("fork")
    p1, c1 = context.Pipe()
    p2, c2 = context.Pipe()
    first = context.Process(target=_worker, args=(manifest_path, ids, cache_path, c1))
    second = context.Process(target=_worker, args=(manifest_path, ids, cache_path, c2))
    first.start()
    first_before = p1.recv()["smaps"]
    p1.send("go")
    first_after = p1.recv()["smaps"]

    second.start()
    second_before = p2.recv()["smaps"]
    p2.send("go")
    second_after = p2.recv()["smaps"]

    p1.send("exit")
    p2.send("exit")
    first.join(timeout=10)
    second.join(timeout=10)

    def delta(before: dict, after: dict, key: str) -> int:
        return int(after.get(key, 0) - before.get(key, 0))

    return {
        "client1_rss_after_kb": first_after.get("Rss", 0),
        "client2_shared_clean_delta_kb": delta(second_before, second_after, "Shared_Clean"),
        "client2_shared_dirty_delta_kb": delta(second_before, second_after, "Shared_Dirty"),
        "client2_private_dirty_delta_kb": delta(second_before, second_after, "Private_Dirty"),
        "client2_rss_anon_delta_kb": delta(second_before, second_after, "RssAnon"),
        "client2_pss_delta_kb": delta(second_before, second_after, "Pss"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mb", type=int, default=128)
    parser.add_argument("--block-mb", type=int, default=16)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="parametral-bench-",
                                         dir=os.environ.get("PARAMETRAL_BENCH_DIR", "/var/tmp")) as tmp:
        root = Path(tmp)
        shard = root / "synthetic.safetensors"
        block_bytes = args.block_mb * 1024 * 1024
        size = args.size_mb * 1024 * 1024
        shard.write_bytes((bytes(range(256)) * ((size // 256) + 1))[:size])
        with open(shard, "rb") as handle:
            os.fsync(handle.fileno())
        drop_cache(str(shard))
        manifest_data = build_manifest(str(shard), block_size=block_bytes,
                                       model="synthetic-bench")
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))
        manifest = WeightManifest.load(str(manifest_path))
        ids = list(manifest.blocks)
        audit = BlockAuditLog(str(root / "blockaudit.jsonl"))
        cache = HashCache(str(root / "hashcache.json"))

        pager = WeightPager(manifest, audit=None, hash_cache=cache)
        cold = []
        for block_id in ids:
            cold.append(timed_read(pager, block_id, "cold"))
        hot = []
        for block_id in ids:
            hot.append(timed_read(pager, block_id, "hot"))
        rss_one = rss_kb()
        smaps_one = smaps_rollup()

        second = WeightPager(manifest, audit=None, hash_cache=cache)
        for block_id in ids:
            view = second.read_block(block_id, req_id="second", copy=False)
            touch_view(view)
            view.release()
        rss_two = rss_kb()
        smaps_two = smaps_rollup()

        audit_pager = WeightPager(manifest, audit=audit, hash_cache=cache)
        audit_pager.read_block(ids[0], req_id="audit-evidence")
        audit_pager.close()
        audit_result = audit.verify()
        two_process = two_process_sharing(str(manifest_path), ids,
                                          str(root / "hashcache-shared.json"))
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
            "smaps_delta_kb_second_pager": {
                key: smaps_two.get(key, 0) - smaps_one.get(key, 0)
                for key in sorted(set(smaps_one) | set(smaps_two))
            },
            "hash": pager.snapshot_stats(),
            "audit": audit_result,
            "two_process": two_process,
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

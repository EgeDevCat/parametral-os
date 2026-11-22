"""Weight pager: aligned mmap blocks, content hashes, LRU/pin and block audit."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from parametral.blockaudit import BlockAuditLog
from parametral.weightpager import (HashCache, WeightManifest, WeightPager,
                                    WeightPagerError, build_manifest,
                                    build_manifest_from_safetensors)


class PagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.shard = self.root / "model.safetensors"
        self.shard.write_bytes(bytes(range(256)) * 512)  # 128 KiB, deterministic
        self.manifest_data = build_manifest(str(self.shard), block_size=16 * 1024,
                                            model="synthetic-9b")
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest_data))
        self.manifest = WeightManifest.load(str(self.manifest_path))
        self.audit = BlockAuditLog(str(self.root / "blockaudit.jsonl"))

    def tearDown(self):
        self.tmp.cleanup()

    def pager(self, **kwargs) -> WeightPager:
        return WeightPager(self.manifest, audit=self.audit, **kwargs)

    def test_manifest_blocks_are_aligned_and_hashed(self):
        self.assertTrue(self.manifest.blocks)
        for block in self.manifest.blocks.values():
            self.assertEqual(block.offset % 4096, 0)
            self.assertTrue(block.sha256.startswith("sha256:"))
            self.assertEqual(len(block.sha256), 71)

    def test_read_is_bytes_and_audited(self):
        pager = self.pager()
        block = next(iter(self.manifest.blocks.values()))
        data = pager.read_block(block.block_id, req_id="req-1")
        self.assertEqual(len(data), block.length)
        self.assertEqual("sha256:" + __import__("hashlib").sha256(data).hexdigest(),
                         block.sha256)
        pager.read_block(block.block_id, req_id="req-2")
        stats = pager.snapshot_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        records = self.audit.query(10)
        reads = [record for record in records if record["event"] == "weight.block.read"]
        self.assertEqual(len(reads), 2)
        self.assertFalse(reads[0]["resident"])
        self.assertTrue(reads[1]["resident"])
        self.assertTrue(reads[0]["content_sha256"].startswith("sha256:"))
        self.assertTrue(self.audit.verify()["verified"])
        pager.close()

    def test_content_hash_is_verified_before_serving(self):
        with open(self.shard, "r+b") as handle:
            handle.seek(0)
            handle.write(b"\xff")
        pager = self.pager()
        block = next(iter(self.manifest.blocks.values()))
        with self.assertRaises(WeightPagerError) as ctx:
            pager.read_block(block.block_id, req_id="bad")
        self.assertEqual(ctx.exception.code, "BLOCK_HASH_MISMATCH")
        pager.close()

    def test_prefetch_emits_batch_event(self):
        pager = self.pager()
        ids = [block.block_id for block in list(self.manifest.blocks.values())[:3]]
        result = pager.prefetch(ids, req_id="pre-1")
        self.assertEqual(result["block_ids"], ids)
        self.assertGreater(result["bytes"], 0)
        records = self.audit.query(10)
        batch = [record for record in records if record["event"] == "weight.pagein.batch"]
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["block_ids"], ids)
        pager.close()

    def test_pinned_block_is_not_evicted(self):
        pager = self.pager(max_resident_bytes=16 * 1024)
        ids = [block.block_id for block in list(self.manifest.blocks.values())[:3]]
        with pager.pinned([ids[0]]):
            pager.read_block(ids[0], req_id="active")
            with self.assertRaises(WeightPagerError) as ctx:
                pager.read_block(ids[1], req_id="active")
            self.assertEqual(ctx.exception.code, "PINNED_LIMIT")
        pager.close()

    def test_explicit_evict_unmaps_and_audits(self):
        pager = self.pager()
        block_id = next(iter(self.manifest.blocks))
        pager.read_block(block_id, req_id="r")
        self.assertTrue(pager.evict(block_id, req_id="e"))
        self.assertEqual(pager.snapshot_stats()["resident_blocks"], 0)
        records = self.audit.query(10)
        self.assertTrue(any(record["event"] == "weight.block.evict" for record in records))
        pager.close()

    def test_audit_tampering_is_detected(self):
        pager = self.pager()
        block_id = next(iter(self.manifest.blocks))
        pager.read_block(block_id, req_id="r")
        pager.close()
        path = self.root / "blockaudit.jsonl"
        lines = path.read_text().splitlines()
        record = json.loads(lines[0])
        record["block_id"] = "forged"
        lines[0] = json.dumps(record, sort_keys=True)
        path.write_text("\n".join(lines) + "\n")
        self.assertFalse(self.audit.verify()["verified"])

    def test_unaligned_manifest_is_refused(self):
        data = json.loads(self.manifest_path.read_text())
        data["blocks"][0]["offset"] = 1
        with self.assertRaises(WeightPagerError):
            WeightManifest(data, str(self.root))

    def test_cold_hash_is_cached_across_pagers(self):
        cache = HashCache(str(self.root / "hashcache.json"))
        block = next(iter(self.manifest.blocks.values()))
        first = WeightPager(self.manifest, audit=self.audit, hash_cache=cache)
        first.read_block(block.block_id, req_id="cold")
        self.assertEqual(first.snapshot_stats()["hash_computed"], 1)
        first.close()
        second = WeightPager(self.manifest, audit=self.audit, hash_cache=cache)
        second.read_block(block.block_id, req_id="warm")
        stats = second.snapshot_stats()
        self.assertEqual(stats["hash_computed"], 0)
        self.assertEqual(stats["hash_skipped"], 1)
        second.close()

    def test_safetensors_blocks_are_aligned_and_do_not_cut_tensors(self):
        # 8-byte length + header + data. The header length deliberately leaves the data
        # section unaligned; the builder must round the block, not split a tensor.
        header = json.dumps({
            "t1": {"dtype": "U8", "shape": [3], "data_offsets": [0, 3]},
            "t2": {"dtype": "U8", "shape": [3], "data_offsets": [3, 6]},
        }).encode()
        blob = self.root / "real.safetensors"
        blob.write_bytes(len(header).to_bytes(8, "little") + header + b"abcdef")
        data = build_manifest_from_safetensors(str(blob), max_block_size=4096,
                                               model="tiny")
        self.assertTrue(data["blocks"])
        for block in data["blocks"]:
            self.assertEqual(block["offset"] % 4096, 0)
        self.assertEqual(set(data["tensors"]), {"t1", "t2"})
        for tensor, blocks in data["tensors"].items():
            self.assertTrue(blocks, tensor)
            for block_id in blocks:
                self.assertIn(block_id, {item["block_id"] for item in data["blocks"]})
        manifest_path = self.root / "real-manifest.json"
        manifest_path.write_text(json.dumps(data))
        manifest = WeightManifest.load(str(manifest_path))
        pager = WeightPager(manifest, audit=self.audit)
        self.assertEqual(pager.read_tensor("t1", req_id="t1"), b"abc")
        self.assertEqual(pager.read_tensor("t2", req_id="t2"), b"def")
        pager.close()


if __name__ == "__main__":
    unittest.main()

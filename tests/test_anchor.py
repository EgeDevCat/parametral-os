"""Audit anchors: the local chain plus an off-host signed head, both must agree."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401  (sys.path)

from parametral import anchor, ed25519
from parametral.audit import AuditLog


class AnchorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="parametral-anchor-")
        self.log = AuditLog(os.path.join(self.tmp, "audit"), node_id="local")
        self.anchors = os.path.join(self.tmp, "anchors")
        self.sk = os.path.join(self.tmp, "anchor.sk")
        self.pub = os.path.join(self.tmp, "anchor.pub")
        ed25519.keygen(self.sk, self.pub)
        for index in range(3):
            self.log.append(method="v1.exec.run", actor="token:tok_x", params={"i": index})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_anchor_roundtrip_verifies(self):
        record = anchor.write_anchor(self.log, self.anchors, self.sk)
        self.assertEqual(record["payload"]["seq"], 3)
        self.assertEqual(record["payload"]["head_hash"], self.log.head["head_hash"])
        result = anchor.verify_anchors(self.log, self.anchors, self.pub)
        self.assertTrue(result["signatures_ok"])
        self.assertTrue(result["chain_matches"])
        self.assertTrue(result["chain_verified"])
        self.assertEqual(result["anchored_seq"], 3)

    def test_anchors_append_and_stay_monotonic(self):
        anchor.write_anchor(self.log, self.anchors, self.sk)
        self.log.append(method="v1.fs.write", actor="token:tok_y", params={})
        anchor.write_anchor(self.log, self.anchors, self.sk)
        records = anchor.read_anchors(self.anchors)
        self.assertEqual([r["payload"]["seq"] for r in records], [3, 4])
        result = anchor.verify_anchors(self.log, self.anchors, self.pub)
        self.assertTrue(result["signatures_ok"] and result["chain_matches"])
        self.assertEqual(result["anchored_seq"], 4)

    def test_rewritten_local_log_is_detected(self):
        anchor.write_anchor(self.log, self.anchors, self.sk)
        path = self.log.path
        lines = open(path).read().splitlines()
        record = json.loads(lines[-1])          # the anchored head
        record["params_sha256"] = "sha256:" + "0" * 64
        lines[-1] = json.dumps(record, sort_keys=True)
        open(path, "w").write("\n".join(lines) + "\n")
        result = anchor.verify_anchors(self.log, self.anchors, self.pub)
        self.assertFalse(result["chain_matches"])
        self.assertTrue("differs from the anchored hash" in result["reason"]
                        or "does not verify" in result["reason"])

    def test_deleted_local_log_is_detected(self):
        anchor.write_anchor(self.log, self.anchors, self.sk)
        open(self.log.path, "w").write("")
        result = anchor.verify_anchors(self.log, self.anchors, self.pub)
        self.assertFalse(result["chain_matches"])
        self.assertIn("truncated", result["reason"])

    def test_forged_anchor_is_detected(self):
        anchor.write_anchor(self.log, self.anchors, self.sk)
        path = os.path.join(self.anchors, anchor.ANCHORS_FILE)
        record = json.loads(open(path).read().splitlines()[0])
        record["payload"]["seq"] = 999
        open(path, "w").write(json.dumps(record) + "\n")
        result = anchor.verify_anchors(self.log, self.anchors, self.pub)
        self.assertFalse(result["signatures_ok"])
        self.assertEqual(result["first_bad"], 1)

    def test_anchor_with_another_key_is_rejected(self):
        anchor.write_anchor(self.log, self.anchors, self.sk)
        other_sk = os.path.join(self.tmp, "other.sk")
        other_pub = os.path.join(self.tmp, "other.pub")
        ed25519.keygen(other_sk, other_pub)
        result = anchor.verify_anchors(self.log, self.anchors, other_pub)
        self.assertFalse(result["signatures_ok"])

    def test_empty_log_cannot_be_anchored(self):
        empty = AuditLog(os.path.join(self.tmp, "empty"), node_id="local")
        with self.assertRaises(anchor.AnchorError):
            anchor.write_anchor(empty, self.anchors, self.sk)

    def test_missing_anchor_file_is_reported(self):
        with self.assertRaises(anchor.AnchorError):
            anchor.verify_anchors(self.log, os.path.join(self.tmp, "nope"), self.pub)


if __name__ == "__main__":
    unittest.main()

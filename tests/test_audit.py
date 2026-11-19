"""Audit log: append-only chain, tamper detection, truncation detection, queries."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401

from parametral.audit import AuditLog, GENESIS


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="parametral-audit-")
        self.log = AuditLog(self.dir, node_id="local")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _append(self, n=3, method="v1.exec.run"):
        return [self.log.append(method=method, actor="token:tok_x", params={"i": i},
                                result="ok", sandbox_id="sbx_l_a") for i in range(n)]

    def test_chain_links_and_verifies(self):
        records = self._append(3)
        self.assertEqual([r["seq"] for r in records], [1, 2, 3])
        self.assertEqual(records[0]["prev_hash"], GENESIS)
        self.assertEqual(records[1]["prev_hash"], records[0]["hash"])
        self.assertTrue(self.log.verify()["verified"])
        self.assertEqual(self.log.verify()["records"], 3)

    def test_modification_is_detected(self):
        self._append(3)
        path = self.log.path
        lines = open(path).read().splitlines()
        record = json.loads(lines[1])
        record["result"] = "ok" if record["result"] != "ok" else "tampered"
        lines[1] = json.dumps(record, sort_keys=True)
        open(path, "w").write("\n".join(lines) + "\n")
        result = self.log.verify()
        self.assertFalse(result["verified"])
        self.assertEqual(result["first_broken_seq"], 2)
        self.assertIn("hash mismatch", result["reason"])

    def test_deletion_is_detected(self):
        self._append(3)
        path = self.log.path
        lines = open(path).read().splitlines()
        del lines[1]
        open(path, "w").write("\n".join(lines) + "\n")
        result = self.log.verify()
        self.assertFalse(result["verified"])
        self.assertEqual(result["first_broken_seq"], 2)

    def test_truncation_is_detected_by_head(self):
        self._append(3)
        path = self.log.path
        lines = open(path).read().splitlines()
        open(path, "w").write(lines[0] + "\n")
        result = self.log.verify()
        self.assertFalse(result["verified"])
        self.assertIn("truncation", result["reason"])

    def test_appending_after_restart_continues_the_chain(self):
        self._append(2)
        head = self.log.verify()["head_hash"]
        reloaded = AuditLog(self.dir, node_id="local")
        record = reloaded.append(method="v1.fs.write", actor="token:tok_y", params={})
        self.assertEqual(record["seq"], 3)
        self.assertEqual(record["prev_hash"], head)
        self.assertTrue(reloaded.verify()["verified"])

    def test_query_filters_and_paginates(self):
        self._append(2, method="v1.exec.run")
        self._append(2, method="v1.fs.write")
        everything = self.log.query()
        self.assertEqual(len(everything), 4)
        only_fs = self.log.query(method="v1.fs.write")
        self.assertEqual([r["seq"] for r in only_fs], [3, 4])
        page = self.log.query(from_seq=3, limit=1)
        self.assertEqual(len(page), 1)
        self.assertEqual(page[0]["seq"], 3)

    def test_records_carry_required_fields(self):
        record = self._append(1)[0]
        for field in ("seq", "ts", "node_id", "method", "actor", "token_id", "approval_id",
                      "sandbox_id", "params_sha256", "result", "exit_code", "duration_ms",
                      "detail", "severity", "prev_hash", "hash"):
            self.assertIn(field, record)
        self.assertTrue(record["hash"].startswith("sha256:"))

    def test_chain_from_another_node_is_refused(self):
        self._append(1)
        with self.assertRaises(Exception):
            AuditLog(self.dir, node_id="node-b")


if __name__ == "__main__":
    unittest.main()

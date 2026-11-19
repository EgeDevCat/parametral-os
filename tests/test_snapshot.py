"""Snapshots: the safety net. Pre-change snapshot, one-command rollback, real proof."""
from __future__ import annotations

import os
import unittest

import support

from ultraos.client import ClientError
from ultraos.sandbox import SandboxError, SandboxManager


class SandboxSnapshotTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="ultraos-snap-")
        self.manager = SandboxManager(self.tmp, defaults={"memory_mb": 256})
        self.meta = self.manager.create(name="snap")
        self.sid = self.meta["sandbox_id"]
        if not self.manager.btrfs_available:
            self.skipTest("this state dir cannot make btrfs subvolumes")

    def tearDown(self):
        import shutil

        try:
            self.manager.destroy(self.sid)
        except SandboxError:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, content):
        self.manager.run(self.sid, ["sh", "-c", f"echo {content} > /work/file.txt"])

    def _read(self):
        return self.manager.run(self.sid, ["cat", "/work/file.txt"])["stdout"].strip()

    def test_snapshot_then_restore_rolls_back_content(self):
        self._write("v1")
        snap = self.manager.snapshot(self.sid, label="before-edit", reason="test")
        self._write("v2")
        self.assertEqual(self._read(), "v2")
        result = self.manager.restore(self.sid, snap["snapshot_id"], confirm=True)
        self.assertTrue(result["restored"])
        self.assertEqual(self._read(), "v1")

    def test_restore_takes_a_safety_snapshot_first(self):
        self._write("v1")
        snap = self.manager.snapshot(self.sid)
        self._write("v2")
        result = self.manager.restore(self.sid, snap["snapshot_id"], confirm=True)
        self.assertNotEqual(result["pre_restore_snapshot"], snap["snapshot_id"])
        labels = [record["label"] for record in self.manager.list_snapshots(self.sid)]
        self.assertIn(f"pre-restore-{snap['snapshot_id']}", labels)

    def test_restore_requires_confirm(self):
        snap = self.manager.snapshot(self.sid)
        with self.assertRaises(SandboxError) as raised:
            self.manager.restore(self.sid, snap["snapshot_id"], confirm=False)
        self.assertEqual(raised.exception.code, "INVALID_PARAMS")

    def test_snapshot_of_another_sandbox_is_refused(self):
        snap = self.manager.snapshot(self.sid)
        other = self.manager.create(name="other")
        try:
            with self.assertRaises(SandboxError):
                self.manager.restore(other["sandbox_id"], snap["snapshot_id"], confirm=True)
        finally:
            self.manager.destroy(other["sandbox_id"])

    def test_unknown_snapshot_is_not_found(self):
        with self.assertRaises((SandboxError, FileNotFoundError)):
            self.manager.restore(self.sid, "snap_19700101T000000_000000", confirm=True)

    def test_snapshot_covers_home_too(self):
        self.manager.run(self.sid, ["sh", "-c", "echo note > /home/user/n.txt"])
        snap = self.manager.snapshot(self.sid)
        self.manager.run(self.sid, ["sh", "-c", "echo changed > /home/user/n.txt"])
        self.manager.restore(self.sid, snap["snapshot_id"], confirm=True)
        result = self.manager.run(self.sid, ["cat", "/home/user/n.txt"])
        self.assertEqual(result["stdout"].strip(), "note")

    def test_snapshots_are_read_only(self):
        snap = self.manager.snapshot(self.sid)
        target = os.path.join(snap["paths"]["root"], "should-fail")
        with self.assertRaises(OSError):
            open(target, "w").write("x")


class DaemonSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = support.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.close()

    def setUp(self):
        self.client = self.harness.client()
        self.sandbox = support.make_sandbox(self.harness, name="snapapi")
        self.sid = self.sandbox["sandbox_id"]
        if not self.harness.daemon.sandboxes.btrfs_available:
            self.skipTest("no btrfs subvolume support in this state dir")

    def tearDown(self):
        try:
            token = self.client.request_permission("sandbox.destroy",
                                                   {"sandbox_id": self.sid},
                                                   "cleanup")["capability_token"]
            self.client.call("v1.sandbox.destroy", sandbox_id=self.sid, capability_token=token)
        except ClientError:
            pass
        self.client.close()

    def test_snapshot_create_and_list_need_only_a_token(self):
        token = support.token_for(self.harness, "snapshot.create",
                                  {"sandbox_id": self.sid})["capability_token"]
        created = self.client.call("v1.snapshot.create", sandbox_id=self.sid,
                                   label="api", capability_token=token)
        self.assertTrue(created["snapshot_id"].startswith("snap_"))
        self.assertTrue(created["read_only"])
        list_token = support.token_for(self.harness, "snapshot.list",
                                       {"sandbox_id": self.sid})["capability_token"]
        listing = self.client.call("v1.snapshot.list", sandbox_id=self.sid,
                                   capability_token=list_token)
        self.assertIn(created["snapshot_id"],
                      [record["snapshot_id"] for record in listing["snapshots"]])

    def test_restore_is_approval_gated(self):
        token = support.token_for(self.harness, "snapshot.create",
                                  {"sandbox_id": self.sid})["capability_token"]
        snapshot = self.client.call("v1.snapshot.create", sandbox_id=self.sid,
                                    capability_token=token)
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("snapshot.restore",
                                           {"sandbox_id": self.sid}, "roll back")
        self.assertEqual(raised.exception.code, -32004)
        self.assertEqual(raised.exception.data["ultraos_code"], "APPROVAL_REQUIRED")

        approval_id = raised.exception.data["approval_id"]
        from ultraos.approvals import ApprovalStore

        store = self.harness.approver_store()
        proof = store.proof(approval_id, "approved")
        self.client.call("v1.approvals.decide", approval_id=approval_id, decision="approve",
                         approver_proof=proof, decided_by="user:test")
        granted = self.client.request_permission("snapshot.restore", {"sandbox_id": self.sid},
                                                 "roll back", approval_id=approval_id)
        result = self.client.call("v1.snapshot.restore", sandbox_id=self.sid,
                                  snapshot_id=snapshot["snapshot_id"], confirm=True,
                                  capability_token=granted["capability_token"])
        self.assertTrue(result["restored"])

    def test_restore_without_confirm_is_refused(self):
        token = support.token_for(self.harness, "snapshot.create",
                                  {"sandbox_id": self.sid})["capability_token"]
        snapshot = self.client.call("v1.snapshot.create", sandbox_id=self.sid,
                                    capability_token=token)
        approval_id = None
        try:
            self.client.request_permission("snapshot.restore", {"sandbox_id": self.sid}, "roll back")
        except ClientError as exc:
            approval_id = exc.data["approval_id"]
        from ultraos.approvals import ApprovalStore

        proof = self.harness.approver_store().proof(approval_id, "approved")
        self.client.call("v1.approvals.decide", approval_id=approval_id, decision="approve",
                         approver_proof=proof, decided_by="user:test")
        granted = self.client.request_permission("snapshot.restore", {"sandbox_id": self.sid},
                                                 "roll back", approval_id=approval_id)
        with self.assertRaises(ClientError) as raised:
            self.client.call("v1.snapshot.restore", sandbox_id=self.sid,
                             snapshot_id=snapshot["snapshot_id"], confirm=False,
                             capability_token=granted["capability_token"])
        self.assertEqual(raised.exception.code, -32602)


if __name__ == "__main__":
    unittest.main()

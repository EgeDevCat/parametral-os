"""End-to-end daemon tests: the API, the gates, and what the audit log records."""
from __future__ import annotations

import json
import os
import socket
import unittest

import support

from ultraos.approvals import ApprovalStore
from ultraos.client import ClientError


class DaemonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = support.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.close()

    def setUp(self):
        self.client = self.harness.client()
        self.sandbox = support.make_sandbox(self.harness, name="daemon-%s" % self._testMethodName[:20])
        self.sandbox_id = self.sandbox["sandbox_id"]

    def tearDown(self):
        try:
            token = self.client.request_permission("sandbox.destroy",
                                                   {"sandbox_id": self.sandbox_id},
                                                   "cleanup")["capability_token"]
            self.client.call("v1.sandbox.destroy", sandbox_id=self.sandbox_id,
                             capability_token=token)
        except ClientError:
            pass
        self.client.close()

    # ------------------------------------------------------------- protocol

    def test_hello_negotiates_v1(self):
        result = self.client.hello()
        self.assertEqual(result["selected"], "v1")
        self.assertIn("v1", result["protocol_versions"])
        self.assertEqual(result["node_id"], "local")
        self.assertIn("sandbox.bwrap", result["features"])

    def test_status_reports_quota_backend_and_audit(self):
        status = self.client.status()
        self.assertEqual(status["node_id"], "local")
        self.assertIn(status["quota_backend"], ("cgroup2", "rlimits"))
        self.assertGreaterEqual(status["audit"]["head_seq"], 1)
        self.assertTrue(status["audit"]["verified"])

    def test_node_mismatch_is_rejected(self):
        with self.assertRaises(ClientError) as raised:
            self.client.call("v1.node.status", node_id="node-42")
        self.assertEqual(raised.exception.code, -32011)
        self.assertEqual(raised.exception.ultraos_code, "NODE_MISMATCH")

    def test_unknown_method(self):
        with self.assertRaises(ClientError) as raised:
            self.client.call("v1.swarm.conquer")
        self.assertEqual(raised.exception.code, -32601)

    def test_malformed_json_gets_parse_error(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as raw:
            raw.connect(self.harness.socket_path)
            raw.sendall(b"{not json}\n")
            response = json.loads(raw.makefile("rb").readline())
        self.assertEqual(response["error"]["code"], -32700)

    # ---------------------------------------------------------- default deny

    def test_exec_without_token_is_refused(self):
        with self.assertRaises(ClientError) as raised:
            self.client.call("v1.exec.run", sandbox_id=self.sandbox_id, cmd=["echo", "hi"])
        self.assertEqual(raised.exception.code, -32002)
        self.assertEqual(raised.exception.ultraos_code, "TOKEN_REQUIRED")

    def test_dangerous_command_denied_at_policy_level(self):
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("exec.run",
                                           {"sandbox_id": self.sandbox_id, "commands": ["curl"]},
                                           "download something")
        self.assertEqual(raised.exception.code, -32001)
        self.assertEqual(raised.exception.data["rule_id"], "deny-dangerous-commands")

    def test_token_smuggling_a_second_command_is_refused(self):
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission(
                "exec.run", {"sandbox_id": self.sandbox_id, "commands": ["git", "curl"]},
                "try to sneak curl in")
        self.assertEqual(raised.exception.code, -32001)

    def test_fs_read_of_host_path_is_denied(self):
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("fs.read",
                                           {"sandbox_id": self.sandbox_id,
                                            "paths": ["/etc/passwd"]},
                                           "read shadow")
        self.assertEqual(raised.exception.code, -32001)
        self.assertEqual(raised.exception.data["rule_id"], "deny-host-escape")

    def test_token_is_bound_to_its_sandbox(self):
        granted = support.token_for(self.harness, "exec.run",
                                    {"sandbox_id": self.sandbox_id, "commands": ["echo"]})
        other = support.make_sandbox(self.harness, name="other-sandbox")
        try:
            with self.assertRaises(ClientError) as raised:
                self.client.call("v1.exec.run", sandbox_id=other["sandbox_id"],
                                 cmd=["echo", "hi"], capability_token=granted["capability_token"])
            self.assertEqual(raised.exception.code, -32003)
        finally:
            destroy = self.client.request_permission("sandbox.destroy",
                                                     {"sandbox_id": other["sandbox_id"]},
                                                     "cleanup")["capability_token"]
            self.client.call("v1.sandbox.destroy", sandbox_id=other["sandbox_id"],
                             capability_token=destroy)

    def test_token_uses_are_limited(self):
        granted = support.token_for(self.harness, "exec.run",
                                    {"sandbox_id": self.sandbox_id, "commands": ["echo"]},
                                    max_uses=1)
        self.client.call("v1.exec.run", sandbox_id=self.sandbox_id, cmd=["echo", "hi"],
                         capability_token=granted["capability_token"])
        with self.assertRaises(ClientError) as raised:
            self.client.call("v1.exec.run", sandbox_id=self.sandbox_id, cmd=["echo", "again"],
                             capability_token=granted["capability_token"])
        self.assertEqual(raised.exception.code, -32003)

    # -------------------------------------------------------------- the work

    def test_exec_runs_isolated_and_reports_metadata(self):
        granted = support.token_for(self.harness, "exec.run",
                                    {"sandbox_id": self.sandbox_id, "commands": ["sh"]})
        result = self.client.exec(self.sandbox_id, ["sh", "-c", "echo inside; whoami; id -u"],
                                  granted["capability_token"])
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("inside", result["stdout"])
        self.assertNotIn("root", result["stdout"].split()[:1])
        self.assertEqual(result["seccomp_profile"], "blacklist-v1")
        self.assertIn(result["quota_backend"], ("cgroup2", "rlimits"))
        self.assertIn("duration_ms", result)

    def test_exec_sees_no_network(self):
        granted = support.token_for(self.harness, "exec.run",
                                    {"sandbox_id": self.sandbox_id, "commands": ["python3"]})
        script = ("import socket\ns=socket.socket()\ns.settimeout(2)\n"
                  "try:\n s.connect(('1.1.1.1',80))\n print('OPEN')\n"
                  "except OSError as e:\n print('CLOSED', e.errno)\n")
        result = self.client.exec(self.sandbox_id, ["python3", "-c", script],
                                  granted["capability_token"])
        self.assertIn("CLOSED", result["stdout"])

    def test_fs_roundtrip(self):
        write = support.token_for(self.harness, "fs.write",
                                  {"sandbox_id": self.sandbox_id, "paths": ["/work/**"]},
                                  "write files")["capability_token"]
        read = support.token_for(self.harness, "fs.read",
                                 {"sandbox_id": self.sandbox_id, "paths": ["/work/**"]},
                                 "read files")["capability_token"]

        created = self.client.call("v1.fs.write", sandbox_id=self.sandbox_id, path="/work/notes.txt",
                                   content="hello\n", capability_token=write)
        self.assertTrue(created["created"])
        self.assertEqual(created["size"], 6)

        content = self.client.call("v1.fs.read", sandbox_id=self.sandbox_id, path="/work/notes.txt",
                                   capability_token=read)
        self.assertEqual(content["content"], "hello\n")
        self.assertEqual(content["encoding"], "utf-8")

        edited = self.client.call("v1.fs.edit", sandbox_id=self.sandbox_id, path="/work/notes.txt",
                                  old="hello", new="merhaba", capability_token=write)
        self.assertEqual(edited["replacements"], 1)

        listing = self.client.call("v1.fs.list", sandbox_id=self.sandbox_id, path="/work",
                                   capability_token=read)
        self.assertEqual([entry["name"] for entry in listing["entries"]], ["notes.txt"])

        deleted = self.client.call("v1.fs.delete", sandbox_id=self.sandbox_id,
                                   path="/work/notes.txt", capability_token=write)
        self.assertTrue(deleted["deleted"])

    def test_fs_escape_attempt_is_audited_as_security_event(self):
        token = support.token_for(self.harness, "fs.read",
                                  {"sandbox_id": self.sandbox_id, "paths": ["/work/**"]},
                                  "read files")["capability_token"]
        with self.assertRaises(ClientError) as raised:
            self.client.call("v1.fs.read", sandbox_id=self.sandbox_id,
                             path="/work/../../etc/passwd", capability_token=token)
        self.assertEqual(raised.exception.code, -32007)

        records = self.harness.daemon.audit.query(limit=200)
        security = [record for record in records if record["severity"] == "security"]
        self.assertTrue(security, "escape attempt must be logged as a security event")
        self.assertIn("LIMIT_EXCEEDED", json.dumps(security[-1]))

    def test_idempotency_key_replays_the_same_result(self):
        token = support.token_for(self.harness, "fs.write",
                                  {"sandbox_id": self.sandbox_id, "paths": ["/work/**"]},
                                  "write")["capability_token"]
        first = self.client.call("v1.fs.write", sandbox_id=self.sandbox_id, path="/work/idem.txt",
                                 content="one", idempotency_key="key-1", capability_token=token)
        second = self.client.call("v1.fs.write", sandbox_id=self.sandbox_id, path="/work/idem.txt",
                                  content="two", idempotency_key="key-1", capability_token=token)
        self.assertEqual(first["sha256"], second["sha256"])

    # ------------------------------------------------------------ approvals

    def _approver(self) -> ApprovalStore:
        return ApprovalStore(self.harness.state, self.harness.approver_key_path)

    def test_approval_gate_full_flow(self):
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("app.install", {"sandbox_id": self.sandbox_id},
                                           "install ripgrep")
        self.assertEqual(raised.exception.code, -32004)
        approval_id = raised.exception.data["approval_id"]

        pending = self.client.call("v1.approvals.list", state="pending")["approvals"]
        self.assertIn(approval_id, [item["approval_id"] for item in pending])

        with self.assertRaises(ClientError) as no_proof:
            self.client.call("v1.approvals.decide", approval_id=approval_id,
                             decision="approve", approver_proof="")
        self.assertEqual(no_proof.exception.code, -32010)

        wrong = self._approver().proof(approval_id, "rejected")
        with self.assertRaises(ClientError):
            self.client.call("v1.approvals.decide", approval_id=approval_id,
                             decision="approve", approver_proof=wrong)

        proof = self._approver().proof(approval_id, "approved")
        decided = self.client.call("v1.approvals.decide", approval_id=approval_id,
                                   decision="approve", approver_proof=proof,
                                   decided_by="user:test")
        self.assertEqual(decided["state"], "approved")

        granted = self.client.request_permission("app.install", {"sandbox_id": self.sandbox_id},
                                                 "install ripgrep", approval_id=approval_id)
        self.assertEqual(granted["approval_id"], approval_id)
        self.assertIn("app.install", granted["ops"])

        with self.assertRaises(ClientError) as unsupported:
            self.client.call("v1.app.install", sandbox_id=self.sandbox_id,
                             manifest={"name": "ripgrep", "version": "14.1.1"},
                             capability_token=granted["capability_token"])
        self.assertEqual(unsupported.exception.code, -32008)
        self.assertEqual(unsupported.exception.data["milestone"], "phase-2")

    def test_rejected_approval_cannot_mint_a_token(self):
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("snapshot.restore", {}, "rollback everything")
        approval_id = raised.exception.data["approval_id"]
        proof = self._approver().proof(approval_id, "rejected")
        self.client.call("v1.approvals.decide", approval_id=approval_id, decision="reject",
                         approver_proof=proof, decided_by="user:test")
        with self.assertRaises(ClientError) as second:
            self.client.request_permission("snapshot.restore", {}, "rollback everything",
                                           approval_id=approval_id)
        self.assertEqual(second.exception.code, -32005)

    # ---------------------------------------------------------------- audit

    def test_every_request_is_audited(self):
        before = self.client.call("v1.audit.verify")["records"]
        token = support.token_for(self.harness, "exec.run",
                                  {"sandbox_id": self.sandbox_id, "commands": ["echo"]},
                                  "run echo")["capability_token"]
        self.client.call("v1.exec.run", sandbox_id=self.sandbox_id, cmd=["echo", "audit"],
                         capability_token=token)
        after = self.client.call("v1.audit.verify")
        self.assertTrue(after["verified"])
        self.assertGreater(after["records"], before)
        self.assertGreaterEqual(after["head_seq"], after["records"])

    def test_audit_query_needs_a_token(self):
        with self.assertRaises(ClientError) as raised:
            self.client.call("v1.audit.query", limit=5)
        self.assertEqual(raised.exception.code, -32002)
        token = support.token_for(self.harness, "audit.read", {}, "inspect trail")["capability_token"]
        page = self.client.call("v1.audit.query", limit=5, capability_token=token)
        self.assertTrue(page["records"])
        self.assertIn("next_seq", page)

    def test_snapshot_create_is_implemented_or_honestly_unsupported(self):
        token = support.token_for(self.harness, "snapshot.create",
                                  {"sandbox_id": self.sandbox_id},
                                  "snapshot")["capability_token"]
        try:
            created = self.client.call("v1.snapshot.create", sandbox_id=self.sandbox_id,
                                       label="daemon-test", capability_token=token)
            self.assertTrue(created["snapshot_id"].startswith("snap_"))
        except ClientError as exc:
            # No btrfs subvolume support on this state dir: must say so, not pretend.
            self.assertEqual(exc.code, -32008)
            self.assertEqual(exc.data["milestone"], "phase-4")


if __name__ == "__main__":
    unittest.main()

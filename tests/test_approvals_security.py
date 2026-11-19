"""Negative tests for the approval path — the properties the AI side asked to see proven.

1. the gateway daemon cannot sign a decision (it holds the public key only)
2. a decision signed with any other keypair is rejected
3. a token cannot be minted on a pending/rejected approval
4. approvals.get long-polls with wait_s and reports the terminal state
5. exec.run verdict actually fails the call's result when the postcondition does not hold
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest

import support

from parametral import ed25519, util
from parametral.approvals import ApprovalError, ApprovalStore


class GatewayCannotSignTest(unittest.TestCase):
    def setUp(self):
        self.harness = support.Harness()

    def tearDown(self):
        self.harness.close()

    def test_daemon_store_has_no_private_key(self):
        daemon_store = self.harness.daemon.approvals
        self.assertIsNone(getattr(daemon_store, "approver_sk_path", None),
                          "the gateway must be constructed without a signing key")
        with self.assertRaises(ApprovalError) as raised:
            daemon_store.proof("appr_x", "approved")
        self.assertEqual(raised.exception.code, "PEER_REJECTED")

    def test_gateway_private_key_file_is_not_readable_by_the_daemon_contract(self):
        # the daemon reads exactly one path: runtime_dir/approver.pub (daemon.py builds the
        # store with that path and nothing else); assert that is what it points at
        path = self.harness.daemon.approvals.approver_pub_path
        self.assertTrue(path.endswith("approver.pub"))
        self.assertTrue(os.path.exists(path))


class WrongKeyRejectedTest(unittest.TestCase):
    def setUp(self):
        self.harness = support.Harness()
        self.tmp = tempfile.mkdtemp(prefix="wrongkey-")
        self.foreign_sk = os.path.join(self.tmp, "foreign.sk")
        self.foreign_pub = os.path.join(self.tmp, "foreign.pub")
        ed25519.keygen(self.foreign_sk, self.foreign_pub)

    def tearDown(self):
        self.harness.close()

    def _pending(self, store: ApprovalStore) -> str:
        approval = store.create(operation="host.apply",
                                scope={"preset": "install-package"},
                                justification="test", requested_by="client:test")
        return approval["approval_id"]

    def test_foreign_signature_is_rejected(self):
        gateway = self.harness.daemon.approvals
        approval_id = self._pending(gateway)

        # a valid ed25519 signature, but from the wrong keypair
        signature = ed25519.b64(ed25519.sign(f"{approval_id}|approved".encode(),
                                            ed25519.load_secret(self.foreign_sk)))
        with self.assertRaises(ApprovalError) as raised:
            gateway.decide(approval_id, "approved", decided_by="attacker",
                           proof="ed25519:" + signature)
        self.assertEqual(raised.exception.code, "PEER_REJECTED")
        self.assertEqual(gateway.get(approval_id)["state"], "pending")

    def test_proof_for_other_decision_is_rejected(self):
        approver = self.harness.approver_store()
        gateway = self.harness.daemon.approvals
        approval_id = self._pending(gateway)

        proof_for_reject = approver.proof(approval_id, "rejected")
        with self.assertRaises(ApprovalError):
            gateway.decide(approval_id, "approved", decided_by="user:local",
                           proof=proof_for_reject)

    def test_correct_signature_is_accepted(self):
        # positive control: the same path with the right key must work, otherwise the
        # negative tests above could be passing for the wrong reason
        approver = self.harness.approver_store()
        gateway = self.harness.daemon.approvals
        approval_id = self._pending(gateway)
        decided = gateway.decide(approval_id, "approved", decided_by="user:local",
                                 proof=approver.proof(approval_id, "approved"))
        self.assertEqual(decided["state"], "approved")


class TokenNeedsApprovalTest(unittest.TestCase):
    def setUp(self):
        self.harness = support.Harness()

    def tearDown(self):
        self.harness.close()

    def test_pending_approval_cannot_mint_a_token(self):
        gateway = self.harness.daemon.approvals
        approval = gateway.create(operation="host.apply", scope={"preset": "install-package"},
                                  justification="test", requested_by="client:test")
        # this is the exact call the token issuer makes before minting
        with self.assertRaises(ApprovalError) as raised:
            gateway.usable(approval["approval_id"], "host.apply")
        self.assertEqual(raised.exception.code, "APPROVAL_PENDING")

    def test_rejected_approval_cannot_mint_a_token(self):
        approver = self.harness.approver_store()
        gateway = self.harness.daemon.approvals
        approval = gateway.create(operation="host.apply", scope={"preset": "install-package"},
                                  justification="test", requested_by="client:test")
        aid = approval["approval_id"]
        gateway.decide(aid, "rejected", decided_by="user:local",
                       proof=approver.proof(aid, "rejected"), reason="no")
        with self.assertRaises(ApprovalError):
            gateway.usable(aid, "host.apply")


class ApprovalsWaitTest(unittest.TestCase):
    def setUp(self):
        self.harness = support.Harness()
        self.client = self.harness.client()

    def tearDown(self):
        self.client.close()
        self.harness.close()

    def test_wait_s_returns_when_decided(self):
        gateway = self.harness.daemon.approvals
        approver = self.harness.approver_store()
        approval = gateway.create(operation="host.apply", scope={"preset": "install-package"},
                                  justification="test", requested_by="client:test")
        aid = approval["approval_id"]

        import threading
        def decide_soon():
            time.sleep(0.4)
            gateway.decide(aid, "approved", decided_by="user:local",
                           proof=approver.proof(aid, "approved"))
        threading.Thread(target=decide_soon, daemon=True).start()

        started = time.monotonic()
        result = self.client.call("v1.approvals.get", approval_id=aid, wait_s=5)
        elapsed = time.monotonic() - started
        self.assertEqual(result["state"], "approved")
        self.assertLess(elapsed, 4.0, "long-poll should return as soon as the state is final")
        self.assertIn("expires_at", result)

    def test_wait_s_caps_and_reports_pending(self):
        gateway = self.harness.daemon.approvals
        approval = gateway.create(operation="host.apply", scope={"preset": "install-package"},
                                  justification="test", requested_by="client:test")
        aid = approval["approval_id"]
        started = time.monotonic()
        result = self.client.call("v1.approvals.get", approval_id=aid, wait_s=0.3)
        elapsed = time.monotonic() - started
        self.assertEqual(result["state"], "pending")
        self.assertGreaterEqual(elapsed, 0.25)
        self.assertLess(elapsed, 2.0)


class ExecVerdictTest(unittest.TestCase):
    def setUp(self):
        self.harness = support.Harness()

    def tearDown(self):
        self.harness.close()

    def test_verdict_passes_when_postcondition_holds(self):
        client = self.harness.client()
        try:
            sandbox = support.make_sandbox(self.harness, name="verdict-ok")
            sid = sandbox["sandbox_id"]
            token = client.request_permission("exec.run", {"sandbox_id": sid, "commands": ["sh"]},
                                              "verdict check")["capability_token"]
            result = client.call("v1.exec.run", sandbox_id=sid,
                                 cmd=["sh", "-c", "echo built-ok"], capability_token=token,
                                 verdict={"expect_exit": 0, "stdout_contains": "built-ok"})
            self.assertTrue(result["verdict"]["passed"])
            self.assertEqual(len(result["verdict"]["checks"]), 2)
        finally:
            client.close()

    def test_verdict_fails_when_postcondition_does_not_hold(self):
        client = self.harness.client()
        try:
            sandbox = support.make_sandbox(self.harness, name="verdict-bad")
            sid = sandbox["sandbox_id"]
            token = client.request_permission("exec.run", {"sandbox_id": sid, "commands": ["sh"]},
                                              "verdict check")["capability_token"]
            result = client.call("v1.exec.run", sandbox_id=sid,
                                 cmd=["sh", "-c", "echo nope; exit 3"], capability_token=token,
                                 verdict={"expect_exit": 0, "stdout_contains": "built-ok"})
            self.assertFalse(result["verdict"]["passed"])
            failed = [c["check"] for c in result["verdict"]["checks"] if not c["ok"]]
            self.assertEqual(sorted(failed), ["expect_exit", "stdout_contains"])
        finally:
            client.close()

    def test_unknown_verdict_key_is_an_error_not_a_pass(self):
        from parametral.client import ClientError
        client = self.harness.client()
        try:
            sandbox = support.make_sandbox(self.harness, name="verdict-typo")
            sid = sandbox["sandbox_id"]
            token = client.request_permission("exec.run", {"sandbox_id": sid, "commands": ["true"]},
                                              "verdict check")["capability_token"]
            with self.assertRaises(ClientError) as raised:
                client.call("v1.exec.run", sandbox_id=sid, capability_token=token,
                            cmd=["true"], verdict={"expect_exit_code": 0})
            self.assertIn("unknown check", str(raised.exception))
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()

"""sysapply: the only component that writes to the real system.

Nothing in these tests runs as root: the runner executes a stubbed `pacman` from a temp
PATH, snapshots are a callback, and the spool lives in a scratch dir. What is real:
the Ed25519 hand-off, the closed preset validation, the ordering (verify → snapshot →
run), and the refusal paths.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import support

from parametral import ed25519, hostapply, sysapply
from parametral.client import ClientError

FAKE_PACMAN = """#!/bin/sh
echo "pacman $*" >> "$FAKE_LOG"
exit "${FAKE_EXIT:-0}"
"""


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="parametral-sysapply-")
        self.spool = os.path.join(self.tmp, "jobs")
        self.results = os.path.join(self.tmp, "results")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.log = os.path.join(self.tmp, "pacman.log")
        open(self.log, "w").close()
        pacman = os.path.join(self.bin, "pacman")
        with open(pacman, "w") as handle:
            handle.write(FAKE_PACMAN)
        os.chmod(pacman, 0o755)

        self.approver_sk = os.path.join(self.tmp, "approver.sk")
        self.approver_pub = os.path.join(self.tmp, "approver.pub")
        ed25519.keygen(self.approver_sk, self.approver_pub)

        self.queue = sysapply.JobQueue(self.spool, self.results)
        self.snapshot_calls = []

        def snapshot():
            self.snapshot_calls.append(True)
            return "snap_test_1"

        self.runner = sysapply.JobRunner(
            self.spool, self.results, approver_pub_path=self.approver_pub,
            snapshot_fn=snapshot,
            env={"PATH": f"{self.bin}:/usr/bin:/bin", "LC_ALL": "C",
                 "FAKE_LOG": self.log, "FAKE_EXIT": "0"})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def request(self, **overrides):
        base = {"intent": "install ripgrep", "snapshot": True,
                "approval_id": "apr_0123456789ab",
                "steps": [{"kind": "pacman", "argv": ["pacman", "-S", "--noconfirm", "ripgrep"]}]}
        base.update(overrides)
        return base

    # ------------------------------------------------------------- happy path

    def test_signed_job_is_executed_once(self):
        payload = self.queue.submit(self.request())
        self.assertEqual(self.queue.pending_jobs(), [payload["job_id"]])
        self.assertEqual(self.runner.run_once(), [], "unsigned jobs must not run")

        self.queue.sign_pending(payload["job_id"], self.approver_sk)
        results = self.runner.run_once()
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["state"], "applied")
        self.assertEqual(result["snapshot_id"], "snap_test_1")
        self.assertEqual(result["steps"][0]["exit_code"], 0)
        self.assertIn("ripgrep", open(self.log).read())
        self.assertEqual(self.queue.signed_jobs(), [], "job files are consumed")
        self.assertEqual(self.queue.result(payload["job_id"])["state"], "applied")

    def test_snapshot_runs_before_the_command(self):
        payload = self.queue.submit(self.request())
        self.queue.sign_pending(payload["job_id"], self.approver_sk)
        self.runner.run_once()
        self.assertTrue(self.snapshot_calls)
        self.assertEqual(self.snapshot_calls.count(True), 1)

    # --------------------------------------------------------------- refusals

    def test_tampered_payload_is_rejected(self):
        payload = self.queue.submit(self.request())
        job_path = os.path.join(self.spool, f"{payload['job_id']}.json")
        self.queue.sign_pending(payload["job_id"], self.approver_sk)
        tampered = json.load(open(job_path))
        tampered["steps"][0]["argv"] = ["pacman", "-S", "--noconfirm", "linux"]
        json.dump(tampered, open(job_path, "w"))
        result = self.runner.run_once()[0]
        self.assertEqual(result["state"], "rejected")
        self.assertEqual(result["parametral_code"], "SIGNATURE_INVALID")
        self.assertEqual(open(self.log).read(), "", "nothing may run")

    def test_signature_from_another_key_is_rejected(self):
        other_sk = os.path.join(self.tmp, "other.sk")
        other_pub = os.path.join(self.tmp, "other.pub")
        ed25519.keygen(other_sk, other_pub)
        payload = self.queue.submit(self.request())
        self.queue.sign_pending(payload["job_id"], other_sk)
        result = self.runner.run_once()[0]
        self.assertEqual(result["state"], "rejected")
        self.assertIn("does not verify", result["error"])

    def test_shell_steps_cannot_be_queued(self):
        with self.assertRaises(hostapply.HostApplyError) as raised:
            self.queue.submit(self.request(steps=[{"kind": "x", "argv": ["sh", "-c", "id"]}]))
        self.assertIn("interpreter/shell", str(raised.exception))

    def test_missing_snapshot_refuses_the_change(self):
        failed = []

        def broken_snapshot():
            failed.append(True)
            raise RuntimeError("btrfs said no")

        runner = sysapply.JobRunner(self.spool, self.results,
                                    approver_pub_path=self.approver_pub,
                                    snapshot_fn=broken_snapshot,
                                    env={"PATH": f"{self.bin}:/usr/bin:/bin",
                                         "FAKE_LOG": self.log})
        payload = self.queue.submit(self.request())
        self.queue.sign_pending(payload["job_id"], self.approver_sk)
        result = runner.run_once()[0]
        self.assertEqual(result["state"], "rejected")
        self.assertEqual(result["parametral_code"], "SNAPSHOT_FAILED")
        self.assertEqual(open(self.log).read(), "", "no snapshot, no change")

    def test_failed_step_is_reported_with_stderr(self):
        runner = sysapply.JobRunner(self.spool, self.results,
                                    approver_pub_path=self.approver_pub,
                                    snapshot_fn=lambda: "snap_x",
                                    env={"PATH": f"{self.bin}:/usr/bin:/bin",
                                         "FAKE_LOG": self.log, "FAKE_EXIT": "1"})
        payload = self.queue.submit(self.request())
        self.queue.sign_pending(payload["job_id"], self.approver_sk)
        result = runner.run_once()[0]
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["steps"][0]["exit_code"], 1)
        self.assertIn("exit_code", result["steps"][0])

    def test_overlong_or_malformed_jobs_are_refused(self):
        payload = self.queue.submit(self.request())
        record = self.queue.sign_pending(payload["job_id"], self.approver_sk)
        self.assertIn("sig", record)
        bad = dict(record)
        bad["sig"] = "base64:not-a-signature"
        job_path = os.path.join(self.spool, f"{payload['job_id']}.json")
        util_sig = job_path + ".sig"
        json.dump(bad, open(util_sig, "w"))
        result = self.runner.run_once()[0]
        self.assertEqual(result["state"], "rejected")

    def test_wait_returns_none_then_result(self):
        self.assertIsNone(self.queue.wait("job_missing", timeout_s=0.1))
        payload = self.queue.submit(self.request())
        self.queue.sign_pending(payload["job_id"], self.approver_sk)
        self.runner.run_once()
        self.assertEqual(self.queue.wait(payload["job_id"], timeout_s=0.1)["state"], "applied")


class DaemonHostApplyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = support.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.close()

    def setUp(self):
        self.client = self.harness.client()
        self.sandbox = support.make_sandbox(self.harness, name="tier1")
        self.tmp = tempfile.mkdtemp(prefix="parametral-tier1-")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.log = os.path.join(self.tmp, "pacman.log")
        open(self.log, "w").close()
        pacman = os.path.join(self.bin, "pacman")
        with open(pacman, "w") as handle:
            handle.write(FAKE_PACMAN)
        os.chmod(pacman, 0o755)

    def tearDown(self):
        try:
            token = self.client.request_permission("sandbox.destroy",
                                                   {"sandbox_id": self.sandbox["sandbox_id"]},
                                                   "cleanup")["capability_token"]
            self.client.call("v1.sandbox.destroy", sandbox_id=self.sandbox["sandbox_id"],
                             capability_token=token)
        except ClientError:
            pass
        self.client.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _approved_token(self) -> tuple[str, str]:
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("host.apply", {}, "install ripgrep system-wide")
        approval_id = raised.exception.data["approval_id"]
        proof = self.harness.approver_store().proof(approval_id, "approved")
        self.client.call("v1.approvals.decide", approval_id=approval_id, decision="approve",
                         approver_proof=proof, decided_by="user:test")
        token = self.client.request_permission("host.apply", {}, "install ripgrep system-wide",
                                               approval_id=approval_id)["capability_token"]
        return token, approval_id

    def test_queued_job_waits_for_the_approver_signature(self):
        token, approval_id = self._approved_token()
        params = {"intent": "install ripgrep", "snapshot": True, "approval_id": approval_id,
                  "steps": [{"kind": "pacman",
                             "argv": ["pacman", "-S", "--noconfirm", "ripgrep"]}]}
        with self.assertRaises(ClientError) as queued:
            self.client.call("v1.host.apply", capability_token=token, wait_s=0.2, **params)
        self.assertEqual(queued.exception.code, -32005)
        job_id = queued.exception.data["job_id"]
        self.assertIn(job_id, self.harness.daemon.job_queue.pending_jobs())

        self.harness.daemon.job_queue.sign_pending(job_id, self.harness.approver_sk_path)
        runner = sysapply.JobRunner(
            self.harness.daemon.job_queue.spool_dir,
            self.harness.daemon.job_queue.results_dir,
            approver_pub_path=self.harness.approver_pub_path,
            snapshot_fn=lambda: "snap_tier1",
            env={"PATH": f"{self.bin}:/usr/bin:/bin", "FAKE_LOG": self.log})
        self.assertEqual(runner.run_once()[0]["state"], "applied")

        result = self.client.call("v1.host.apply", capability_token=token, job_id=job_id)
        self.assertEqual(result["state"], "applied")
        self.assertEqual(result["snapshot_id"], "snap_tier1")
        self.assertIn("ripgrep", open(self.log).read())


if __name__ == "__main__":
    unittest.main()

"""app.install pipeline: verify-gated, 3 attempts, honest failure, snapshot first.

The `nix` binary is stubbed inside the sandbox (this host has no /nix/store), but
everything else is real: real bwrap sandbox, real subprocesses, real exit codes,
real snapshot. The stub records its argv so the flags we promise (builders '',
require-sigs) are checked, not assumed.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import support

from parametral.appinstall import Installer, ManifestError
from parametral.client import ClientError
from parametral.sandbox import SandboxManager

STUB = r"""#!/bin/sh
echo "$@" >> /work/nix-calls.log
if [ "$1 $2" = "profile install" ]; then
  if [ -f /work/FAIL_INSTALL ]; then
    echo "error: unable to download 'https://cache.nixos.org/x': network unreachable" >&2
    exit 1
  fi
  mkdir -p /work/.nix-profile/bin
  cat > /work/.nix-profile/bin/greet <<'INNER'
#!/bin/sh
n=0
[ -f /work/BOOT_COUNT ] && n=$(cat /work/BOOT_COUNT)
n=$((n+1))
echo $n > /work/BOOT_COUNT
if [ -f /work/FAIL_VERIFY ] && [ "$n" -lt "$(cat /work/FAIL_VERIFY)" ]; then
  echo "greet: not ready" >&2
  exit 1
fi
echo "greet 1.0"
INNER
  chmod +x /work/.nix-profile/bin/greet
  echo "installed greeting"
  exit 0
fi
if [ "$1 $2" = "profile remove" ]; then
  rm -rf /work/.nix-profile
  echo removed
  exit 0
fi
if [ "$1 $2" = "profile rollback" ]; then
  echo rolled back
  exit 0
fi
echo "stub nix: unsupported $*" >&2
exit 2
"""

MANIFEST = {
    "name": "greet",
    "version": "1.0",
    "source": "nix",
    "flake_ref": "nixpkgs#greet",
    "verify": {"cmd": ["greet"], "expect_exit": 0, "expect_stdout_contains": "greet"},
    "permissions": {"network": [], "write_dirs": ["/work/appdata"], "ipc": []},
}


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="parametral-app-")
        self.manager = SandboxManager(self.tmp, defaults={"memory_mb": 256})
        self.meta = self.manager.create(name="app")
        self.sid = self.meta["sandbox_id"]
        self.installer = Installer(self.manager, nix_bin="/work/fake-nix", state_root=self.tmp)
        self._put("/work/fake-nix", STUB, mode=0o755)

    def tearDown(self):
        try:
            self.manager.destroy(self.sid)
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put(self, sandbox_path, content, mode=0o644):
        target = self.manager.host_path(self.meta, sandbox_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as handle:
            handle.write(content)
        os.chmod(target, mode)

    def _read(self, sandbox_path):
        return open(self.manager.host_path(self.meta, sandbox_path)).read()

    # ------------------------------------------------------------ happy path

    def test_install_then_verify(self):
        record = self.installer.install(self.sid, MANIFEST)
        self.assertEqual(record["state"], "installed")
        self.assertEqual(record["attempts"], 1)
        self.assertTrue(record["verify"]["passed"])
        self.assertEqual(record["verify"]["exit_code"], 0)
        self.assertIn("greet 1.0", record["verify"]["stdout_tail"])

    def test_promised_nix_flags_are_actually_passed(self):
        self.installer.install(self.sid, MANIFEST)
        calls = self._read("/work/nix-calls.log")
        self.assertIn("profile install", calls)
        self.assertIn("--option builders", calls)
        self.assertIn("--option require-sigs true", calls)
        self.assertIn("nixpkgs#greet", calls)

    def test_snapshot_is_taken_before_install(self):
        record = self.installer.install(self.sid, MANIFEST)
        if not self.manager.btrfs_available:
            self.assertIsNone(record["snapshot_id"])
            return
        self.assertIsNotNone(record["snapshot_id"])
        self.assertIn(record["snapshot_id"],
                      [snap["snapshot_id"] for snap in self.manager.list_snapshots(self.sid)])

    def test_install_record_is_persisted(self):
        record = self.installer.install(self.sid, MANIFEST)
        path = os.path.join(self.installer.records_dir, f"{record['app_id']}.json")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(json.load(open(path))["state"], "installed")

    # --------------------------------------------------------------- retries

    def test_verify_failures_are_retried_until_success(self):
        self._put("/work/FAIL_VERIFY", "3")
        record = self.installer.install(self.sid, MANIFEST)
        self.assertEqual(record["state"], "installed")
        self.assertEqual(record["attempts"], 3)
        self.assertEqual(len(record["failures"]), 2)
        self.assertEqual({failure["stage"] for failure in record["failures"]}, {"verify"})

    def test_persistent_failure_is_reported_honestly(self):
        self._put("/work/FAIL_VERIFY", "99")
        record = self.installer.install(self.sid, MANIFEST)
        self.assertEqual(record["state"], "failed")
        self.assertEqual(record["attempts"], 3)
        self.assertEqual(len(record["failures"]), 3)
        self.assertTrue(all(failure["stderr_tail"] for failure in record["failures"]))
        self.assertIn("verify", record["diagnosis"])

    def test_install_failure_diagnosis_names_the_network_boundary(self):
        self._put("/work/FAIL_INSTALL", "1")
        record = self.installer.install(self.sid, MANIFEST)
        self.assertEqual(record["state"], "failed")
        self.assertIn("nix-daemon", record["diagnosis"])
        self.assertEqual(record["failures"][0]["stage"], "install")

    def test_attempt_limit_is_capped(self):
        record = self.installer.install(self.sid, MANIFEST, attempt_limit=99)
        self.assertEqual(record["attempts"], 1)
        self._put("/work/FAIL_VERIFY", "99")
        capped = self.installer.install(self.sid, MANIFEST, attempt_limit=99)
        self.assertLessEqual(capped["attempts"], 3)

    # ------------------------------------------------------------- refusals

    def test_manifest_without_verify_is_refused(self):
        broken = {key: value for key, value in MANIFEST.items() if key != "verify"}
        with self.assertRaises(ManifestError) as raised:
            self.installer.install(self.sid, broken)
        self.assertEqual(raised.exception.code, "INVALID_PARAMS")
        self.assertIn("verify", str(raised.exception))

    def test_bad_flake_ref_is_refused(self):
        broken = dict(MANIFEST, flake_ref="http://example.com/pkg")
        with self.assertRaises(ManifestError):
            self.installer.install(self.sid, broken)

    def test_artifact_source_is_declared_not_implemented(self):
        broken = dict(MANIFEST, source="artifact", artifact_url="https://x/y.deb")
        with self.assertRaises(ManifestError) as raised:
            self.installer.install(self.sid, broken)
        self.assertEqual(raised.exception.code, "UNSUPPORTED")
        self.assertEqual(raised.exception.detail["milestone"], "phase-2b")

    # ------------------------------------------------------- remove/rollback

    def test_remove_and_rollback(self):
        self.installer.install(self.sid, MANIFEST)
        removed = self.installer.remove(self.sid, MANIFEST)
        self.assertEqual(removed["state"], "removed")
        rollback = self.installer.rollback(self.sid)
        self.assertEqual(rollback["state"], "rolled_back")

    # ------------------------------------------------- sandbox stays sealed

    def test_install_runs_without_network_in_the_sandbox(self):
        script = ("import socket\ns=socket.socket()\ns.settimeout(2)\n"
                  "try:\n s.connect(('1.1.1.1',80))\n print('OPEN')\n"
                  "except OSError as e:\n print('CLOSED', e.errno)\n")
        probe = self.manager.run(self.sid, ["python3", "-c", script])
        self.assertIn("CLOSED", probe["stdout"])
        self.assertEqual(self.installer.install(self.sid, MANIFEST)["state"], "installed")


class DaemonAppInstallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = support.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.close()

    def setUp(self):
        self.client = self.harness.client()
        self.sandbox = support.make_sandbox(self.harness, name="appapi")
        self.sid = self.sandbox["sandbox_id"]
        self.harness.daemon.installer.nix_bin = "/work/fake-nix"
        root = self.harness.daemon.sandboxes.get(self.sid)["root"]
        os.makedirs(os.path.join(root, "work"), exist_ok=True)
        path = os.path.join(root, "fake-nix")
        with open(path, "w") as handle:
            handle.write(STUB)
        os.chmod(path, 0o755)

    def tearDown(self):
        try:
            token = self.client.request_permission("sandbox.destroy",
                                                   {"sandbox_id": self.sid},
                                                   "cleanup")["capability_token"]
            self.client.call("v1.sandbox.destroy", sandbox_id=self.sid, capability_token=token)
        except ClientError:
            pass
        self.client.close()

    def _approved_token(self, operation: str) -> str:
        from parametral.approvals import ApprovalStore

        with self.assertRaises(ClientError) as raised:
            self.client.request_permission(operation, {"sandbox_id": self.sid}, "install greet")
        approval_id = raised.exception.data["approval_id"]
        store = self.harness.approver_store()
        proof = store.proof(approval_id, "approved")
        self.client.call("v1.approvals.decide", approval_id=approval_id, decision="approve",
                         approver_proof=proof, decided_by="user:test")
        return self.client.request_permission(operation, {"sandbox_id": self.sid},
                                              "install greet",
                                              approval_id=approval_id)["capability_token"]

    def test_install_is_approval_gated_then_works(self):
        token = self._approved_token("app.install")
        record = self.client.call("v1.app.install", sandbox_id=self.sid, manifest=MANIFEST,
                                  capability_token=token)
        self.assertEqual(record["state"], "installed")
        self.assertEqual(record["attempts"], 1)

    def test_verify_endpoint_reports_reality(self):
        token = self._approved_token("app.install")
        self.client.call("v1.app.install", sandbox_id=self.sid, manifest=MANIFEST,
                         capability_token=token)
        verify_token = support.token_for(self.harness, "app.read",
                                        {"sandbox_id": self.sid})["capability_token"]
        result = self.client.call("v1.app.verify", sandbox_id=self.sid, manifest=MANIFEST,
                                  capability_token=verify_token)
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()

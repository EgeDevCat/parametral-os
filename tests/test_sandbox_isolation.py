"""Sandbox isolation with real namespaces: the claims are checked from inside."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support  # noqa: F401

from parametral.proof import run_proof
from parametral.sandbox import Limits, SandboxError, SandboxManager


class IsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="parametral-sbx-")
        self.manager = SandboxManager(self.tmp, node_id="local",
                                      defaults={"cpu_cores": 0.5, "memory_mb": 256,
                                                "pids": 64, "disk_mb": 32})
        self.meta = self.manager.create(name="isolation")

    def tearDown(self):
        try:
            self.manager.destroy(self.meta["sandbox_id"], purge=True)
        except SandboxError:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- proof

    def test_full_isolation_proof_passes(self):
        passed, report, raw = run_proof()
        self.assertTrue(passed, report)
        self.assertIn("RESULT: PASS", report)
        checks = raw["checks"]
        self.assertTrue(checks["network_closed"]["ok"])
        self.assertTrue(checks["mount_blocked"]["ok"])
        self.assertTrue(checks["ptrace_blocked"]["ok"])
        self.assertTrue(checks["home_only_sandbox_user"]["ok"])
        self.assertTrue(checks["no_capabilities"]["ok"])
        self.assertEqual(checks["not_root"]["detail"], "uid=%d" % os.getuid())

    def test_hello_world_runs(self):
        result = self.manager.run(self.meta["sandbox_id"], ["echo", "hello world"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "hello world\n")
        self.assertFalse(result["timed_out"])

    def test_network_is_unreachable_from_inside(self):
        script = ("import socket\n"
                  "s = socket.socket()\n"
                  "s.settimeout(2)\n"
                  "try:\n"
                  "    s.connect(('1.1.1.1', 80))\n"
                  "    print('OPEN')\n"
                  "except OSError as exc:\n"
                  "    print('CLOSED', exc.errno)\n")
        result = self.manager.run(self.meta["sandbox_id"], ["python3", "-c", script])
        self.assertIn("CLOSED", result["stdout"])
        self.assertNotIn("OPEN", result["stdout"])

    def test_host_home_is_not_visible(self):
        home = os.path.expanduser("~")
        result = self.manager.run(self.meta["sandbox_id"],
                                  ["sh", "-c", f"ls {home} 2>&1; echo rc=$?"])
        self.assertIn("No such file", result["stdout"])

    # ------------------------------------------------------------ path rules

    def test_path_outside_scope_is_refused(self):
        for path in ("/etc/passwd", "/root", "/", "/home", "/proc/self/environ"):
            with self.assertRaises(SandboxError) as raised:
                self.manager.host_path(self.meta, path)
            self.assertEqual(raised.exception.code, "LIMIT_EXCEEDED")
            self.assertEqual(raised.exception.detail["severity"], "security")

    def test_traversal_is_refused(self):
        with self.assertRaises(SandboxError):
            self.manager.host_path(self.meta, "/work/../../etc/passwd")

    def test_symlink_escape_is_refused(self):
        os.symlink("/etc", os.path.join(self.meta["root"], "escape"))
        with self.assertRaises(SandboxError) as raised:
            self.manager.host_path(self.meta, "/work/escape/passwd")
        self.assertEqual(raised.exception.code, "LIMIT_EXCEEDED")

    def test_valid_paths_resolve_inside_sandbox(self):
        path = self.manager.host_path(self.meta, "/work/deep/file.txt")
        self.assertTrue(path.startswith(self.meta["root"]))
        home_path = self.manager.host_path(self.meta, "/home/user/x")
        self.assertTrue(home_path.startswith(self.meta["home"]))

    # -------------------------------------------------------------- limits

    def test_cgroup_limits_are_written(self):
        cgroup, note = self.manager._cgroup_create(self.meta)
        try:
            if cgroup is None:
                self.skipTest(f"no delegated cgroup on this host: {note}")
            limits = Limits.from_dict(self.meta["limits"])
            with open(os.path.join(cgroup, "memory.max")) as handle:
                memory = int(handle.read().strip())
            with open(os.path.join(cgroup, "pids.max")) as handle:
                pids = int(handle.read().strip())
            with open(os.path.join(cgroup, "cpu.max")) as handle:
                cpu = handle.read().strip()
            self.assertLessEqual(memory, limits.memory_mb * 1024 * 1024)
            self.assertEqual(pids, limits.pids)
            self.assertEqual(cpu, f"{int(limits.cpu_cores * 100000)} 100000")
        finally:
            self.manager._cgroup_remove(self.meta["sandbox_id"])

    def test_timeout_kills_the_sandbox_process(self):
        result = self.manager.run(self.meta["sandbox_id"], ["sleep", "30"], timeout_s=1)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["exit_code"], 124)
        self.assertLess(result["duration_ms"], 8000)

    def test_output_is_capped(self):
        result = self.manager.run(self.meta["sandbox_id"],
                                  ["sh", "-c", "for i in $(seq 1 5000); do echo line-$i; done"],
                                  max_output_bytes=4096)
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["stdout"]), 4096)

    def test_disk_limit_is_a_rlimit(self):
        result = self.manager.run(
            self.meta["sandbox_id"],
            ["sh", "-c", "dd if=/dev/zero of=/work/big bs=1M count=64 2>&1; echo rc=$?"])
        self.assertIn("rc=1", result["stdout"])

    # ------------------------------------------------------------- lifecycle

    def test_destroy_purges_everything(self):
        sandbox_id = self.meta["sandbox_id"]
        self.manager.destroy(sandbox_id, purge=True)
        self.assertFalse(os.path.exists(self.meta["root"]))
        with self.assertRaises(SandboxError):
            self.manager.get(sandbox_id)

    def test_duplicate_name_is_a_conflict(self):
        with self.assertRaises(SandboxError) as raised:
            self.manager.create(name="isolation")
        self.assertEqual(raised.exception.code, "CONFLICT")

    def test_microvm_profile_is_explicitly_unsupported(self):
        with self.assertRaises(SandboxError) as raised:
            self.manager.create(name="vm", profile="microvm")
        self.assertEqual(raised.exception.code, "UNSUPPORTED")
        self.assertEqual(raised.exception.detail["milestone"], "phase-5")

    def test_environment_is_cleared(self):
        os.environ["PARAMETRAL_TEST_LEAK"] = "host-secret"
        try:
            result = self.manager.run(self.meta["sandbox_id"], ["sh", "-c", "env"])
        finally:
            os.environ.pop("PARAMETRAL_TEST_LEAK", None)
        self.assertNotIn("host-secret", result["stdout"])
        self.assertIn("HOME=/home/user", result["stdout"])
        self.assertIn("PATH=/usr/local/bin:/usr/bin:/bin", result["stdout"])


if __name__ == "__main__":
    unittest.main()

"""Deterministic verifier: patch -> build -> test, repeat and quarantine flaky."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from parametral.verifier import Task, Verifier, VerifyError

PATCH = """--- a/impl.py
+++ b/impl.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 2
"""


class VerifierTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "impl.py").write_text("VALUE = 1\n")
        (self.repo / "check.py").write_text(
            "from impl import VALUE\n"
            "raise SystemExit(0 if VALUE == 2 else 1)\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def task(self, **overrides) -> Task:
        data = {
            "task_id": "unit-1",
            "repo": str(self.repo),
            "patch": PATCH,
            "build": [sys.executable, "-c", "import impl"],
            "test": [sys.executable, "check.py"],
            "repeat": 2,
            "sandbox": "none",
        }
        data.update(overrides)
        return Task.from_dict(data)

    def test_patch_build_test_passes_twice(self):
        result = Verifier().run(self.task())
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["deterministic"])
        self.assertEqual(result["repeat"], 2)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertFalse(result["network_isolated"])
        self.assertEqual(len(result["patch_sha256"]), 64)

    def test_without_patch_the_hidden_test_fails(self):
        result = Verifier().run(self.task(patch=None))
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["passed"])

    def test_mixed_results_are_flaky_and_not_quarantined_as_pass(self):
        test = [
            sys.executable, "-c",
            "from pathlib import Path\n"
            "p = Path('count.txt')\n"
            "n = int(p.read_text()) if p.exists() else 0\n"
            "p.write_text(str(n + 1))\n"
            "raise SystemExit(0 if n % 2 == 0 else 1)\n",
        ]
        result = Verifier().run(self.task(patch=None, test=test, repeat=2))
        self.assertEqual(result["status"], "flaky", result)
        self.assertFalse(result["deterministic"])
        self.assertFalse(result["passed"])

    def test_toolchain_pin_is_checked(self):
        task = self.task(toolchain={"python3": "0" * 64})
        with self.assertRaises(VerifyError) as ctx:
            Verifier().run(task)
        self.assertEqual(ctx.exception.code, "TOOLCHAIN_MISMATCH")

    def test_bad_patch_is_an_error(self):
        with self.assertRaises(VerifyError) as ctx:
            Verifier().run(self.task(patch="this is not a patch\n"))
        self.assertEqual(ctx.exception.code, "PATCH_FAILED")

    def test_commands_must_be_argv_lists(self):
        with self.assertRaises(VerifyError):
            self.task(build="make -j4")

    def test_missing_test_command_is_reported_as_failure(self):
        result = Verifier().run(self.task(test=[]))
        self.assertEqual(result["status"], "failed")
        self.assertIn("no test command", result["attempts"][0]["error"])

    @unittest.skipUnless(shutil.which("bwrap"), "bubblewrap not installed")
    def test_bwrap_runs_with_network_isolated(self):
        result = Verifier().run(self.task(sandbox="bwrap", repeat=1))
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["network_isolated"])


if __name__ == "__main__":
    unittest.main()

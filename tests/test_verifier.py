"""Deterministic verifier: patch -> build -> test, repeat and quarantine flaky."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
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

    def test_patch_build_test_passes_once(self):
        result = Verifier().run(self.task())
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["verdict"], "passed")
        self.assertTrue(result["deterministic"])
        self.assertFalse(result["flaky"])
        self.assertEqual(result["repeat"], 2)
        self.assertEqual(len(result["attempts"]), 1,
                         "a passing task must not be repeated")
        self.assertFalse(result["network_isolated"])
        for key in ("task_id", "verdict", "exit_code", "build_log_sha256",
                    "test_log_sha256", "patch_sha256", "toolchain_sha256",
                    "tests_sha256", "repo_commit", "timeout_hit", "max_rss_kb",
                    "hash_algo", "duration_ms", "flaky"):
            self.assertIn(key, result)
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
            "raise SystemExit(0 if n % 2 == 1 else 1)\n",
        ]
        result = Verifier().run(self.task(patch=None, test=test, repeat=2))
        self.assertEqual(result["status"], "flaky", result)
        self.assertTrue(result["flaky"])
        self.assertFalse(result["deterministic"])
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["attempts"]), 2)

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

    def test_test_mutation_is_refused_in_code(self):
        patch = """--- a/check.py
+++ b/check.py
@@ -1,2 +1,2 @@
 from impl import VALUE
-raise SystemExit(0 if VALUE == 2 else 1)
+raise SystemExit(0)
"""
        with self.assertRaises(VerifyError) as ctx:
            Verifier().run(self.task(patch=patch, test_files=["check.py"]))
        self.assertEqual(ctx.exception.code, "TEST_MUTATION")

    def test_batch_mode_emits_one_json_line_per_task_and_exits_zero(self):
        tasks = self.root / "tasks.jsonl"
        good = {
            "task_id": "batch-good", "repo": str(self.repo), "patch": PATCH,
            "build": [sys.executable, "-c", "import impl"],
            "test": [sys.executable, "check.py"], "repeat": 2, "sandbox": "none",
        }
        bad = dict(good, task_id="batch-bad", patch=None)
        tasks.write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n")
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent
                                 / "bin" / "parametral-verify"),
             "--batch", str(tasks)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual([line["task_id"] for line in lines], ["batch-good", "batch-bad"])
        self.assertEqual([line["verdict"] for line in lines], ["passed", "failed"])


if __name__ == "__main__":
    unittest.main()

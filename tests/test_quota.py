"""qgroup quota layer: exact argv, honest failure, no pretending the limit is on."""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import unittest

import support  # noqa: F401

from parametral import quota

STUB = r'''#!/usr/bin/env python3
import os, sys

args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")

if args[:2] == ["quota", "enable"]:
    sys.exit(int(os.environ.get("STUB_ENABLE_EXIT", "0")))
if args[:2] == ["qgroup", "limit"]:
    sys.exit(int(os.environ.get("STUB_LIMIT_EXIT", "0")))
if args[:2] == ["qgroup", "show"]:
    print("qgroupid  rfer   excl   max_rfer")
    print("0/256     1.2MiB 1.0MiB 512.00MiB")
    sys.exit(0)
sys.exit(2)
'''


class QuotaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="parametral-quota-")
        self.stub = os.path.join(self.tmp, "btrfs")
        with open(self.stub, "w") as handle:
            handle.write(STUB)
        os.chmod(self.stub, 0o755)
        self.log = os.path.join(self.tmp, "calls.log")
        open(self.log, "w").close()
        os.environ["STUB_LOG"] = self.log
        self.subvol = os.path.join(self.tmp, "root")
        os.makedirs(self.subvol)

    def tearDown(self):
        for key in ("STUB_LOG", "STUB_LIMIT_EXIT", "STUB_ENABLE_EXIT"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls(self):
        return open(self.log).read().splitlines()

    def test_argv_shape_is_exact(self):
        manager = quota.QuotaManager(btrfs_bin=self.stub)
        self.assertEqual(manager.argv_limit(self.subvol, 256),
                         [self.stub, "qgroup", "limit", "256M", self.subvol])
        self.assertEqual(manager.argv_enable("/"), [self.stub, "quota", "enable", "/"])
        self.assertEqual(manager.argv_show(self.subvol), [self.stub, "qgroup", "show", self.subvol])

    def test_limit_is_applied_and_runs_the_expected_command(self):
        manager = quota.QuotaManager(btrfs_bin=self.stub)
        result = manager.limit(self.subvol, 256)
        self.assertTrue(result["limited"])
        self.assertIn(f"qgroup limit 256M {self.subvol}", self.calls())

    def test_failed_limit_raises_with_stderr(self):
        os.environ["STUB_LIMIT_EXIT"] = "1"
        manager = quota.QuotaManager(btrfs_bin=self.stub)
        with self.assertRaises(quota.QuotaError) as raised:
            manager.limit(self.subvol, 256)
        self.assertEqual(raised.exception.code, "QUOTA_UNAVAILABLE")
        self.assertIn("argv", raised.exception.detail)

    def test_bad_size_is_refused_before_running_anything(self):
        manager = quota.QuotaManager(btrfs_bin=self.stub)
        for size in (0, -5, "many"):
            with self.assertRaises(quota.QuotaError):
                manager.argv_limit(self.subvol, size)  # type: ignore[arg-type]
        self.assertEqual(self.calls(), [])

    def test_best_effort_returns_a_note_instead_of_hiding_the_failure(self):
        os.environ["STUB_LIMIT_EXIT"] = "1"
        note = quota.apply_best_effort(quota.QuotaManager(btrfs_bin=self.stub), self.subvol, 256)
        self.assertIsNotNone(note)
        self.assertIn("not applied", note)
        os.environ["STUB_LIMIT_EXIT"] = "0"
        self.assertIsNone(
            quota.apply_best_effort(quota.QuotaManager(btrfs_bin=self.stub), self.subvol, 256))

    def test_dry_run_writes_no_command_output(self):
        manager = quota.QuotaManager(btrfs_bin=self.stub, dry_run=True)
        result = manager.limit(self.subvol, 128)
        self.assertTrue(result["limited"])
        self.assertEqual(self.calls(), [])

    def test_usage_parses_show_output(self):
        manager = quota.QuotaManager(btrfs_bin=self.stub)
        usage = manager.usage(self.subvol)
        self.assertIn("qgroupid", usage["raw"])


class SandboxQuotaNoteTest(unittest.TestCase):
    def test_sandbox_records_when_the_quota_could_not_be_applied(self):
        from parametral.sandbox import SandboxManager

        tmp = tempfile.mkdtemp(prefix="parametral-sbxquota-")
        try:
            manager = SandboxManager(tmp)
            meta = manager.create(name="quota")
            self.assertIn("quota_note", meta)
            # on a host without qgroup privileges the note explains it; when it did work,
            # the key is absent from the notes and that is equally fine
            if meta["quota_note"]:
                self.assertIn("qgroup", meta["quota_note"])
            manager.destroy(meta["sandbox_id"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

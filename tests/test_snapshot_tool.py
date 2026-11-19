"""parametral-snapshot: the rollback safety net, tested without root or btrfs.

`btrfs` is replaced by a stub that records argv and materialises directories, the root
tree is redirected to a scratch dir. The tool's own logic (naming, metadata,
boot entry, promote ordering, prune arithmetic, refusal paths) runs for real.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "src", "tools", "parametral-snapshot")

STUB = r'''#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")

if args[:2] == ["subvolume", "show"]:
    sys.exit(0 if os.path.isdir(args[2]) else 1)

if args[:2] == ["subvolume", "snapshot"]:
    rest = [a for a in args[2:] if a != "-r"]
    src, dst = rest[0], rest[1]
    if not os.path.isdir(src):
        sys.stderr.write("stub: source missing %s\n" % src)
        sys.exit(1)
    os.makedirs(dst, exist_ok=True)
    sys.exit(0)

if args[:2] == ["subvolume", "delete"]:
    target = args[2]
    if os.getenv("STUB_FAIL_DELETE") == "1":
        sys.exit(1)
    shutil_target = target
    os.system("rm -rf %s" % shutil_target) if os.getenv("STUB_USE_RM") == "1" else None
    try:
        os.rmdir(shutil_target)
    except OSError:
        pass
    sys.exit(0)

sys.stderr.write("stub: unsupported %s\n" % args)
sys.exit(2)
'''


class SnapshotToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="parametral-snap-tool-")
        self.root = os.path.join(self.tmp, "tree")
        self.snap_dir = os.path.join(self.tmp, "snapshots")
        self.boot_dir = os.path.join(self.tmp, "boot")
        self.log = os.path.join(self.tmp, "btrfs.log")
        self.stub = os.path.join(self.tmp, "btrfs")
        for path in (os.path.join(self.root, "@"), os.path.join(self.root, "@home")):
            os.makedirs(path)
        os.makedirs(self.snap_dir)
        os.makedirs(os.path.join(self.boot_dir, "loader", "entries"))
        with open(self.stub, "w") as handle:
            handle.write(STUB.replace("shutil_target", "target"))
        os.chmod(self.stub, 0o755)
        open(self.log, "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *args, dry_run=False, extra_env=None):
        env = dict(os.environ)
        env.update({
            "PARAMETRAL_BTRFS": self.stub,
            "PARAMETRAL_SNAP_DIR": self.snap_dir,
            "PARAMETRAL_BOOT_DIR": self.boot_dir,
            "PARAMETRAL_ROOT_PREFIX": self.root,
            "PARAMETRAL_DRY_RUN": "1" if dry_run else "0",
            "PARAMETRAL_DEV": "UUID=1234-abcd",
            "STUB_LOG": self.log,
        })
        env.update(extra_env or {})
        return subprocess.run(["bash", TOOL, *args], capture_output=True, text=True, env=env)

    def calls(self):
        with open(self.log) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    # --------------------------------------------------------------- create

    def test_create_makes_snapshot_with_metadata(self):
        result = self.run_tool("create", "pre-upgrade")
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot_id = result.stdout.strip()
        self.assertRegex(snapshot_id, r"^\d{8}T\d{6}Z_pre-upgrade$")
        path = os.path.join(self.snap_dir, snapshot_id)
        self.assertTrue(os.path.isdir(os.path.join(path, "@")))
        self.assertTrue(os.path.isdir(os.path.join(path, "@home")))
        meta = open(os.path.join(path, ".meta")).read()
        self.assertIn("label=pre-upgrade", meta)
        self.assertIn("kernel=", meta)

    def test_create_is_read_only(self):
        self.run_tool("create", "manual")
        snapshots = [call for call in self.calls() if call[:2] == ["subvolume", "snapshot"]]
        self.assertTrue(snapshots)
        for call in snapshots:
            self.assertIn("-r", call, "snapshots must be read-only")

    def test_list_reports_snapshots(self):
        self.run_tool("create", "alpha")
        listing = self.run_tool("list")
        self.assertEqual(listing.returncode, 0)
        self.assertIn("alpha", listing.stdout)
        self.assertIn("present", listing.stdout)

    # ----------------------------------------------------------- boot entry

    def test_boot_entry_points_at_the_snapshot(self):
        snapshot_id = self.run_tool("create", "bootme").stdout.strip()
        result = self.run_tool("boot-entry", snapshot_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = os.path.join(self.boot_dir, "loader", "entries",
                             f"parametral-snap-{snapshot_id}.conf")
        body = open(entry).read()
        self.assertIn("title   ParametralOS (snapshot", body)
        self.assertIn("root=UUID=1234-abcd", body)
        self.assertIn(f"rootflags=subvol={self.snap_dir.lstrip('/')}/{snapshot_id}/@", body)
        self.assertIn("/vmlinuz-linux", body)

    def test_boot_entry_requires_device(self):
        snapshot_id = self.run_tool("create", "nodev").stdout.strip()
        result = self.run_tool("boot-entry", snapshot_id, extra_env={"PARAMETRAL_DEV": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PARAMETRAL_DEV", result.stderr)

    def test_boot_entry_refuses_unknown_snapshot(self):
        result = self.run_tool("boot-entry", "19990101T000000Z_nope")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no root subvolume", result.stderr)

    # -------------------------------------------------------------- promote

    def test_promote_dry_run_shows_the_swap(self):
        snapshot_id = self.run_tool("create", "promote-me").stdout.strip()
        result = self.run_tool("promote", snapshot_id, dry_run=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY mv", result.stdout)
        self.assertIn("DRY", result.stdout)
        self.assertIn("subvolume snapshot", result.stdout)
        self.assertTrue(os.path.isdir(os.path.join(self.root, "@")),
                        "dry run must not touch the live tree")

    def test_promote_removes_the_snapshot_boot_entry(self):
        snapshot_id = self.run_tool("create", "promote2").stdout.strip()
        self.run_tool("boot-entry", snapshot_id)
        entry = os.path.join(self.boot_dir, "loader", "entries",
                             f"parametral-snap-{snapshot_id}.conf")
        self.assertTrue(os.path.exists(entry))
        self.run_tool("promote", snapshot_id)
        self.assertFalse(os.path.exists(entry))

    # ---------------------------------------------------------------- prune

    def test_prune_keeps_the_newest(self):
        ids = []
        for label in ("one", "two", "three"):
            ids.append(self.run_tool("create", label).stdout.strip())
        result = self.run_tool("prune", "--keep", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        remaining = sorted(os.listdir(self.snap_dir))
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0], ids[-1], "prune must keep the newest snapshot")

    def test_prune_rejects_a_bad_keep(self):
        result = self.run_tool("prune", "--keep", "many")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--keep needs a number", result.stderr)

    # ------------------------------------------------------------- refusals

    def test_refuses_to_promote_into_a_foreign_subvol(self):
        snapshot_id = self.run_tool("create", "x").stdout.strip()
        result = self.run_tool("promote", snapshot_id,
                               extra_env={"PARAMETRAL_ROOT_SUBVOL": "@custom"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing", result.stderr)

    def test_unknown_command(self):
        result = self.run_tool("frobnicate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown command", result.stderr)

    def test_help_is_readable(self):
        result = self.run_tool("help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("parametral-snapshot create", result.stdout)


if __name__ == "__main__":
    unittest.main()

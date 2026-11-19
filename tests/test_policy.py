"""Default-deny is the core claim: prove it at the engine level."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import support  # noqa: F401  (sets sys.path)

from ultraos.policy import OPERATIONS, Policy, PolicyError


class DefaultDenyTest(unittest.TestCase):
    def setUp(self):
        self.policy = Policy(support.POLICY)

    def test_policy_default_is_deny(self):
        limits = self.policy.limits
        self.assertEqual(limits["max_token_ttl_s"], 1800)
        self.assertEqual(json.load(open(support.POLICY))["default"], "deny")

    def test_service_start_is_approval_gated(self):
        decision = self.policy.explain("service.start", {"sandbox_id": "sbx_l_aaaa"})
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)
        self.assertEqual(decision.rule_id, "allow-network-with-approval")

    def test_no_allow_rule_means_deny(self):
        # Not on the deny list, just not on any allow list: default deny applies.
        decision = self.policy.explain("exec.run",
                                       {"sandbox_id": "sbx_l_aaaa", "command": "terraform"})
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.rule_id, "default-deny")

    def test_dangerous_command_denied_even_with_valid_sandbox(self):
        decision = self.policy.explain("exec.run", {"sandbox_id": "sbx_l_aaaa", "command": "curl"})
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.rule_id, "deny-dangerous-commands")

    def test_allowed_command_in_sandbox(self):
        decision = self.policy.explain("exec.run", {"sandbox_id": "sbx_l_aaaa", "command": "git"})
        self.assertEqual(decision.decision, "allow")
        self.assertEqual(decision.rule_id, "allow-sandbox-exec")

    def test_host_paths_are_denied_for_fs_ops(self):
        for path in ("/etc/passwd", "/root/.ssh/id_rsa", "/proc/self/environ", "/boot/vmlinuz"):
            decision = self.policy.explain("fs.read", {"sandbox_id": "sbx_l_aaaa", "paths": [path]})
            self.assertEqual(decision.decision, "deny", path)

    def test_sandbox_paths_are_allowed(self):
        decision = self.policy.explain("fs.write", {"sandbox_id": "sbx_l_aaaa",
                                                    "paths": ["/work/deep/file.txt"]})
        self.assertEqual(decision.decision, "allow")

    def test_host_mounts_must_be_operator_listed(self):
        allowed = self.policy.explain("sandbox.create", {"host_paths": ["/opt/models/llama"]})
        self.assertEqual(allowed.decision, "allow")
        denied = self.policy.explain("sandbox.create", {"host_paths": ["/home/user/.ssh"]})
        self.assertEqual(denied.decision, "deny")
        self.assertEqual(denied.rule_id, "deny-unlisted-host-mounts")

    def test_app_install_requires_human_approval(self):
        decision = self.policy.explain("app.install", {"sandbox_id": "sbx_l_aaaa"})
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_tier0_nix_profile_needs_no_approval(self):
        decision = self.policy.explain("host.nix_profile", {})
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_approval)
        self.assertEqual(decision.rule_id, "allow-host-nix-profile")

    def test_tier1_host_apply_always_needs_approval(self):
        decision = self.policy.explain("host.apply", {})
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)
        self.assertEqual(decision.rule_id, "allow-host-apply")

    def test_stack_is_arch_nix_not_debian(self):
        self.assertTrue(self.policy.explain("exec.run",
                                            {"sandbox_id": "sbx_l_a", "command": "pacman"}).allowed)
        self.assertTrue(self.policy.explain("exec.run",
                                            {"sandbox_id": "sbx_l_a", "command": "nix"}).allowed)
        self.assertEqual(self.policy.explain("exec.run",
                                             {"sandbox_id": "sbx_l_a",
                                              "command": "apt-get"}).decision, "deny")

    def test_snapshot_restore_requires_approval(self):
        decision = self.policy.explain("snapshot.restore", {})
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_ttl_is_capped_by_rule(self):
        self.assertEqual(self.policy.clamp_ttl(99999, 900), 900)
        self.assertEqual(self.policy.clamp_ttl(60, 900), 60)
        self.assertEqual(self.policy.clamp_ttl(99999, None), 1800)

    def test_policy_file_must_be_fail_closed(self):
        base = json.load(open(support.POLICY))
        with tempfile.TemporaryDirectory() as tmp:
            for mutation, message in (
                ({"default": "allow"}, "default"),
                ({"rules": []}, "non-empty"),
            ):
                data = dict(base)
                data.update(mutation)
                path = os.path.join(tmp, "bad.json")
                json.dump(data, open(path, "w"))
                with self.assertRaises(PolicyError) as raised:
                    Policy(path)
                self.assertIn(message, str(raised.exception))

    def test_unknown_operation_in_policy_refuses_to_load(self):
        base = json.load(open(support.POLICY))
        base["rules"] = [{"id": "bad", "effect": "allow", "operations": ["rm-rf-everything"]}]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            json.dump(base, open(path, "w"))
            with self.assertRaises(PolicyError):
                Policy(path)

    def test_every_operation_has_a_decision(self):
        for operation in sorted(OPERATIONS):
            decision = self.policy.explain(operation, {})
            self.assertIn(decision.decision, ("allow", "deny"), operation)


if __name__ == "__main__":
    unittest.main()

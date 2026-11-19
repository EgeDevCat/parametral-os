"""Tier-1 must be a closed operation set, never a generic root executor."""
from __future__ import annotations

import unittest

import support  # noqa: F401

from ultraos import hostapply


def request(*steps, snapshot=True, approval="apr_0123456789ab", intent="install ripgrep"):
    return {"intent": intent, "snapshot": snapshot, "approval_id": approval,
            "steps": [{"kind": "x", "argv": list(step)} for step in steps]}


class AcceptTest(unittest.TestCase):
    def test_reviewed_operations_pass(self):
        cases = [
            request(["pacman", "-S", "--noconfirm", "ripgrep"]),
            request(["pacman", "-Syu", "--noconfirm"]),
            request(["pacman", "-Rns", "--noconfirm", "ripgrep"]),
            request(["nix", "profile", "install", "nixpkgs#ripgrep"]),
            request(["home-manager", "switch"]),
            request(["systemctl", "enable", "podman.socket"]),
            request(["pacman", "-S", "--noconfirm", "ripgrep"],
                    ["systemctl", "enable", "podman.socket"]),
        ]
        for case in cases:
            normalised = hostapply.validate(case)
            self.assertEqual(len(normalised["steps"]), len(case["steps"]))
            self.assertTrue(normalised["steps"][0]["kind"])

    def test_normalised_output_is_explicit(self):
        normalised = hostapply.validate(request(["pacman", "-S", "--noconfirm", "ripgrep"]))
        self.assertEqual(normalised["steps"][0]["kind"], "pacman-install")
        self.assertEqual(normalised["snapshot"], True)
        self.assertEqual(normalised["approval_id"], "apr_0123456789ab")


class RejectTest(unittest.TestCase):
    def assertRejected(self, case, fragment):
        with self.assertRaises(hostapply.HostApplyError) as raised:
            hostapply.validate(case)
        self.assertIn(fragment, str(raised.exception))

    def test_no_shell_step(self):
        self.assertRejected(request(["sh", "-c", "pacman -S ripgrep"]), "interpreter/shell token")

    def test_no_absolute_binary(self):
        self.assertRejected(request(["/usr/bin/pacman", "-S", "ripgrep"]), "absolute paths")

    def test_command_chaining_is_refused(self):
        self.assertRejected(request(["pacman", "-S", "ripgrep;rm"]), "illegal character")

    def test_flags_outside_the_preset_are_refused(self):
        self.assertRejected(request(["pacman", "-S", "--noconfirm", "-U", "x.pkg.tar.zst"]),
                            "bad packages value")

    def test_traversal_in_package_name_is_refused(self):
        self.assertRejected(request(["pacman", "-S", "--noconfirm", "../../etc/passwd"]),
                            "bad packages value")

    def test_unit_must_be_a_service(self):
        self.assertRejected(request(["systemctl", "start", "sshd"]), "bad units value")

    def test_no_arguments_on_a_no_argument_preset(self):
        self.assertRejected(request(["home-manager", "switch", "extra"]), "takes no arguments")

    def test_snapshot_is_mandatory(self):
        self.assertRejected(request(["pacman", "-S", "--noconfirm", "ripgrep"], snapshot=False),
                            "snapshot:true")

    def test_approval_id_is_mandatory(self):
        self.assertRejected(request(["pacman", "-S", "--noconfirm", "ripgrep"], approval=""),
                            "approval_id")
        self.assertRejected(request(["pacman", "-S", "--noconfirm", "ripgrep"], approval="yolo"),
                            "approval_id")

    def test_step_and_argument_limits(self):
        self.assertRejected(request(*([["pacman", "-S", "--noconfirm", "ripgrep"]] * 9)),
                            "at most 8 steps")

    def test_environment_and_interpreter_tokens_are_refused(self):
        for token in ("bash", "env", "sudo", "xargs", "-c"):
            with self.assertRaises(hostapply.HostApplyError):
                hostapply.validate(request(["pacman", "-S", "--noconfirm", token]))

    def test_intent_must_be_a_single_line(self):
        self.assertRejected(request(["pacman", "-S", "--noconfirm", "ripgrep"],
                                    intent="install\nrm -rf /"), "single line")


if __name__ == "__main__":
    unittest.main()

"""The installer's desktop choice must be real, not a menu that changes a label.

These tests do not install packages. They check the parts that decide *what* would be
installed: the dispatcher plan, the wizard's edition list, the separation between bootstrap
and desktop, and the session selector that runs after install.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install"


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), cwd=ROOT, capture_output=True, text=True, env=env, timeout=30,
    )


def plan(edition: str) -> str:
    result = run("bash", str(INSTALL / "74-desktop.sh"), "--plan", edition)
    if result.returncode != 0:
        raise AssertionError(f"plan {edition} failed: {result.stderr}")
    return result.stdout


class DispatcherPlan(unittest.TestCase):
    def test_list_names_both_editions(self):
        result = run("bash", str(INSTALL / "74-desktop.sh"), "--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("hyprland", result.stdout)
        self.assertIn("kde", result.stdout)
        self.assertIn("both", result.stdout)

    def test_kde_plan_is_plasma_and_not_hyprland(self):
        text = plan("kde")
        self.assertIn("session=plasma", text)
        self.assertIn("plasma-meta", text)
        self.assertIn("sddm", text)
        self.assertNotIn("hyprland", text.lower())

    def test_hyprland_plan_is_our_session_and_not_plasma(self):
        text = plan("hyprland")
        self.assertIn("session=parametral", text)
        self.assertIn("hyprland", text)
        self.assertIn("noctalia", text)
        self.assertIn("uwsm", text)
        self.assertNotIn("plasma-meta", text)

    def test_both_plan_contains_both_and_picks_parametral(self):
        text = plan("both")
        self.assertIn("primary-session=parametral", text)
        self.assertIn("[kde]", text)
        self.assertIn("[hyprland]", text)
        self.assertIn("plasma-meta", text)
        self.assertIn("noctalia", text)

    def test_unknown_edition_is_refused(self):
        result = run("bash", str(INSTALL / "74-desktop.sh"), "--plan", "gnome")
        self.assertEqual(result.returncode, 2)

    def test_status_needs_no_root(self):
        result = run("bash", str(INSTALL / "74-desktop.sh"), "--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("installed-sessions:", result.stdout)


class Wizard(unittest.TestCase):
    def test_wizard_lists_desktops_with_ready_state(self):
        result = run(sys.executable, str(INSTALL / "parametral-install"), "--list-desktops")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line.split("\t") for line in result.stdout.splitlines()]
        by_key = {line[0]: line for line in lines if len(line) >= 4}
        self.assertEqual(by_key["hyprland"][3], "ready")
        self.assertEqual(by_key["kde"][3], "ready")
        self.assertEqual(by_key["both"][3], "ready")

    def test_wizard_carries_the_answer_into_the_install(self):
        text = (INSTALL / "parametral-install").read_text()
        self.assertIn("PARAMETRAL_DESKTOP", text)
        self.assertIn('"74-desktop.sh"', text)
        self.assertIn("arch-chroot", text)
        self.assertIn("install_payload", text)


class Separation(unittest.TestCase):
    def test_bootstrap_installs_no_desktop(self):
        text = (INSTALL / "30-bootstrap.sh").read_text()
        self.assertNotIn("plasma-meta", text)
        self.assertNotIn("sddm", text)
        self.assertIn("pacstrap /mnt", text)

    def test_run_all_uses_the_dispatcher(self):
        text = (INSTALL / "run-all.sh").read_text()
        self.assertIn("74-desktop.sh", text)
        self.assertIn("PARAMETRAL_DESKTOP", text)
        self.assertNotIn('bash "$SRC/install/79-hypr.sh"', text)
        self.assertNotIn('bash "$SRC/install/80-noctalia.sh"', text)

    def test_legacy_hypr_entries_are_wrappers(self):
        for name in ("79-hypr.sh", "80-noctalia.sh"):
            text = (INSTALL / name).read_text()
            self.assertIn("desktop/hyprland.sh", text, name)

    def test_hyprland_reads_generated_theme(self):
        variables = (ROOT / "branding" / "hypr" / "variables.lua").read_text()
        environment = (ROOT / "branding" / "hypr" / "environment.lua").read_text()
        self.assertIn('dofile(here .. "theme.lua")', variables)
        self.assertIn("theme.gtk_theme", environment)

    def test_shell_syntax(self):
        scripts = sorted(str(path) for path in INSTALL.glob("*.sh"))
        scripts += sorted(str(path) for path in (INSTALL / "desktop").glob("*.sh"))
        for script in scripts:
            result = run("bash", "-n", script)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")


class VerifyRegressions(unittest.TestCase):
    def test_subvolume_check_accepts_the_findmnt_form(self):
        text = (INSTALL / "70-verify.sh").read_text()
        self.assertIn("subvol=/@", text)
        self.assertNotIn('mount | grep -q "subvol=$s,"', text)

    def test_sudo_check_uses_exit_status_not_english(self):
        text = (INSTALL / "70-verify.sh").read_text()
        self.assertIn("runuser -u ai -- sudo -n true", text)
        self.assertNotIn("grep -qi 'not allowed'", text)
        self.assertIn("set -a", text)

    def test_approver_key_dir_is_checked_and_created_0700(self):
        verify = (INSTALL / "70-verify.sh").read_text()
        users = (INSTALL / "40-users.sh").read_text()
        self.assertIn("/var/lib/parametral/keys", verify)
        self.assertIn("-m 0700 /var/lib/parametral/keys", users)

    def test_bootstrap_generates_the_fallback_initramfs(self):
        text = (INSTALL / "30-bootstrap.sh").read_text()
        self.assertIn("initramfs-linux-fallback.img", text)
        self.assertIn("mkinitcpio -g", text)


class IsoBuild(unittest.TestCase):
    def test_iso_scripts_parse(self):
        for name in ("build.sh", "installer.sh", "live-init.sh"):
            result = run("bash", "-n", str(ROOT / "iso" / name))
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")

    def test_build_keeps_boot_images_and_uses_the_live_launcher(self):
        text = (ROOT / "iso" / "build.sh").read_text()
        self.assertIn("-boot_image any replay", text)
        self.assertIn("-volume_date uuid", text)
        self.assertIn("parametral-installer.sh", text)
        self.assertIn("script=/root/parametral-installer.sh", text)
        self.assertIn("eltorito_img2_uefi.img", text)
        self.assertIn("mcopy", text)
        self.assertIn("::/arch/boot/x86_64/initramfs-linux.img", text)
        self.assertIn("efi_path=--interval:appended_partition_2:all::", text)
        self.assertNotIn("mkarchiso", text)
        self.assertNotIn("sudo", text)

    def test_iso_installer_runs_python_not_bash(self):
        text = (ROOT / "iso" / "installer.sh").read_text()
        self.assertIn('exec python3 "$DIR/parametral/install/parametral-install"', text)
        self.assertNotIn('exec bash "$DIR/parametral/install/parametral-install"', text)

    def test_live_init_has_a_manual_fallback(self):
        text = (ROOT / "iso" / "live-init.sh").read_text()
        self.assertIn("/root/parametral-medium", text)
        self.assertIn("mount -o ro", text)
        self.assertIn("/run/archiso/bootmnt", text)


class SessionSelector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "etc/parametral").mkdir(parents=True)
        (self.root / "usr/share/wayland-sessions").mkdir(parents=True)
        (self.root / "etc/parametral/desktop.conf").write_text(
            "PARAMETRAL_DESKTOP=both\n"
            "PARAMETRAL_APPEARANCE=light\n"
            "PARAMETRAL_PRIMARY_SESSION=parametral\n"
            "PARAMETRAL_SESSIONS=\"plasma parametral\"\n"
        )
        for name, display in (("parametral", "Parametral"), ("plasma", "Plasma")):
            (self.root / f"usr/share/wayland-sessions/{name}.desktop").write_text(
                f"[Desktop Entry]\nName={display}\nExec=/bin/true\n"
            )

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return run(sys.executable, str(ROOT / "bin" / "parametral-desktop"),
                   "--root", str(self.root), *args)

    def test_status_reports_the_selected_edition(self):
        result = self.cli("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("desktop=both", result.stdout)
        self.assertIn("appearance=light", result.stdout)
        self.assertIn("primary-session=parametral", result.stdout)

    def test_list_json_contains_both_sessions(self):
        result = self.cli("list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"parametral"', result.stdout)
        self.assertIn('"plasma"', result.stdout)

    def test_default_writes_sddm_state_and_primary(self):
        result = self.cli("default", "plasma")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = (self.root / "var/lib/sddm/state.conf").read_text()
        self.assertIn("Session=plasma", state)
        conf = (self.root / "etc/parametral/desktop.conf").read_text()
        self.assertIn("PARAMETRAL_PRIMARY_SESSION=plasma", conf)
        sddm = (self.root / "etc/sddm.conf.d/20-parametral-session.conf").read_text()
        self.assertIn("Session=plasma", sddm)

    def test_unknown_session_is_refused(self):
        result = self.cli("default", "gnome")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown session", result.stderr)


if __name__ == "__main__":
    unittest.main()

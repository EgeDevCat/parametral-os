"""The daemon entry point must sort a flat option list into argparse order.

Regression test for: the unit passing --policy/--harddeny-socket next to --state/--socket,
which argparse rejects ("invalid choice: /etc/parametral/policy/...").
"""
import importlib.machinery
import importlib.util
import pathlib
import unittest

BIN = pathlib.Path(__file__).resolve().parent.parent / "bin" / "parametrald"


def load_entry_point():
    # the entry point has no .py suffix, so name the loader explicitly
    loader = importlib.machinery.SourceFileLoader("parametrald_entry", str(BIN))
    spec = importlib.util.spec_from_loader("parametrald_entry", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SplitArgvTest(unittest.TestCase):
    def setUp(self):
        self.split = load_entry_point().split_argv

    def test_globals_and_serve_options_are_separated(self):
        globals_, serve = self.split([
            "--state", "/var/lib/parametral",
            "--socket", "/run/parametral/control.sock",
            "--policy", "/etc/parametral/policy/policy.v1.json",
            "--harddeny-socket", "/run/parametral/harddeny.sock",
        ])
        self.assertEqual(globals_, ["--state", "/var/lib/parametral",
                                    "--socket", "/run/parametral/control.sock"])
        self.assertEqual(serve, ["--policy", "/etc/parametral/policy/policy.v1.json",
                                 "--harddeny-socket", "/run/parametral/harddeny.sock"])

    def test_equals_form_is_kept_with_serve(self):
        globals_, serve = self.split(["--state", "/s", "--policy=/p.json"])
        self.assertEqual(globals_, ["--state", "/s"])
        self.assertEqual(serve, ["--policy=/p.json"])

    def test_no_serve_options(self):
        globals_, serve = self.split(["--state", "/s"])
        self.assertEqual(globals_, ["--state", "/s"])
        self.assertEqual(serve, [])

    def test_ordering_is_stable_for_argparse(self):
        globals_, serve = self.split(["--policy", "/p", "--state", "/s"])
        # argparse wants globals before the subcommand, serve options after
        self.assertIn("--state", globals_)
        self.assertNotIn("--policy", globals_)
        self.assertEqual(serve[0], "--policy")


if __name__ == "__main__":
    unittest.main()

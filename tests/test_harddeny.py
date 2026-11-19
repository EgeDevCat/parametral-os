"""Tier-2 oracle: deterministic, signed, fail-closed — and not the model.

These tests exist because the security story must not rest on GC Shield (an
in-model, probabilistic defence). They prove the hard floor is independent of
the model: a valid token, a permissive policy and a jailbroken AI all still hit
the same deterministic wall.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import threading
import time
import unittest

import support

from ultraos import harddeny as hd
from ultraos.client import Client, ClientError
from ultraos.daemon import UltraOsDaemon, UltraOsServer


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ultraos-hd-")
        self.rules = os.path.join(self.tmp, "hard_deny.v1.json")
        self.key = os.path.join(self.tmp, "hard_deny.ed25519.sk")
        self.pub = os.path.join(self.tmp, "hard_deny.v1.pub")
        shutil.copyfile(os.path.join(support.REPO, "policy", hd.DEFAULT_RULES), self.rules)
        hd.ed25519_keygen(self.key, self.pub)
        hd.sign_rules(self.rules, self.key)
        self.engine = hd.load_rules(self.rules, self.pub)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_disk_and_kernel_commands_are_denied(self):
        for command in ("mkfs.ext4", "wipefs", "fdisk", "dd", "modprobe", "kexec", "iptables"):
            verdict = self.engine.check("exec.run", {"command": command})
            self.assertEqual(verdict["decision"], "deny", command)
            self.assertTrue(verdict["rule_id"].startswith("hd-"))

    def test_bootloader_paths_are_denied(self):
        verdict = self.engine.check("fs.write", {"paths": ["/boot/loader/entries/x.conf"]})
        self.assertEqual(verdict["decision"], "deny")
        self.assertEqual(verdict["rule_id"], "hd-bootloader")

    def test_credential_material_is_denied(self):
        for path in ("/etc/shadow", "/etc/sudoers", "/root/.ssh/id_ed25519",
                     "/home/x/.ssh/id_rsa", "/home/x/.gnupg/private-keys-v1.d/a.key"):
            verdict = self.engine.check("fs.read", {"paths": [path]})
            self.assertEqual(verdict["decision"], "deny", path)
            self.assertEqual(verdict["rule_id"], "hd-credentials")

    def test_sensitive_host_mounts_are_denied(self):
        verdict = self.engine.check("sandbox.create", {"host_paths": ["/dev/sda"]})
        self.assertEqual(verdict["decision"], "deny")
        self.assertEqual(verdict["rule_id"], "hd-sensitive-host-mounts")

    def test_instance_files_cannot_be_rewritten(self):
        for path in ("/etc/ultraos/policy.v1.json", "/var/lib/ultraos/hard_deny.v1.json",
                     "/home/x/operator.key"):
            verdict = self.engine.check("fs.write", {"paths": [path]})
            self.assertEqual(verdict["decision"], "deny", path)

    def test_normal_work_is_allowed(self):
        for operation, scope in (("exec.run", {"command": "git"}),
                                 ("exec.run", {"command": "nix"}),
                                 ("fs.read", {"paths": ["/work/notes.txt"]}),
                                 ("fs.list", {"paths": ["/work"]}),
                                 ("sandbox.create", {"host_paths": ["/opt/models/llama"]}),
                                 ("status", {})):
            verdict = self.engine.check(operation, scope)
            self.assertEqual(verdict["decision"], "allow", f"{operation} {scope}")

    def test_verdict_carries_rules_identity(self):
        verdict = self.engine.check("exec.run", {"command": "git"})
        self.assertEqual(verdict["rules_version"], 1)
        self.assertTrue(verdict["rules_sig"].startswith("ed25519:"))

    def test_unsigned_rules_are_refused(self):
        os.unlink(self.rules + ".sig")
        with self.assertRaises(hd.HardDenyError) as raised:
            hd.load_rules(self.rules, self.key)
        self.assertIn("unsigned", str(raised.exception))

    def test_tampered_rules_are_refused(self):
        rules = json.load(open(self.rules))
        rules["rules"] = [rule for rule in rules["rules"] if rule["id"] != "hd-disk-destroy"]
        json.dump(rules, open(self.rules, "w"))
        with self.assertRaises(hd.HardDenyError) as raised:
            hd.load_rules(self.rules, self.pub)
        self.assertIn("signature does not verify", str(raised.exception))

    def test_wrong_public_key_is_refused(self):
        other_sk = os.path.join(self.tmp, "other.sk")
        other_pub = os.path.join(self.tmp, "other.pub")
        hd.ed25519_keygen(other_sk, other_pub)
        with self.assertRaises(hd.HardDenyError):
            hd.load_rules(self.rules, other_pub)

    def test_verification_needs_no_private_key(self):
        # Asymmetric by construction: delete the signing key, verification still works.
        os.unlink(self.key)
        engine = hd.load_rules(self.rules, self.pub)
        self.assertTrue(engine.sig.startswith("ed25519:"))
        self.assertEqual(engine.rules["version"], 1)

    def test_signature_record_is_ed25519(self):
        record = json.load(open(self.rules + ".sig"))
        self.assertEqual(record["alg"], "ed25519")
        self.assertTrue(record["key_id"].startswith("ed25519:"))
        self.assertTrue(record["sig"].startswith("base64:"))

    def test_forged_signature_is_refused(self):
        record = json.load(open(self.rules + ".sig"))
        raw = bytearray(base64.b64decode(record["sig"].split("base64:", 1)[-1]))
        raw[0] ^= 0xFF
        record["sig"] = "base64:" + base64.b64encode(bytes(raw)).decode()
        json.dump(record, open(self.rules + ".sig", "w"))
        with self.assertRaises(hd.HardDenyError):
            hd.load_rules(self.rules, self.pub)

    def test_client_fails_closed_when_oracle_is_down(self):
        client = hd.HardDenyClient(os.path.join(self.tmp, "nope.sock"), timeout=0.5)
        with self.assertRaises(hd.HardDenyUnavailable):
            client.check("exec.run", {"command": "git"})

    def test_server_round_trip(self):
        socket_path = os.path.join(self.tmp, "hd.sock")
        server = hd.HardDenyServer(socket_path, self.engine)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = hd.HardDenyClient(socket_path)
            self.assertEqual(client.check("exec.run", {"command": "wipefs"})["decision"], "deny")
            self.assertEqual(client.check("exec.run", {"command": "git"})["decision"], "allow")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class DaemonOracleTest(unittest.TestCase):
    """The oracle is consulted before policy and before token use."""

    @classmethod
    def setUpClass(cls):
        cls.harness = support.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.close()

    def setUp(self):
        self.client = self.harness.client()
        self.sandbox = support.make_sandbox(self.harness, name="hd-%s" % self._testMethodName[:16])
        self.sandbox_id = self.sandbox["sandbox_id"]

    def tearDown(self):
        try:
            token = self.client.request_permission("sandbox.destroy",
                                                   {"sandbox_id": self.sandbox_id},
                                                   "cleanup")["capability_token"]
            self.client.call("v1.sandbox.destroy", sandbox_id=self.sandbox_id,
                             capability_token=token)
        except ClientError:
            pass
        self.client.close()

    def test_valid_token_cannot_override_hard_deny(self):
        # Mint a fully valid token behind the policy engine's back: even then the
        # oracle refuses, which is the whole point of a deterministic floor.
        token, _payload = self.harness.daemon.tokens.issue(
            ops=["exec.run"], scope={"sandbox_ids": [self.sandbox_id]}, ttl_s=60)
        with self.assertRaises(ClientError) as raised:
            self.client.call("v1.exec.run", sandbox_id=self.sandbox_id, cmd=["wipefs", "-a", "/dev/sda"],
                             capability_token=token)
        self.assertEqual(raised.exception.code, -32001)
        self.assertTrue(raised.exception.data["hard_deny"])
        self.assertFalse(raised.exception.data["approval_possible"])

    def test_permission_request_is_stopped_by_the_oracle(self):
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("exec.run",
                                           {"sandbox_id": self.sandbox_id,
                                            "commands": ["iptables"]},
                                           "flush the firewall")
        self.assertEqual(raised.exception.data["rule_id"], "hd-firewall")
        self.assertTrue(raised.exception.data["hard_deny"])

    def test_credential_read_is_a_hard_deny_not_a_policy_deny(self):
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("fs.read",
                                           {"sandbox_id": self.sandbox_id,
                                            "paths": ["/etc/shadow"]},
                                           "read hashes")
        self.assertTrue(raised.exception.data["hard_deny"])
        self.assertEqual(raised.exception.data["rule_id"], "hd-credentials")

    def test_hard_deny_is_audited_as_critical(self):
        with self.assertRaises(ClientError):
            self.client.request_permission("exec.run",
                                           {"sandbox_id": self.sandbox_id,
                                            "commands": ["modprobe"]},
                                           "load a module")
        records = self.harness.daemon.audit.query(limit=200)
        critical = [record for record in records if record["severity"] == "critical"]
        self.assertTrue(critical, "hard deny must be logged as critical")
        self.assertIn("hd-kernel", json.dumps(critical[-1]))

    def test_status_reports_oracle_identity(self):
        status = self.client.status()
        self.assertTrue(status["harddeny"]["available"])
        self.assertEqual(status["harddeny"]["rules_version"], 1)
        self.assertTrue(status["harddeny"]["rules_sig"].startswith("ed25519:"))


class OracleDownTest(unittest.TestCase):
    """Fail closed: no oracle means no state-changing operation, but status still works."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ultraos-hddown-")
        os.environ["XDG_RUNTIME_DIR"] = os.path.join(self.tmp, "run")
        socket_path = os.path.join(self.tmp, "control.sock")
        self.daemon = UltraOsDaemon(state_dir=os.path.join(self.tmp, "state"),
                                    socket_path=socket_path,
                                    notifier=lambda approval: None,
                                    harddeny_socket=os.path.join(self.tmp, "missing.sock"))
        self.server = UltraOsServer(socket_path, self.daemon)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.socket_path = socket_path

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_state_changing_calls_are_refused_with_clear_error(self):
        with Client(socket_path=self.socket_path) as client:
            with self.assertRaises(ClientError) as raised:
                client.call("v1.fs.list", sandbox_id="sbx_loc_000000000000", path="/work")
            self.assertEqual(raised.exception.code, -32013)
            self.assertEqual(raised.exception.ultraos_code, "HARD_DENY_UNAVAILABLE")

    def test_diagnostics_still_answer_and_report_the_oracle_down(self):
        with Client(socket_path=self.socket_path) as client:
            status = client.status()
            self.assertFalse(status["harddeny"]["available"])
            self.assertIn("error", status["harddeny"])
            self.assertEqual(client.hello()["selected"], "v1")


class PeerCredentialTest(unittest.TestCase):
    """SO_PEERCRED: only the gateway uid may query the oracle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ultraos-peer-")
        self.rules = os.path.join(self.tmp, "hard_deny.v1.json")
        self.sk = os.path.join(self.tmp, "k.sk")
        self.pub = os.path.join(self.tmp, "k.pub")
        shutil.copyfile(os.path.join(support.REPO, "policy", hd.DEFAULT_RULES), self.rules)
        hd.ed25519_keygen(self.sk, self.pub)
        hd.sign_rules(self.rules, self.sk)
        self.engine = hd.load_rules(self.rules, self.pub)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _serve(self, allowed):
        socket_path = os.path.join(self.tmp, "hd.sock")
        server = hd.HardDenyServer(socket_path, self.engine, allowed_uids=allowed)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 5)
        return socket_path

    def test_own_uid_is_allowed(self):
        client = hd.HardDenyClient(self._serve({os.getuid()}))
        self.assertEqual(client.check("exec.run", {"command": "git"})["decision"], "allow")

    def test_foreign_uid_is_rejected(self):
        # Simulate a socket owned for a different user: only uid 424242 may connect,
        # so our own connection must be refused instead of answered.
        client = hd.HardDenyClient(self._serve({424242}))
        verdict = client.check("exec.run", {"command": "git"})
        self.assertEqual(verdict["decision"], "deny")
        self.assertEqual(verdict["rule_id"], "hd-peer-rejected")

    def test_rejected_peer_cannot_probe_the_list(self):
        client = hd.HardDenyClient(self._serve({424242}))
        verdict = client.check("exec.run", {"command": "modprobe"})
        self.assertEqual(verdict["rule_id"], "hd-peer-rejected",
                         "a foreign peer must not even learn which rule matched")


class RuntimeFileWatchTest(unittest.TestCase):
    """A rule file that changes while the oracle runs shuts the oracle down."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ultraos-watch-")
        self.rules = os.path.join(self.tmp, "hard_deny.v1.json")
        self.sk = os.path.join(self.tmp, "k.sk")
        self.pub = os.path.join(self.tmp, "k.pub")
        shutil.copyfile(os.path.join(support.REPO, "policy", hd.DEFAULT_RULES), self.rules)
        hd.ed25519_keygen(self.sk, self.pub)
        hd.sign_rules(self.rules, self.sk)
        self.engine = hd.load_rules(self.rules, self.pub)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_watcher_fires_when_rules_change(self):
        watcher = hd.RulesWatcher(self.rules, on_change=lambda reason: None,
                                  poll_interval=0.1)
        watcher.start()
        self.addCleanup(watcher.stop)
        with open(self.rules, "a") as handle:
            handle.write("\n")
        self.assertTrue(watcher.fired.wait(5), "watcher did not notice the change")
        self.assertIn("changed", watcher.reason)

    def test_oracle_stops_serving_after_rules_change(self):
        socket_path = os.path.join(self.tmp, "hd.sock")
        server = hd.HardDenyServer(socket_path, self.engine, allowed_uids={os.getuid()})
        closed: dict = {"reason": None}
        watcher = hd.RulesWatcher(
            self.rules,
            on_change=lambda reason: (closed.update(reason=reason), server.shutdown()),
            poll_interval=0.1).start()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = hd.HardDenyClient(socket_path)
            self.assertEqual(client.check("exec.run", {"command": "git"})["decision"], "allow")
            with open(self.rules, "a") as handle:
                handle.write("\n")
            self.assertTrue(watcher.fired.wait(5))
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "oracle kept serving after a rules change")
            with self.assertRaises(hd.HardDenyUnavailable):
                hd.HardDenyClient(socket_path, timeout=0.5).check("exec.run", {"command": "git"})
        finally:
            watcher.stop()
            server.server_close()


if __name__ == "__main__":
    unittest.main()

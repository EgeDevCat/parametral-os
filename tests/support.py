"""Test harness: an isolated daemon per test, real sockets, real sandboxes."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

POLICY = os.path.join(REPO, "policy", "policy.v1.json")
GUARD = os.path.join(REPO, "bin", "seccomp_guard")


class Harness:
    """Starts parametrald on a private socket + state dir; cleans up on close()."""

    def __init__(self, policy: str | None = None):
        from parametral.daemon import ParametralDaemon, ParametralServer

        self.tmp = tempfile.mkdtemp(prefix="parametral-test-")
        self.state = os.path.join(self.tmp, "state")
        self.socket_path = os.path.join(self.tmp, "control.sock")
        self._old_env = {key: os.environ.get(key) for key in ("XDG_RUNTIME_DIR", "PARAMETRAL_STATE")}
        os.environ["XDG_RUNTIME_DIR"] = os.path.join(self.tmp, "run")
        os.environ["PARAMETRAL_STATE"] = self.state

        from parametral import harddeny as hd
        from parametral import util

        from parametral import ed25519 as _ed

        self.approver_pub_path = os.path.join(util.runtime_dir(), "approver.pub")
        self.approver_sk_path = os.path.join(util.runtime_dir(), "approver.sk")
        util.ensure_dir(util.runtime_dir(), 0o700)
        _ed.keygen(self.approver_sk_path, self.approver_pub_path)
        self.approver_key_path = self.approver_pub_path  # legacy alias

        # Tier-2 oracle: signed copy of the repo rules, signed with a throwaway key.
        self.harddeny_socket = os.path.join(self.tmp, "harddeny.sock")
        self.operator_key = os.path.join(self.tmp, "operator.key")
        self.harddeny_rules = os.path.join(self.tmp, "hard_deny.v1.json")
        self.harddeny_pub = os.path.join(self.tmp, "hard_deny.v1.pub")
        shutil.copyfile(os.path.join(REPO, "policy", hd.DEFAULT_RULES), self.harddeny_rules)
        hd.ed25519_keygen(self.operator_key, self.harddeny_pub)
        hd.sign_rules(self.harddeny_rules, self.operator_key)
        engine = hd.load_rules(self.harddeny_rules, self.harddeny_pub)
        self.harddeny_server = hd.HardDenyServer(self.harddeny_socket, engine)
        self.harddeny_thread = threading.Thread(target=self.harddeny_server.serve_forever,
                                                daemon=True)
        self.harddeny_thread.start()
        self.harddeny_engine = engine
        for _ in range(100):
            if os.path.exists(self.harddeny_socket):
                break
            time.sleep(0.01)
        self.daemon = ParametralDaemon(policy_path=policy or POLICY, state_dir=self.state,
                                    socket_path=self.socket_path,
                                    notifier=lambda approval: None,
                                    harddeny_socket=self.harddeny_socket,
                                    harddeny_rules=self.harddeny_rules)
        self.server = ParametralServer(self.socket_path, self.daemon)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        for _ in range(100):
            if os.path.exists(self.socket_path):
                break
            time.sleep(0.01)

    def approver_store(self):
        """Approver-side store: holds the private key, used by tests to sign decisions."""
        from parametral.approvals import ApprovalStore

        return ApprovalStore(self.state, self.approver_pub_path,
                             approver_sk_path=self.approver_sk_path)

    def client(self):
        from parametral.client import Client

        return Client(socket_path=self.socket_path)

    def close(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
            self.harddeny_server.shutdown()
            self.harddeny_server.server_close()
        finally:
            self.thread.join(timeout=5)
            for key, value in self._old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            shutil.rmtree(self.tmp, ignore_errors=True)


def make_sandbox(harness: Harness, name: str = "test", **options):
    client = harness.client()
    try:
        token = client.request_permission("sandbox.create", {}, "test sandbox")["capability_token"]
        return client.call("v1.sandbox.create", name=name, capability_token=token, **options)
    finally:
        client.close()


def token_for(harness: Harness, operation: str, scope: dict, justification: str = "test",
              **options):
    client = harness.client()
    try:
        return client.request_permission(operation, scope, justification, **options)
    finally:
        client.close()

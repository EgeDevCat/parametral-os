"""Per-app network permission: allow-listed Unix-socket proxy, sandbox stays netless.

The sandbox has no interfaces at all. The only way out is a Unix socket whose proxy
refuses every destination that was not approved — so "can it reach the internet?" has a
two-part answer: not directly, and only the approved host:port through the proxy.
"""
from __future__ import annotations

import os
import socket
import threading
import time
import unittest

import support

from parametral import netproxy
from parametral.client import ClientError


class EchoServer:
    """Tiny TCP echo server standing in for a remote service."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.connections = 0
        self._stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._echo, args=(conn,), daemon=True).start()

    @staticmethod
    def _echo(conn):
        with conn:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                conn.sendall(b"echo:" + chunk)

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def unix_roundtrip(path: str, payload: bytes, timeout: float = 5.0) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(path)
        sock.sendall(payload)
        return sock.recv(4096)


class GrantTest(unittest.TestCase):
    def setUp(self):
        self.tmp = support.REPO + "/.tmp-net-" + os.urandom(4).hex()
        os.makedirs(self.tmp, exist_ok=True)
        self.events = []
        self.registry = netproxy.GrantRegistry(on_event=self.events.append)
        self.echo = EchoServer()

    def tearDown(self):
        self.echo.close()
        self.registry.sweep()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_approved_destination_is_reachable_through_the_socket(self):
        grant = self.registry.open("sbx_l_test", self.tmp,
                                   [{"host": "127.0.0.1", "port": self.echo.port}], ttl_s=30)
        path = os.path.join(self.tmp, f"{grant.grant_id}-{self.echo.port}.sock")
        self.assertEqual(self.registry.open.__name__, "open")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(unix_roundtrip(path, b"ping"), b"echo:ping")
        self.assertEqual(self.echo.connections, 1)
        self.assertTrue(any(event["event"] == "connect" for event in self.events))

    def test_unapproved_destination_is_refused(self):
        grant = self.registry.open("sbx_l_test", self.tmp,
                                   [{"host": "127.0.0.1", "port": free_port()}], ttl_s=30)
        path = os.path.join(self.tmp, f"{grant.grant_id}-{grant.hosts[0][1]}.sock")
        with self.assertRaises((OSError, socket.timeout)):
            unix_roundtrip(path, b"x", timeout=1.0)
        self.assertTrue(any(event["event"] == "connect_failed" for event in self.events))

    def test_grant_lists_and_closes(self):
        grant = self.registry.open("sbx_l_a", self.tmp,
                                   [{"host": "127.0.0.1", "port": self.echo.port}], ttl_s=30)
        self.assertEqual(len(self.registry.list()), 1)
        self.assertEqual(len(self.registry.for_sandbox("sbx_l_a")), 1)
        self.registry.close(grant.grant_id)
        self.assertEqual(self.registry.list(), [])
        with self.assertRaises(netproxy.NetGrantError):
            self.registry.close(grant.grant_id)

    def test_expired_grant_is_swept_and_socket_is_gone(self):
        grant = self.registry.open("sbx_l_a", self.tmp,
                                   [{"host": "127.0.0.1", "port": self.echo.port}], ttl_s=1)
        path = os.path.join(self.tmp, f"{grant.grant_id}-{self.echo.port}.sock")
        time.sleep(1.1)
        self.assertTrue(grant.closed)
        self.assertEqual(self.registry.sweep(), 1)
        self.assertFalse(os.path.exists(path))

    def test_bad_destination_is_refused_at_grant_time(self):
        for hosts in ([], [{"host": "", "port": 80}], [{"host": "x", "port": 0}],
                      [{"host": "a b", "port": 80}], ["not-a-dict"]):
            with self.assertRaises(netproxy.NetGrantError):
                netproxy.GrantRegistry().open("sbx_l_a", self.tmp, hosts, ttl_s=10)


class DaemonNetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = support.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.close()

    def setUp(self):
        self.client = self.harness.client()
        self.sandbox = support.make_sandbox(self.harness, name="net-%s" % os.urandom(3).hex())
        self.sid = self.sandbox["sandbox_id"]
        self.echo = EchoServer()

    def tearDown(self):
        for grant in self.harness.daemon.net_grants.for_sandbox(self.sid):
            self.harness.daemon.net_grants.close(grant.grant_id)
        try:
            token = self.client.request_permission("sandbox.destroy",
                                                   {"sandbox_id": self.sid},
                                                   "cleanup")["capability_token"]
            self.client.call("v1.sandbox.destroy", sandbox_id=self.sid, capability_token=token)
        except ClientError:
            pass
        self.client.close()
        self.echo.close()

    def _approved(self, hosts, ttl_s=60) -> str:
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("net.open", {"sandbox_id": self.sid},
                                           f"let the app reach {hosts}")
        approval_id = raised.exception.data["approval_id"]
        proof = self.harness.approver_store().proof(approval_id, "approved")
        self.client.call("v1.approvals.decide", approval_id=approval_id, decision="approve",
                         approver_proof=proof, decided_by="user:test")
        return self.client.request_permission("net.open", {"sandbox_id": self.sid},
                                              "approved net access", approval_id=approval_id,
                                              ttl_s=ttl_s)["capability_token"]

    def test_net_open_requires_approval(self):
        with self.assertRaises(ClientError) as raised:
            self.client.request_permission("net.open", {"sandbox_id": self.sid}, "net")
        self.assertEqual(raised.exception.code, -32004)

    def test_approved_grant_works_from_inside_the_sandbox(self):
        token = self._approved([{"host": "127.0.0.1", "port": self.echo.port}])
        grant = self.client.call("v1.net.open", sandbox_id=self.sid,
                                 hosts=[{"host": "127.0.0.1", "port": self.echo.port}],
                                 ttl_s=60, capability_token=token)
        sock_path = grant["sockets"][0]
        script = (
            "import socket\n"
            f"s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
            f"s.settimeout(5)\n"
            f"s.connect('{sock_path}')\n"
            "s.sendall(b'hello')\n"
            "print(s.recv(64).decode())\n"
        )
        result = self.harness.daemon.sandboxes.run(self.sid, ["python3", "-c", script],
                                                   timeout_s=20)
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertIn("echo:hello", result["stdout"])

    def test_sandbox_still_has_no_direct_network_with_a_grant_open(self):
        token = self._approved([{"host": "127.0.0.1", "port": self.echo.port}])
        self.client.call("v1.net.open", sandbox_id=self.sid,
                          hosts=[{"host": "127.0.0.1", "port": self.echo.port}],
                          ttl_s=60, capability_token=token)
        script = ("import socket\ns=socket.socket()\ns.settimeout(2)\n"
                  "try:\n s.connect(('127.0.0.1', %d))\n print('OPEN')\n"
                  "except OSError as e:\n print('CLOSED', e.errno)\n" % self.echo.port)
        result = self.harness.daemon.sandboxes.run(self.sid, ["python3", "-c", script])
        self.assertIn("CLOSED", result["stdout"])

    def test_grants_are_audited(self):
        token = self._approved([{"host": "127.0.0.1", "port": self.echo.port}])
        self.client.call("v1.net.open", sandbox_id=self.sid,
                          hosts=[{"host": "127.0.0.1", "port": self.echo.port}],
                          ttl_s=60, capability_token=token)
        records = [record for record in self.harness.daemon.audit.query(limit=200)
                   if record["method"].startswith("netproxy.")]
        self.assertTrue(records, "grant creation and connections must be audited")
        self.assertEqual(records[-1]["sandbox_id"], self.sid)

    def test_list_and_close_via_api(self):
        token = self._approved([{"host": "127.0.0.1", "port": self.echo.port}])
        grant = self.client.call("v1.net.open", sandbox_id=self.sid,
                                  hosts=[{"host": "127.0.0.1", "port": self.echo.port}],
                                  ttl_s=60, capability_token=token)
        list_token = support.token_for(self.harness, "net.list",
                                       {"sandbox_id": self.sid})["capability_token"]
        listing = self.client.call("v1.net.list", sandbox_id=self.sid,
                                    capability_token=list_token)
        self.assertEqual(listing["grants"][0]["grant_id"], grant["grant_id"])
        # revoking is an admin action keyed by grant id, not by sandbox scope
        close_token = support.token_for(self.harness, "net.close", {})["capability_token"]
        closed = self.client.call("v1.net.close", grant_id=grant["grant_id"],
                                  capability_token=close_token)
        self.assertTrue(closed["closed"])


if __name__ == "__main__":
    unittest.main()

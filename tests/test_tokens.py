"""Capability tokens: signature, TTL, node, operation, scope, use limits."""
from __future__ import annotations

import os
import tempfile
import time
import unittest

import support  # noqa: F401

from parametral.tokens import TokenError, TokenStore


class TokenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="parametral-token-")
        self.store = TokenStore(self.tmp, os.path.join(self.tmp, "key"), node_id="local",
                                ttl_cap_s=60, default_max_uses=3)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roundtrip_and_claims(self):
        token, payload = self.store.issue(ops=["exec.run"], scope={"sandbox_ids": ["sbx_l_a"]},
                                          ttl_s=30)
        verified = self.store.verify(token, "exec.run", {"sandbox_id": "sbx_l_a"})
        self.assertEqual(verified["tid"], payload["tid"])
        self.assertEqual(verified["ops"], ["exec.run"])
        self.assertEqual(verified["node_id"], "local")

    def test_tampered_payload_is_rejected(self):
        token, _ = self.store.issue(ops=["exec.run"], scope={}, ttl_s=30)
        body, signature = token[3:].split(".")
        forged = token[:3] + body[:-2] + ("AA" if body[-2:] != "AA" else "BB") + "." + signature
        with self.assertRaises(TokenError) as raised:
            self.store.verify(forged)
        self.assertEqual(raised.exception.code, "TOKEN_INVALID")

    def test_missing_signature_is_rejected(self):
        with self.assertRaises(TokenError):
            self.store.verify("u1.eyJ2IjoxfQ", "exec.run", {})

    def test_node_scope_is_enforced(self):
        token, _ = self.store.issue(ops=["exec.run"], scope={}, ttl_s=30)
        other = TokenStore(self.tmp, os.path.join(self.tmp, "key"), node_id="node-b")
        with self.assertRaises(TokenError) as raised:
            other.verify(token, "exec.run", {})
        self.assertIn("different node", str(raised.exception))

    def test_read_token_covers_list(self):
        token, _ = self.store.issue(ops=["fs.read"], scope={"sandbox_ids": ["sbx_l_a"]},
                                    ttl_s=30)
        self.store.verify(token, "fs.list", {"sandbox_id": "sbx_l_a"})
        with self.assertRaises(TokenError):
            self.store.verify(token, "fs.write", {"sandbox_id": "sbx_l_a"})

    def test_operation_scope_is_enforced(self):
        token, _ = self.store.issue(ops=["fs.read"], scope={}, ttl_s=30)
        with self.assertRaises(TokenError):
            self.store.verify(token, "exec.run", {})

    def test_scope_limits_sandbox_and_command(self):
        token, _ = self.store.issue(ops=["exec.run"],
                                    scope={"sandbox_ids": ["sbx_l_a"], "commands": ["git"]},
                                    ttl_s=30)
        self.store.verify(token, "exec.run", {"sandbox_id": "sbx_l_a", "command": "git"})
        with self.assertRaises(TokenError):
            self.store.verify(token, "exec.run", {"sandbox_id": "sbx_l_b", "command": "git"})
        with self.assertRaises(TokenError):
            self.store.verify(token, "exec.run", {"sandbox_id": "sbx_l_a", "command": "curl"})

    def test_path_scope(self):
        token, _ = self.store.issue(ops=["fs.read"], scope={"paths": ["/work/**"]}, ttl_s=30)
        self.store.verify(token, "fs.read", {"paths": ["/work/a/b"]})
        with self.assertRaises(TokenError):
            self.store.verify(token, "fs.read", {"paths": ["/etc/passwd"]})

    def test_uses_are_counted_and_exhaust(self):
        token, payload = self.store.issue(ops=["exec.run"], scope={}, ttl_s=30, max_uses=2)
        self.store.verify(token, "exec.run", {}, consume=True)
        self.store.verify(token, "exec.run", {}, consume=True)
        with self.assertRaises(TokenError) as raised:
            self.store.verify(token, "exec.run", {}, consume=True)
        self.assertIn("exhausted", str(raised.exception))
        self.assertEqual(payload["max_uses"], 2)

    def test_expiry_is_enforced(self):
        token, _ = self.store.issue(ops=["exec.run"], scope={}, ttl_s=1)
        time.sleep(1.2)
        with self.assertRaises(TokenError) as raised:
            self.store.verify(token, "exec.run", {})
        self.assertIn("expired", str(raised.exception))

    def test_ttl_is_capped(self):
        _token, payload = self.store.issue(ops=["exec.run"], scope={}, ttl_s=999999)
        from parametral import util

        lifetime = (util.parse_iso(payload["exp"]) - util.parse_iso(payload["iat"])).total_seconds()
        self.assertLessEqual(lifetime, 61)

    def test_key_is_private(self):
        key_path = os.path.join(self.tmp, "key")
        self.assertEqual(os.stat(key_path).st_mode & 0o777, 0o600)
        self.assertGreaterEqual(os.path.getsize(key_path), 32)

    def test_sweep_removes_expired_counters(self):
        token, payload = self.store.issue(ops=["exec.run"], scope={}, ttl_s=1)
        self.store.verify(token, "exec.run", {}, consume=True)
        time.sleep(1.2)
        self.assertGreaterEqual(self.store.sweep(), 1)


if __name__ == "__main__":
    unittest.main()

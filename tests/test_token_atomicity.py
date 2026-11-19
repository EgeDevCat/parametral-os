"""A token's use budget must hold under concurrency.

The daemon is threaded; before the flock, verify(consume=True) read the counter, compared it,
then wrote it back, so twenty simultaneous calls could all pass a max_uses=5 check.
"""
from __future__ import annotations

import os
import tempfile
import threading
import unittest

from parametral import tokens
from parametral.tokens import TokenError, TokenStore


class SingleUseRaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="token-race-")
        self.store = TokenStore(os.path.join(self.tmp, "state"),
                                os.path.join(self.tmp, "tokens.key"), node_id="local")

    def _hammer(self, token: str, threads: int = 20):
        ok, rejected, errors = [], [], []

        def worker():
            try:
                self.store.verify(token, "exec.run", consume=True)
                ok.append(1)
            except TokenError:
                rejected.append(1)
            except Exception as exc:  # noqa: BLE001 - surfaced below
                errors.append(repr(exc))

        gate = threading.Barrier(threads)
        running = []
        for _ in range(threads):
            def run():
                gate.wait()
                worker()
            thread = threading.Thread(target=run)
            running.append(thread)
            thread.start()
        for thread in running:
            thread.join(timeout=20)
        self.assertEqual(errors, [])
        return len(ok), len(rejected)

    def test_exactly_max_uses_calls_succeed(self):
        token, payload = self.store.issue(ops=["exec.run"], scope={}, ttl_s=60, max_uses=5)
        ok, rejected = self._hammer(token, threads=20)
        self.assertEqual(ok, 5, f"expected exactly 5 successful uses, got {ok}")
        self.assertEqual(rejected, 15)
        self.assertEqual(self.store.used_count(payload["tid"]), 5)

    def test_single_use_token_is_spent_once(self):
        token, payload = self.store.issue(ops=["exec.run"], scope={}, ttl_s=60, max_uses=1)
        ok, rejected = self._hammer(token, threads=12)
        self.assertEqual(ok, 1, "a single-use token must be usable exactly once")
        self.assertEqual(rejected, 11)
        self.assertEqual(self.store.used_count(payload["tid"]), 1)

    def test_non_consuming_verify_does_not_spend(self):
        token, payload = self.store.issue(ops=["exec.run"], scope={}, ttl_s=60, max_uses=2)
        for _ in range(5):
            self.store.verify(token, "exec.run")   # dry check, no consume
        self.assertEqual(self.store.used_count(payload["tid"]), 0)
        self.store.verify(token, "exec.run", consume=True)
        self.assertTrue(self.store.used_count(payload["tid"]) == 1)


class CanonicalJsonTest(unittest.TestCase):
    """params_digest is only stable across implementations if the encoding is pinned."""

    def test_sorted_keys_compact_and_unicode_preserved(self):
        from parametral import util
        a = util.canonical_json({"b": 1, "a": "ğ", "c": [1, 2]})
        b = util.canonical_json({"c": [1, 2], "a": "ğ", "b": 1})
        self.assertEqual(a, b)
        self.assertEqual(a, b'{"a":"\xc4\x9f","b":1,"c":[1,2]}')
        self.assertNotIn(b" ", a)


if __name__ == "__main__":
    unittest.main()

"""The contract test: docs/API-v1.md and the daemon must not drift apart.

This is what keeps the promise to the other half of the project (Parametral): the
document is the interface, so every method in the doc must exist and every
implemented method must be documented.
"""
from __future__ import annotations

import re
import unittest

import support

from parametral.daemon import UltraOsDaemon

DOC = support.REPO + "/docs/API-v1.md"
METHOD_RE = re.compile(r"\bv1\.[a-z]+\.[a-z_]+(?:\.[a-z_]+)?\b")

ULTRaOS_CODES = {
    "PARSE_ERROR", "INVALID_REQUEST", "METHOD_NOT_FOUND", "INVALID_PARAMS", "INTERNAL",
    "POLICY_DENIED", "TOKEN_REQUIRED", "TOKEN_INVALID", "APPROVAL_REQUIRED",
    "APPROVAL_PENDING", "NOT_FOUND", "LIMIT_EXCEEDED", "UNSUPPORTED",
    "SANDBOX_UNAVAILABLE", "PEER_REJECTED", "NODE_MISMATCH", "CONFLICT",
}


class ApiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = open(DOC, encoding="utf-8").read()
        cls.documented = set(METHOD_RE.findall(cls.doc))
        cls.harness = support.Harness()
        cls.handlers = set(cls.harness.daemon.handlers)

    @classmethod
    def tearDownClass(cls):
        cls.harness.close()

    def test_every_documented_method_is_implemented(self):
        missing = self.documented - self.handlers
        self.assertFalse(missing, f"documented but not implemented: {sorted(missing)}")

    def test_every_implemented_method_is_documented(self):
        undocumented = self.handlers - self.documented
        self.assertFalse(undocumented, f"implemented but undocumented: {sorted(undocumented)}")

    def test_methods_are_version_prefixed(self):
        for method in self.handlers:
            self.assertTrue(method.startswith("v1."), method)

    def test_error_codes_are_documented(self):
        for code in ULTRaOS_CODES:
            self.assertIn(code, self.doc, f"error code {code} missing from the contract")

    def test_contract_is_frozen_at_v1(self):
        self.assertIn("v1.0.0", self.doc)
        self.assertIn("FROZEN", self.doc)
        self.assertIn("Additive only", self.doc)

    def test_operations_are_covered_by_policy_rules(self):
        from parametral.policy import OPERATIONS

        daemon = self.harness.daemon
        for method, operation in daemon.operation_of.items():
            if operation is None:
                continue
            self.assertIn(operation, OPERATIONS, method)

    def test_no_swarm_code_in_v1(self):
        import os

        src = os.path.join(support.REPO, "src", "parametral")
        for name in os.listdir(src):
            if not name.endswith(".py"):
                continue
            body = open(os.path.join(src, name), encoding="utf-8").read().lower()
            self.assertNotIn("import grpc", body)
            self.assertNotIn("swarm_manager", body)
            self.assertNotIn("gossip", body)


if __name__ == "__main__":
    unittest.main()

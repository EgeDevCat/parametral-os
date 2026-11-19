"""MCP adapter tests.

The adapter must be boring: parse MCP, forward to the gateway, report failures. Every test uses
a stub backend so the protocol can be checked without a daemon.
"""
from __future__ import annotations

import io
import json
import unittest

from parametral.mcp import McpServer, TOOLS, serve, tool_list


class StubBackend:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.error: Exception | None = None

    def __call__(self, method: str, params: dict) -> dict:
        self.calls.append((method, params))
        if self.error is not None:
            raise self.error
        return {"ok": True, "method": method}


class InitializeTest(unittest.TestCase):
    def test_initialize_reports_protocol_and_capabilities(self):
        server = McpServer(StubBackend())
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert response is not None
        result = response["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "parametral")

    def test_notifications_get_no_reply(self):
        server = McpServer(StubBackend())
        self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method_is_an_error(self):
        server = McpServer(StubBackend())
        response = server.handle({"jsonrpc": "2.0", "id": 9, "method": "nope"})
        assert response is not None
        self.assertEqual(response["error"]["code"], -32601)


class ToolsListTest(unittest.TestCase):
    def test_every_tool_has_schema_and_description(self):
        tools = tool_list()
        self.assertGreaterEqual(len(tools), 10)
        for tool in tools:
            self.assertTrue(tool["name"])
            self.assertTrue(tool["description"])
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_names_are_unique(self):
        names = [tool["name"] for tool in tool_list()]
        self.assertEqual(len(names), len(set(names)))


class ToolCallTest(unittest.TestCase):
    def setUp(self):
        self.backend = StubBackend()
        self.server = McpServer(self.backend)

    def _call(self, name, arguments, msg_id=2) -> dict:
        response = self.server.handle({
            "jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        assert response is not None, "tools/call must always answer"
        return response

    def test_call_is_forwarded_to_the_gateway_method(self):
        response = self._call("sandbox_create", {"name": "box"})
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(self.backend.calls, [("v1.sandbox.create", {"name": "box"})])
        self.assertIn("ok", response["result"]["content"][0]["text"])

    def test_missing_required_argument_is_reported_not_forwarded(self):
        response = self._call("exec_run", {"sandbox_id": "sbx_1"})
        self.assertTrue(response["result"]["isError"])
        self.assertIn("missing required argument", response["result"]["content"][0]["text"])
        self.assertEqual(self.backend.calls, [])

    def test_unknown_tool_is_an_error(self):
        response = self._call("rm_rf_everything", {})
        self.assertEqual(response["error"]["code"], -32602)

    def test_gateway_failure_becomes_tool_error_with_code(self):
        class Boom(Exception):
            code = -32004

            def __init__(self):
                super().__init__("operation needs human approval")
                self.data = {"approval_id": "appr_1"}

        self.backend.error = Boom()
        response = self._call("exec_run", {"sandbox_id": "sbx_1", "cmd": ["ls"]})
        text = response["result"]["content"][0]["text"]
        self.assertTrue(response["result"]["isError"])
        self.assertIn("-32004", text)
        self.assertIn("appr_1", text)


class StdioTest(unittest.TestCase):
    def test_line_protocol_handles_two_calls_and_a_bad_line(self):
        stdin = io.StringIO("\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            "not json",
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]) + "\n")
        stdout = io.StringIO()
        serve(StubBackend(), stdin=stdin, stdout=stdout)
        lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
        self.assertEqual(lines[0]["id"], 1)
        self.assertEqual(lines[1]["error"]["code"], -32700)   # parse error is reported
        self.assertEqual(lines[2]["id"], 2)
        self.assertIn("tools", lines[2]["result"])


class SafetyTest(unittest.TestCase):
    def test_adapter_holds_no_policy_of_its_own(self):
        """Every tool maps to exactly one gateway method — the adapter must not encode rules."""
        for name, spec in TOOLS.items():
            self.assertTrue(spec["method"].startswith("v1."), name)

    def test_dangerous_operations_are_not_reachable_here(self):
        # things that must only ever happen through the gateway with approval
        forbidden = {"approvals_decide", "policy_write", "host_root_shell"}
        self.assertFalse(forbidden & set(TOOLS))


if __name__ == "__main__":
    unittest.main()

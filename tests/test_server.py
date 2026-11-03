"""服务器层实测：协议协商、tools/list、tools/call 的封装与 isError。"""

from __future__ import annotations

import unittest

from nsa_mcp_hub import jsonrpc
from nsa_mcp_hub.server import build_handlers
from nsa_mcp_hub.tools import Kit, ToolSpec

EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def make_kit(handler, timeout_s=5.0) -> Kit:
    kit = Kit(key="t", name="testkit", instructions="测试用")
    kit.add(ToolSpec("t_ok", "总是成功", EMPTY, handler, timeout_s=timeout_s))
    return kit


class InitializeTests(unittest.TestCase):
    def setUp(self):
        self.handlers = build_handlers(make_kit(lambda a: {"ok": True}))

    def test_echoes_supported_protocol(self):
        r = self.handlers["initialize"]({"protocolVersion": "2025-03-26"})
        self.assertEqual(r["protocolVersion"], "2025-03-26")

    def test_falls_back_for_unknown_protocol(self):
        r = self.handlers["initialize"]({"protocolVersion": "1999-01-01"})
        self.assertEqual(r["protocolVersion"], jsonrpc.DEFAULT_PROTOCOL)

    def test_announces_tools_capability(self):
        r = self.handlers["initialize"]({})
        self.assertIn("tools", r["capabilities"])

    def test_server_info_name(self):
        r = self.handlers["initialize"]({})
        self.assertEqual(r["serverInfo"]["name"], "nsa-mcp-hub-t")

    def test_instructions_used(self):
        r = self.handlers["initialize"]({})
        self.assertEqual(r["instructions"], "测试用")


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.kit = make_kit(lambda a: {"ok": True, "reads": {"v": a.get("v", 0)}})
        self.handlers = build_handlers(self.kit)

    def test_tools_list(self):
        r = self.handlers["tools/list"]({})
        # kit_runtime 是内核白送的状态工具
        self.assertEqual([t["name"] for t in r["tools"]], ["t_ok", "kit_runtime"])

    def test_tools_call_wraps_result(self):
        r = self.handlers["tools/call"]({"name": "t_ok", "arguments": {"v": 3}})
        self.assertFalse(r["isError"])
        self.assertEqual(r["structuredContent"]["reads"], {"v": 3})
        self.assertEqual(r["content"][0]["type"], "text")

    def test_tools_call_missing_name(self):
        with self.assertRaises(jsonrpc.RpcError) as ctx:
            self.handlers["tools/call"]({})
        self.assertEqual(ctx.exception.code, jsonrpc.INVALID_PARAMS)

    def test_tools_call_unknown_tool(self):
        with self.assertRaises(jsonrpc.RpcError) as ctx:
            self.handlers["tools/call"]({"name": "nope", "arguments": {}})
        self.assertEqual(ctx.exception.code, jsonrpc.INVALID_PARAMS)

    def test_is_error_when_ok_false(self):
        kit = make_kit(lambda a: {"ok": False, "errors": ["failed"]})
        handlers = build_handlers(kit)
        r = handlers["tools/call"]({"name": "t_ok", "arguments": {}})
        self.assertTrue(r["isError"])
        self.assertEqual(r["structuredContent"]["errors"], ["failed"])

    def test_ping(self):
        self.assertEqual(self.handlers["ping"]({}), {})


if __name__ == "__main__":
    unittest.main()

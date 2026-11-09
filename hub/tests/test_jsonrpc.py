"""内核实测：framing、错误码、通知语义。"""

from __future__ import annotations

import io
import json
import unittest

from nsa_mcp_hub import jsonrpc


def run_serve(handlers, lines: list) -> list:
    """把若干行喂给 serve()，返回输出行解析后的对象列表。"""
    out = io.StringIO()
    jsonrpc.serve(handlers, instream=iter(lines), outstream=out)
    text = out.getvalue().strip()
    return [json.loads(x) for x in text.splitlines()] if text else []


class ReadMessagesTests(unittest.TestCase):
    def test_skips_blank_lines(self):
        msgs = list(jsonrpc.read_messages(iter(["", "   ", '{"a":1}'])))
        self.assertEqual(msgs, [{"a": 1}])

    def test_invalid_json_yields_none(self):
        msgs = list(jsonrpc.read_messages(iter(["{not json"])))
        self.assertEqual(msgs, [None])

    def test_multiple_messages(self):
        msgs = list(jsonrpc.read_messages(iter(['{"i":1}', '{"i":2}'])))
        self.assertEqual([m["i"] for m in msgs], [1, 2])


class ServeTests(unittest.TestCase):
    def test_request_returns_result(self):
        handlers = {"echo": lambda p: {"got": p.get("x")}}
        out = run_serve(handlers, ['{"jsonrpc":"2.0","id":7,"method":"echo","params":{"x":5}}'])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], 7)
        self.assertEqual(out[0]["result"], {"got": 5})

    def test_unknown_method_code(self):
        out = run_serve({}, ['{"jsonrpc":"2.0","id":1,"method":"nope"}'])
        self.assertEqual(out[0]["error"]["code"], jsonrpc.METHOD_NOT_FOUND)

    def test_notification_produces_no_output(self):
        handlers = {"ping": lambda p: {}}
        out = run_serve(handlers, ['{"jsonrpc":"2.0","method":"ping"}'])
        self.assertEqual(out, [])

    def test_notifications_prefix_never_replies(self):
        handlers = {"notifications/initialized": lambda p: None}
        out = run_serve(handlers, ['{"jsonrpc":"2.0","id":3,"method":"notifications/initialized"}'])
        self.assertEqual(out, [])

    def test_rpc_error_maps_to_code(self):
        def boom(_p):
            raise jsonrpc.RpcError(jsonrpc.INVALID_PARAMS, "bad params")
        out = run_serve({"boom": boom}, ['{"jsonrpc":"2.0","id":2,"method":"boom"}'])
        self.assertEqual(out[0]["error"]["code"], jsonrpc.INVALID_PARAMS)
        self.assertEqual(out[0]["error"]["message"], "bad params")

    def test_unexpected_exception_maps_to_internal(self):
        def boom(_p):
            raise ValueError("kaboom")
        out = run_serve({"boom": boom}, ['{"jsonrpc":"2.0","id":4,"method":"boom"}'])
        self.assertEqual(out[0]["error"]["code"], jsonrpc.INTERNAL_ERROR)
        self.assertIn("kaboom", out[0]["error"]["message"])

    def test_non_object_message(self):
        out = run_serve({}, ['[1,2,3]'])
        self.assertEqual(out[0]["error"]["code"], jsonrpc.INVALID_REQUEST)

    def test_missing_method(self):
        out = run_serve({}, ['{"jsonrpc":"2.0","id":9,"params":{}}'])
        self.assertEqual(out[0]["error"]["code"], jsonrpc.INVALID_REQUEST)

    def test_exit_stops_loop(self):
        out = run_serve({}, ['{"jsonrpc":"2.0","id":1,"method":"exit"}'])
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()

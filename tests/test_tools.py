"""工具层实测：结果归一化、单飞锁、超时、注册表。"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest

from nsa_mcp_hub.jsonrpc import INVALID_PARAMS, RpcError
from nsa_mcp_hub.tools import (Kit, ToolSpec, call_tool, normalize, run_with_lock,
                          tool_listing)

EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def make_kit(handler, timeout_s=5.0, key="t", name="testkit") -> Kit:
    kit = Kit(key=key, name=name)
    kit.add(ToolSpec("t_echo", "echo", EMPTY, handler, timeout_s=timeout_s))
    return kit


class NormalizeTests(unittest.TestCase):
    def test_dict_checks_all_ok(self):
        r = normalize("k", "c", ok=True, checks=[{"check": "v", "ok": True}])
        self.assertTrue(r["ok"])
        self.assertEqual(r["kit"], "k")
        self.assertEqual(r["capability"], "c")

    def test_failed_check_flips_ok(self):
        r = normalize("k", "c", ok=True, checks=[{"check": "v", "ok": False}])
        self.assertFalse(r["ok"])

    def test_string_checks_tolerated(self):
        # acadkit 的判据是纯文本，不能因此崩掉
        r = normalize("k", "c", ok=True, checks=["count", "length"])
        self.assertTrue(r["ok"])

    def test_errors_flip_ok(self):
        r = normalize("k", "c", ok=True, errors=["boom"])
        self.assertFalse(r["ok"])

    def test_defaults_present(self):
        r = normalize("k", "c", ok=True)
        for key in ("ok", "kit", "capability", "reads", "checks", "errors", "seconds"):
            self.assertIn(key, r)

    def test_seconds_rounded(self):
        r = normalize("k", "c", ok=True, seconds=1.23456)
        self.assertEqual(r["seconds"], 1.23)


class RegistryTests(unittest.TestCase):
    def test_tool_listing_shape(self):
        kit = make_kit(lambda a: {})
        rows = tool_listing(kit)
        # 每个 kit 自带一个 kit_runtime（不进锁的状态查询）
        self.assertEqual([r["name"] for r in rows], ["t_echo", "kit_runtime"])
        self.assertEqual(set(rows[0]), {"name", "description", "inputSchema"})

    def test_unknown_tool_raises(self):
        kit = make_kit(lambda a: {})
        with self.assertRaises(RpcError) as ctx:
            call_tool(kit, "nope", {})
        self.assertEqual(ctx.exception.code, INVALID_PARAMS)


class RunWithLockTests(unittest.TestCase):
    def test_handler_value_returned(self):
        kit = make_kit(lambda a: {"ok": True, "reads": {"n": 1}})
        r = call_tool(kit, "t_echo", {})
        self.assertTrue(r["ok"])
        self.assertEqual(r["reads"], {"n": 1})

    def test_handler_exception_becomes_error(self):
        def boom(_a):
            raise RuntimeError("nope")
        kit = make_kit(boom)
        r = call_tool(kit, "t_echo", {})
        self.assertFalse(r["ok"])
        self.assertIn("RuntimeError", r["errors"][0])

    def test_timeout_reported(self):
        def slow(_a):
            time.sleep(1.0)
            return {"ok": True}
        kit = make_kit(slow, timeout_s=0.2)
        started = time.time()
        r = call_tool(kit, "t_echo", {})
        elapsed = time.time() - started
        self.assertFalse(r["ok"])
        self.assertIn("超时", r["errors"][0])
        self.assertLess(elapsed, 0.9)          # 没有陪着等满 1s

    def test_calls_are_serialized(self):
        active = {"now": 0, "max": 0}
        guard = threading.Lock()

        def handler(_a):
            with guard:
                active["now"] += 1
                active["max"] = max(active["max"], active["now"])
            time.sleep(0.15)
            with guard:
                active["now"] -= 1
            return {"ok": True}

        kit = make_kit(handler, timeout_s=5.0)
        threads = [threading.Thread(target=lambda: call_tool(kit, "t_echo", {}))
                   for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(active["max"], 1, "同一个 kit 的调用必须串行")

    def test_stdout_is_redirected(self):
        # 有些 runner 会 print()，绝不能污染协议流
        def noisy(_a):
            print("noise on stdout")
            return {"ok": True}
        kit = make_kit(noisy)
        r = call_tool(kit, "t_echo", {})
        self.assertTrue(r["ok"])


class IdempotencyTests(unittest.TestCase):
    """request_id 幂等：重试不能重复产生副作用。"""

    def test_second_call_is_replayed(self):
        counter = {"n": 0}

        def handler(_a):
            counter["n"] += 1
            return {"ok": True, "reads": {"run": counter["n"]}, "checks": []}

        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_bump", "bump", EMPTY, handler, timeout_s=5, idempotent=True))
        first = call_tool(kit, "t_bump", {"request_id": "abc"})
        second = call_tool(kit, "t_bump", {"request_id": "abc"})
        self.assertTrue(first["ok"])
        self.assertEqual(counter["n"], 1, "同 request_id 不应执行第二次")
        self.assertTrue(second.get("replayed"))
        self.assertEqual(second["reads"]["run"], 1)

    def test_different_request_id_runs_again(self):
        counter = {"n": 0}

        def handler(_a):
            counter["n"] += 1
            return {"ok": True, "reads": {}, "checks": []}

        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_bump", "bump", EMPTY, handler, timeout_s=5, idempotent=True))
        call_tool(kit, "t_bump", {"request_id": "a"})
        call_tool(kit, "t_bump", {"request_id": "b"})
        self.assertEqual(counter["n"], 2)

    def test_non_idempotent_ignores_request_id(self):
        counter = {"n": 0}

        def handler(_a):
            counter["n"] += 1
            return {"ok": True, "reads": {}, "checks": []}

        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_bump", "bump", EMPTY, handler, timeout_s=5))
        call_tool(kit, "t_bump", {"request_id": "x"})
        call_tool(kit, "t_bump", {"request_id": "x"})
        self.assertEqual(counter["n"], 2)


class ValidationTests(unittest.TestCase):
    def test_schema_type_mismatch(self):
        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_num", "num",
                         {"type": "object", "properties": {"n": {"type": "number"}}},
                         lambda a: {"ok": True}, timeout_s=5))
        r = call_tool(kit, "t_num", {"n": "not-a-number"})
        self.assertFalse(r["ok"])
        self.assertIn("must be", r["errors"][0])

    def test_schema_required_missing(self):
        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_req", "req",
                         {"type": "object", "required": ["path"],
                          "properties": {"path": {"type": "string"}}},
                         lambda a: {"ok": True}, timeout_s=5))
        r = call_tool(kit, "t_req", {})
        self.assertFalse(r["ok"])
        self.assertIn("path is required", r["errors"][0])

    def test_custom_validator(self):
        from nsa_mcp_hub.contracts import require_positive

        def validate(args):
            require_positive(args.get("size", 0), "size")

        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_size", "size",
                         {"type": "object", "properties": {"size": {"type": "number"}}},
                         lambda a: {"ok": True}, timeout_s=5, validator=validate))
        self.assertFalse(call_tool(kit, "t_size", {"size": -1})["ok"])
        self.assertIn("size must be > 0", call_tool(kit, "t_size", {"size": -1})["errors"][0])
        self.assertTrue(call_tool(kit, "t_size", {"size": 2})["ok"])


class MustHaveChecksTests(unittest.TestCase):
    def test_empty_checks_fails(self):
        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_nocheck", "x", EMPTY,
                         lambda a: {"ok": True, "checks": []},
                         timeout_s=5, must_have_checks=True))
        r = call_tool(kit, "t_nocheck", {})
        self.assertFalse(r["ok"])
        self.assertIn("checks 为空", r["errors"][-1])

    def test_with_checks_passes(self):
        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_check", "x", EMPTY,
                         lambda a: {"ok": True, "checks": [{"check": "c", "ok": True}]},
                         timeout_s=5, must_have_checks=True))
        self.assertTrue(call_tool(kit, "t_check", {})["ok"])


class RuntimeToolTests(unittest.TestCase):
    def test_runtime_does_not_block(self):
        kit = make_kit(lambda a: {"ok": True})
        kit.lock.acquire()          # 模拟一个长任务占着锁
        try:
            r = call_tool(kit, "kit_runtime", {})
        finally:
            kit.lock.release()
        self.assertTrue(r["ok"])
        self.assertTrue(r["reads"]["busy"], "锁被占时应报 busy=True")

    def test_stats_count_calls(self):
        kit = make_kit(lambda a: {"ok": True, "checks": []})
        call_tool(kit, "t_echo", {})
        r = call_tool(kit, "kit_runtime", {})
        self.assertGreaterEqual(r["reads"]["calls"], 1)
        self.assertEqual(r["reads"]["last_tool"], "t_echo")


class StuckGuardTests(unittest.TestCase):
    """超时后 worker 还在跑 → 后续调用必须被挡住，而不是继续堆任务。"""

    def test_timeout_then_blocked(self):
        started = threading.Event()

        def slow(_a):
            started.set()
            time.sleep(1.2)
            return {"ok": True, "checks": []}

        kit = Kit(key="t", name="t")
        kit.add(ToolSpec("t_slow", "x", EMPTY, slow, timeout_s=0.2))
        first = call_tool(kit, "t_slow", {})
        self.assertFalse(first["ok"])
        self.assertTrue(first.get("stuck"), "超时应标记 stuck")
        second = call_tool(kit, "t_slow", {})
        self.assertFalse(second["ok"])
        self.assertIn("仍在后台运行", second["errors"][0])
        # 等 worker 结束后，标记应被清掉，别的工具可以正常调
        time.sleep(1.4)
        self.assertEqual(kit.stuck_tools(), [], "worker 结束后不该再有卡住记录")
        kit.add(ToolSpec("t_fast", "x", EMPTY,
                         lambda a: {"ok": True, "checks": []}, timeout_s=2))
        self.assertTrue(call_tool(kit, "t_fast", {})["ok"])


class FileLockTests(unittest.TestCase):
    """跨进程文件锁：另一个进程占着锁时，调用要明确报错。"""

    def test_lock_held_elsewhere(self):
        from nsa_mcp_hub.tools import _FileLock
        path = os.path.join(tempfile.mkdtemp(prefix="nsa_mcp_hub_test_lock_"), "x.lock")
        holder = _FileLock(path)
        self.assertTrue(holder.acquire(1.0))
        try:
            kit = Kit(key="t", name="t", lock_path=path)
            kit.add(ToolSpec("t_x", "x", EMPTY,
                             lambda a: {"ok": True, "checks": []}, timeout_s=0.3))
            r = call_tool(kit, "t_x", {})
            self.assertFalse(r["ok"])
            self.assertIn("另一个进程", r["errors"][0])
        finally:
            holder.release()
        kit2 = Kit(key="t", name="t", lock_path=path)
        kit2.add(ToolSpec("t_x", "x", EMPTY,
                          lambda a: {"ok": True, "checks": []}, timeout_s=2))
        self.assertTrue(call_tool(kit2, "t_x", {})["ok"])


if __name__ == "__main__":
    unittest.main()

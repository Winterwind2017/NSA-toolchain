"""验收框架：用 MCP 协议驱动各 kit 服务器，跑固定用例并核对期望值。

设计原则：
- **走真实链路**：启动 `python -m nsa_mcp_hub.servers.<kit>_mcp`，用 MCP 调工具，
  而不是直接 import 适配器函数——这样协议层、超时、判据归一化都被覆盖。
- **用例是数据**：每条用例 = 工具名 + 参数 + 期望（checks 值 / reads 路径）。
- **失败要能定位**：打印期望 vs 实测，退出码非 0。
"""

from __future__ import annotations

import collections
import json
import math
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --------------------------------------------------------------------- 客户端
class McpClient:
    """最小 MCP stdio 客户端（newline-delimited JSON-RPC 2.0）。"""

    def __init__(self, module: str, env_extra: dict | None = None, timeout_s: float = 300):
        env = dict(os.environ)
        env["PYTHONPATH"] = ROOT + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["PYTHONIOENCODING"] = "utf-8"
        env.update(env_extra or {})
        self.module = module
        self.timeout_s = timeout_s
        self._id = 0
        # 记下拉起参数，restart() 要用同一套（含 env）
        self._spawn_args = [sys.executable, "-u", "-m", module]
        self._spawn_env = env
        self.proc = subprocess.Popen(
            self._spawn_args,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", env=env, cwd=ROOT)
        # **必须一直排空 stderr**：acadkit 这类 kit 每跑一条能力就往 stderr 写进度
        # （progress=lambda m: sys.stderr.write(...)）。管道缓冲区只有 ~64 KB，
        # 不读就写满 → 服务器进程卡在 write() 上 → 工具调用永不返回。
        # 实测症状：acad 组跑到第 12 条（projection）必"超时 120 s"，而单跑 9 s 就过。
        self._stderr_tail: "deque[str]" = collections.deque(maxlen=400)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self.handshake()

    def restart(self) -> None:
        """杀掉卡住的子进程并重新拉起（同一套参数/环境），然后重新握手。

        用途：某个工具调用在 NX 里挂死时，等待线程会一直抱着 stdout 管道，
        后续每次调用都会再卡一次（实测把 6 步流程拖成 300 s 超时）。
        `restart()` 把子进程换掉，旧线程读到 EOF 自然退出，kit 立刻恢复可用。
        """
        try:
            self.proc.kill()
        except Exception:                          # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:                          # noqa: BLE001
            pass
        self._stderr_tail.clear()
        self._id = 0
        self.proc = subprocess.Popen(
            self._spawn_args,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            env=self._spawn_env, cwd=ROOT)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self.handshake()

    def _drain_stderr(self) -> None:
        try:
            for line in self.proc.stderr:
                self._stderr_tail.append(line)
        except Exception:                          # noqa: BLE001
            pass

    def stderr_tail(self, limit: int = 600) -> str:
        return "".join(self._stderr_tail)[-limit:]

    def _send(self, payload: dict) -> None:
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            err = self.stderr_tail()
            raise RuntimeError("%s 无响应（退出码 %s）：%s" % (self.module, self.proc.poll(), err))
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method,
                    "params": params or {}})
        msg = self._read()
        if "error" in msg:
            raise RuntimeError("%s: %s" % (method, json.dumps(msg["error"], ensure_ascii=False)))
        return msg["result"]

    def notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def handshake(self) -> dict:
        result = self.request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "nsa-mcp-hub-acceptance", "version": "0.1"}})
        self.notify("notifications/initialized")
        return result

    def tools(self) -> list:
        return self.request("tools/list").get("tools") or []

    def call(self, name: str, args: dict | None = None) -> dict:
        result = self.request("tools/call", {"name": name, "arguments": args or {}})
        payload = result.get("structuredContent")
        if isinstance(payload, dict):
            return payload
        text = ""
        for block in result.get("content") or []:
            if block.get("type") == "text":
                text += block.get("text") or ""
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"text": text}
        except Exception:                              # noqa: BLE001
            return {"text": text, "isError": result.get("isError")}

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:                              # noqa: BLE001
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:                              # noqa: BLE001
            try:
                self.proc.kill()
            except Exception:                      # noqa: BLE001
                pass


# ------------------------------------------------------------------- 期望判定
_SEG_RE = None


def _split_path(path: str) -> list:
    """把 `a.b["c.d"].e` 拆成 ["a", "b", "c.d", "e"]——能力 id 里带点，必须支持引号段。"""
    import re
    parts = []
    i = 0
    buf = ""
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if buf:
                parts.append(buf)
                buf = ""
            i += 1
        elif ch == "[":
            if buf:
                parts.append(buf)
                buf = ""
            j = path.find("]", i)
            if j < 0:
                buf += path[i:]
                break
            inner = path[i + 1:j].strip().strip("'\"")
            parts.append(inner)
            i = j + 1
        else:
            buf += ch
            i += 1
    if buf:
        parts.append(buf)
    return parts


def _dig(payload: dict, path: str):
    node = payload
    for part in _split_path(path):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return _MISSING
    return node


class _Missing:
    def __repr__(self) -> str:
        return "<缺失>"


_MISSING = _Missing()


def _equal(got, want, tol: float = 1e-3) -> bool:
    if isinstance(want, bool) or isinstance(got, bool):
        return bool(got) == bool(want)
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return math.isclose(float(got), float(want), rel_tol=tol, abs_tol=tol)
    if isinstance(want, list) and isinstance(got, list):
        return len(got) == len(want) and all(_equal(g, w, tol) for g, w in zip(got, want))
    return got == want


REFUSE_CODES_DEFAULT = (
    "ENV", "NOT_ATTACHED", "UNAVAILABLE", "INVALID", "NOT_FOUND", "MISSING",
    "HELP_INDEX_NOT_BUILT", "no_instance", "NO_INSTANCE", "backend error",
    "未运行", "不可用", "未连接", "不存在", "ECOM", "DISPATCH",
)


def error_text(payload: dict) -> str:
    """把 payload 里所有像错误码/错误信息的东西拼成一段文本。

    三种来源都收：`errors`（字符串或 dict 列表）、`reads.error`（字符串或
    `{code,message}`）、顶层 `error`。拒绝断言就靠它做匹配。
    """
    parts: list[str] = []
    errors = payload.get("errors")
    if isinstance(errors, str):
        parts.append(errors)
    elif isinstance(errors, list):
        for item in errors:
            parts.append(item if isinstance(item, str)
                         else json.dumps(item, ensure_ascii=False))
    reads = payload.get("reads")
    if isinstance(reads, dict):
        for key in ("error", "error_code", "code"):
            value = reads.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                parts.append(json.dumps(value, ensure_ascii=False))
    for key in ("error", "code"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            parts.append(json.dumps(value, ensure_ascii=False))
    return " | ".join(part for part in parts if part)


def refusal_evidence(payload: dict) -> str | None:
    """ok=False 时必须有"为什么"的证据；没有就是静默失败，拒绝断言不该放过。"""
    if payload.get("ok"):
        return None
    text = error_text(payload)
    if text.strip():
        return text
    checks = [c for c in (payload.get("checks") or []) if isinstance(c, dict)]
    failed = [str(c.get("check")) for c in checks if not c.get("ok")]
    if failed:
        return "失败判据：" + ", ".join(failed)
    return None


def evaluate(case: dict, payload: dict) -> list:
    """返回失败列表；空列表 = 通过。"""
    failures = []
    if case.get("expect_ok", True) and not payload.get("ok"):
        failures.append("ok=%r（期望 True）；errors=%s"
                        % (payload.get("ok"), str(payload.get("errors"))[:200]))

    checks = {c.get("check"): c for c in (payload.get("checks") or []) if isinstance(c, dict)}
    for name, want in (case.get("expect_checks") or {}).items():
        item = checks.get(name)
        if item is None:
            failures.append("缺少判据 %r（实际有 %s）" % (name, ", ".join(checks) or "无"))
        elif not _equal(item.get("got"), want, case.get("tol", 1e-3)):
            failures.append("判据 %s: got=%r want=%r" % (name, item.get("got"), want))

    for name in case.get("expect_check_true") or []:
        item = checks.get(name)
        if item is None or not item.get("ok"):
            failures.append("判据 %s 未通过（%r）" % (name, None if item is None else item.get("got")))

    for path, want in (case.get("expect_reads") or {}).items():
        got = _dig(payload, path)
        if got is _MISSING:
            failures.append("reads 缺路径 %s" % path)
        elif not _equal(got, want, case.get("tol", 1e-3)):
            failures.append("reads.%s: got=%r want=%r" % (path, got, want))

    for path, factor in (case.get("expect_ratio") or {}).items():
        # {"reads.geometry_after.volume_mm3 / reads.geometry_before.volume_mm3": 1.6}
        left, _, right = path.partition(" / ")
        a, b = _dig(payload, left), _dig(payload, right)
        if a is _MISSING or b is _MISSING or not b:
            failures.append("比值基数缺失：%s=%r %s=%r" % (left, a, right, b))
        elif not math.isclose(float(a) / float(b), float(factor), rel_tol=1e-3):
            failures.append("比值 %s/%s = %.6f（期望 %.6f）"
                            % (left, right, float(a) / float(b), float(factor)))

    for path, spec in (case.get("expect_between") or {}).items():
        got = _dig(payload, path)
        low, high = spec
        if got is _MISSING or not (low <= float(got) <= high):
            failures.append("reads.%s = %r（期望在 [%s, %s]）" % (path, got, low, high))

    # 明确拒绝：ok 必须为假，且必须给出证据（不能静默失败）
    if case.get("expect_refusal"):
        if payload.get("ok"):
            failures.append("期望明确拒绝，但 ok=True")
        else:
            evidence = refusal_evidence(payload)
            if evidence is None:
                failures.append("ok=False 但没有任何错误证据（errors / reads.error 都为空）")

    codes = case.get("expect_error_code")
    if codes:
        text = error_text(payload)
        wanted = codes if isinstance(codes, (list, tuple)) else [codes]
        if not any(str(code) in text for code in wanted):
            failures.append("错误码不匹配：期望其中之一 %s，实际 %r"
                            % (list(wanted), text[:200]))

    minimum = case.get("expect_min_checks")
    if minimum is not None and len(checks) < minimum:
        failures.append("判据条数 %d < %d" % (len(checks), minimum))
    return failures


# --------------------------------------------------------------------- 运行器
def _run_cleanup(case: dict, spec: dict, client, context: dict, verbose: bool) -> None:
    """每条用例后恢复基线。用例级 cleanup 优先，其次是 kit 级 cleanup。

    写类用例必须提供 cleanup（关新建文档 / 删沙箱工程），否则会污染后续用例；
    这里允许它抛异常——只警告，不把原本的判据结果带崩。
    """
    hook = case.get("cleanup") or spec.get("cleanup")
    if not hook:
        return
    try:
        hook(client, context)
    except Exception as exc:                       # noqa: BLE001
        if verbose:
            print("  [warn] cleanup 失败：%s: %s" % (type(exc).__name__, str(exc)[:160]),
                  flush=True)


def run_kit(kit_key: str, spec: dict, *, only: list | None = None,
            verbose: bool = True) -> dict:
    """跑一个 kit 的全部用例，返回汇总。"""
    started = time.time()
    setup = spec.get("setup")
    context = {}
    results = []
    pending: list = []
    client = None
    try:
        if setup:
            context = setup() or {}
        # setup 说环境不可用（软件没开/没装）→ 整组跳过，绝不硬跑
        if setup and context.get("available") is False:
            for case in spec["cases"]:
                if only and case["id"] not in only:
                    continue
                # 纯计算类用例（例如不碰 COM 的 Feature Graph 生成器）不该因为
                # CAD 没开而被跳过：用 no_setup 标记放行。
                # 纯计算（no_setup）和带 requires 的用例都放行：后者在主循环里
                # 会降级成"明确拒绝"断言，而不是 SKIP（SKIP 不计覆盖）。
                if case.get("no_setup") or case.get("requires"):
                    pending.append(case)
                    continue
                results.append({"kit": kit_key, "id": case["id"],
                                "title": case.get("title", ""), "verdict": "SKIP",
                                "ms": 0, "detail": "环境不可用（setup 报不可用），整组跳过"})
                if verbose:
                    print("  %-4s %-28s %5d ms  %s"
                          % ("SKIP", case["id"], 0, "环境不可用"), flush=True)
            # 纯计算类用例（no_setup）放行；一条都没有才整组收工
            if not pending:
                return {"kit": kit_key, "results": results, "passed": 0,
                        "skipped": len(results), "total": len(results),
                        "seconds": round(time.time() - started, 1)}

        client = McpClient(spec["module"])
        tool_names = {t.get("name") for t in client.tools()}
        # setup 不可用时只跑放行的那些；否则跑全部
        for case in (pending if pending else spec["cases"]):
            if only and case["id"] not in only:
                continue
            row = {"kit": kit_key, "id": case["id"], "title": case.get("title", ""),
                   "tool": case.get("tool"), "mode": "normal"}
            skip_if = case.get("skip_if")
            if skip_if and skip_if(context):
                row.update(verdict="SKIP", ms=0, detail="前置条件不满足，已跳过")
                results.append(row)
                if verbose:
                    print("  %-4s %-28s %5d ms  %s" % ("SKIP", row["id"], 0, row["detail"]),
                          flush=True)
                continue
            # requires：依赖的软件/能力不在时，不 SKIP（SKIP 不计覆盖），而是降级成
            # "明确拒绝"断言——工具被真的调到了，且必须给出拒绝证据。
            unmet = [name for name in (case.get("requires") or [])
                     if not context.get(name)]
            effective = case
            if unmet:
                row["mode"] = "refusal"
                row["unmet"] = unmet
                # 保留 tool/call/args/timeout（否则调不动），只把"期望"换成拒绝断言
                effective = dict(case)
                for key in ("expect_checks", "expect_check_true", "expect_reads",
                            "expect_ratio", "expect_between", "expect_min_checks"):
                    effective.pop(key, None)
                effective["expect_ok"] = False
                effective["expect_refusal"] = True

            if effective.get("call") is None and effective.get("tool") and \
                    effective["tool"] not in tool_names:
                row.update(verdict="FAIL", ms=0,
                           detail="工具不存在：%s" % case["tool"])
                results.append(row)
                continue
            prepare = case.get("prepare")
            if effective.get("call") is not None:
                args = None
            elif prepare is not None:
                try:
                    args = prepare(client)
                except Exception as exc:               # noqa: BLE001
                    row.update(verdict="ERROR", ms=0,
                               detail="prepare 失败：%s: %s" % (type(exc).__name__, str(exc)[:200]))
                    results.append(row)
                    continue
            else:
                args = effective.get("args", {})
                if callable(args):
                    args = args(context)
            t0 = time.time()
            timeout_s = float(effective.get("timeout_s") or 300)
            box = {}

            def _invoke():
                try:
                    hook = effective.get("call")
                    if hook is not None:
                        box["payload"] = hook(client, context)
                    else:
                        box["payload"] = client.call(effective["tool"], args)
                except Exception as exc:               # noqa: BLE001
                    box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:300])

            worker = threading.Thread(target=_invoke, daemon=True)
            worker.start()
            worker.join(timeout_s)
            if worker.is_alive():
                verdict = "XFAIL" if case.get("xfail") else "TIMEOUT"
                row.update(verdict=verdict, ms=int((time.time() - t0) * 1000),
                           detail=("已知问题：%s" % case["xfail"]) if case.get("xfail")
                           else "单条用例超过 %.0f s，已放弃并重启该 kit 服务器" % timeout_s)
                results.append(row)
                if verbose:
                    print("  %-4s %-28s %5d ms  %s" % ("TIMEOUT", row["id"], row["ms"],
                                                       row["detail"]), flush=True)
                _run_cleanup(case, spec, client, context, verbose)
                try:
                    client.close()
                except Exception:                      # noqa: BLE001
                    pass
                client = McpClient(spec["module"])
                continue
            try:
                if "error" in box:
                    raise RuntimeError(box["error"])
                payload = box["payload"]
                failures = evaluate(effective, payload)
                if failures and case.get("xfail"):
                    verdict = "XFAIL"
                    detail = "已知问题：%s" % case["xfail"]
                else:
                    verdict = "PASS" if not failures else "FAIL"
                    detail = "; ".join(failures)[:400] or case.get("note", "")
                # 剧本用例（call 钩子）把子步骤也记下来，覆盖率才能算到工具级
                steps = (payload.get("reads") or {}).get("steps") if isinstance(payload, dict) else None
                covered = [s.get("tool") for s in steps
                           if isinstance(s, dict) and s.get("ok")] if isinstance(steps, list) else None
                row.update(verdict=verdict, ms=int((time.time() - t0) * 1000),
                           detail=detail, checks=len(payload.get("checks") or []))
                if covered:
                    row["covered_tools"] = covered
            except Exception as exc:                   # noqa: BLE001
                row.update(verdict="ERROR", ms=int((time.time() - t0) * 1000),
                           detail="%s: %s" % (type(exc).__name__, str(exc)[:300]))
            results.append(row)
            if verbose:
                print("  %-4s %-28s %5d ms  %s"
                      % (row["verdict"], row["id"], row["ms"], row["detail"]), flush=True)
            _run_cleanup(case, spec, client, context, verbose)
            between = spec.get("between")
            if between:
                try:
                    between(context)
                except Exception as exc:               # noqa: BLE001
                    print("  [warn] between 失败：%s" % exc, flush=True)
    finally:
        if client is not None:
            client.close()
        teardown = spec.get("teardown")
        if teardown:
            try:
                teardown(context)
            except Exception as exc:                   # noqa: BLE001
                print("  [warn] teardown 失败：%s" % exc, flush=True)

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    xfailed = sum(1 for r in results if r["verdict"] == "XFAIL")
    skipped = sum(1 for r in results if r["verdict"] == "SKIP")
    return {"kit": kit_key, "results": results, "passed": passed, "skipped": skipped, "xfailed": xfailed,
            "total": len(results), "seconds": round(time.time() - started, 1)}


def print_summary(summary: dict) -> None:
    skipped = summary.get("skipped", 0)
    print("\n%s：%d/%d 通过%s（%.1fs）"
          % (summary["kit"], summary["passed"], summary["total"],
             ("，%d 跳过" % skipped) if skipped else "", summary["seconds"]))
    bad = [r for r in summary["results"] if r["verdict"] in ("FAIL", "ERROR", "TIMEOUT")]
    if bad:
        print("  失败项：")
        for r in bad:
            print("    - %s [%s] %s" % (r["id"], r["verdict"], r["detail"]))

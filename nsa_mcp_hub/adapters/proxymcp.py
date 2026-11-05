"""通用"MCP 代理"适配器：把任意 stdio MCP 服务器接进统一内核。

用于 ug（Siemens NX 的 CAM/机床/钣金套件）和 catia（CATIA V5 建模 + 原生 Analysis）：
这两个上游服务器本身是完整实现（UG 的 server.py 55 KB、nx_remote_ops.py 457 KB；
CATIA 的 modeling/simulation/surfaces 三个模块），重写没有意义，代理即可——
工具名统一加前缀、返回统一成 `{ok, kit, capability, reads, checks, errors}`，
并把上游自带的 checks（如果有）抬上来当判据。
"""

from __future__ import annotations

import os
import sys

from ..jsonrpc import log
from ..mcpclient import ChildMcp, unwrap
from ..tools import Kit, ToolSpec, apply_checks, normalize


def _schema_for(tool: dict) -> dict:
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    if not isinstance(schema, dict) or schema.get("type") != "object":
        schema = {"type": "object", "properties": {}, "additionalProperties": True}
    return schema


def build_proxy_kit(*, key: str, name: str, argv: list, cwd: str,
                    env_extra: dict | None = None, instructions: str = "",
                    prefix: str | None = None, timeout_s: float = 3600.0,
                    prelude: str | None = None) -> Kit:
    """起一个子 MCP 服务器，把它的工具面整体代理进本 kit。

    prefix 为空表示沿用上游原名（上游已经自带前缀时用）。
    prelude：初始化失败时给用户的提示（例如"CATIA 没装"）。
    """
    kit = Kit(key=key, name=name, version="proxy", instructions=instructions)
    child: ChildMcp | None = None
    remote: list = []
    try:
        child = ChildMcp(argv, name="%s-mcp" % key, env_extra=env_extra or {}, cwd=cwd)
        child.initialize()
        remote = child.list_tools()
        log("%s 代理已接上上游 %d 个工具" % (key, len(remote)))
    except Exception as exc:                           # noqa: BLE001
        log("%s 代理启动失败：%s" % (key, exc))
        detail = str(exc)[:400]
        if prelude:
            detail = prelude + " | " + detail
        kit.add(ToolSpec("%s_unavailable" % (prefix or key),
                         "%s 的上游 MCP 起不来，返回诊断信息。" % name,
                         {"type": "object", "properties": {},
                          "additionalProperties": False},
                         lambda _a: normalize(key, "unavailable", ok=False,
                                              errors=[detail]),
                         timeout_s=30))
        return kit

    def make_handler(remote_name: str):
        def handler(args: dict) -> dict:
            result = child.call_tool(remote_name, args or {})
            payload, is_error = unwrap(result)
            payload["remote_tool"] = remote_name

            inner = payload.get("result")
            if not isinstance(inner, dict):
                inner = payload

            checks = [{"check": "backend_ok", "got": not is_error,
                       "want": True, "ok": not is_error}]
            # 上游给了自己的 `ok` 时，它的 `checks` 只是**说明性**的：上游已经把
            # "object_created and (segments_increased or text_matches)" 这类
            # 取舍算进 ok 了，这里再要求每个 check 都为真会把 ok 翻回 false
            # （实测 sw_sketch_text：上游 ok=true，但 text_matches 单项 false）。
            backend_verdict = inner.get("ok")
            informative = isinstance(backend_verdict, bool)
            inner_checks = inner.get("checks")
            if isinstance(inner_checks, dict):
                for ck, value in inner_checks.items():
                    checks.append({"check": ck, "want": True,
                                   "ok": True if informative else bool(value),
                                   "got": bool(value),
                                   "informational": informative})
            elif isinstance(inner_checks, list):
                for item in inner_checks:
                    if isinstance(item, dict):
                        if informative:
                            item = dict(item)
                            item.setdefault("got", item.get("ok"))
                            item["ok"] = True
                            item["informational"] = True
                        checks.append(item)

            reads = inner.get("detail") if isinstance(inner.get("detail"), dict) else {}
            if not reads:
                reads = {k: v for k, v in inner.items()
                         if k not in ("ok", "checks", "tool", "api", "result")}
                if isinstance(inner.get("result"), dict):
                    reads["result"] = inner["result"]

            if not is_error and inner.get("ok", True):
                errors = []
            else:
                text = str(payload.get("text") or inner.get("error") or "").strip()
                if not text:
                    # 上游只回 ok=false 不给原因时，尽量把它的解释性字段抬上来
                    bits = []
                    for field in ("message", "reason", "failure_reason", "blocking_reason"):
                        if inner.get(field):
                            bits.append(str(inner[field])[:140])
                    # 结构化阻塞项：ug/机床校验这类工具只回 ok=false + blockers，
                    # 不抬上来调用方只会看到"后端未给出原因"（实测就是这个坑）。
                    for field in ("blockers", "remaining_blockers",
                                  "missing_channel_axis_assignments",
                                  "missing_expected_axes", "missing_components"):
                        value = inner.get(field)
                        if isinstance(value, list) and value:
                            bits.append("%s=%s" % (field, ",".join(
                                str(item) for item in value[:6])))
                    gen = inner.get("generation_results")
                    if isinstance(gen, list):
                        for item in gen[:3]:
                            if isinstance(item, dict) and item.get("result") != "success":
                                bits.append("%s: %s %s" % (
                                    item.get("operation_name") or "?",
                                    item.get("result"),
                                    str(item.get("error") or item.get("result_value")
                                        or "")[:90]))
                    if bits:
                        text = "；".join(bits)[:360]
                    else:
                        # swkit 这类上游把原因放在 reads.error / reads.detail.error 里
                        for field in ("error", "detail", "message"):
                            value = reads.get(field)
                            if isinstance(value, str) and value.strip():
                                bits.append(value.strip()[:160])
                            elif isinstance(value, dict):
                                inner_err = value.get("error")
                                if isinstance(inner_err, str) and inner_err.strip():
                                    bits.append(inner_err.strip()[:160])
                        if bits:
                            text = "；".join(bits)[:360]
                    if not bits:
                        bad = [c.get("check") for c in checks
                               if isinstance(c, dict)
                               and (c.get("ok") is False or c.get("got") is False)
                               and c.get("check") != "backend_ok"]
                        text = ("后端判据未通过：%s" % "、".join(str(x) for x in bad[:4])
                                if bad else "backend error（后端未给出原因）")
                errors = [text[:400]]

            return apply_checks(
                normalize(key, remote_name,
                          ok=bool(not is_error and inner.get("ok", True)),
                          reads=reads, errors=errors), checks)
        return handler

    for tool in remote:
        remote_name = tool.get("name") or ""
        if not remote_name:
            continue
        local = remote_name
        if prefix and not remote_name.startswith(prefix + "_"):
            local = "%s_%s" % (prefix, remote_name)
        kit.add(ToolSpec(local,
                         (tool.get("description") or "").strip()
                         or ("%s: %s" % (name, remote_name)),
                         _schema_for(tool),
                         make_handler(remote_name),
                         timeout_s=timeout_s,
                         must_have_checks=True))

    kit.add(ToolSpec("%s_proxy_tools" % (prefix or key),
                     "列出被代理的上游原始工具名（诊断用）。",
                     {"type": "object", "properties": {},
                      "additionalProperties": False},
                     lambda _a: normalize(key, "proxy_tools", ok=True,
                                          reads={"count": len(remote),
                                                 "tools": [t.get("name") for t in remote]}),
                     timeout_s=30))
    return kit


def venv_python(root: str) -> str:
    """优先用 CAD-Agent-Hub 自带的 venv（里面有 mcp / pywin32）。"""
    cand = os.path.join(root, ".venv", "Scripts", "python.exe")
    return cand if os.path.isfile(cand) else sys.executable

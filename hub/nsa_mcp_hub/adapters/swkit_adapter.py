"""swkit 适配器（代理模式）：把现有 SolidWorks MCP 服务器的工具面接进统一内核。

为什么不重写：swkit 的工具面有 40 个、56.9 KB 的 server.py 已经在跑并验证过；
代理能在**不改它一行**的前提下统一命名与返回结构。
"""

from __future__ import annotations

import os
import sys

from ..jsonrpc import log
from ..mcpclient import ChildMcp, unwrap
from ..tools import Kit, ToolSpec, apply_checks, normalize
from .. import paths

KIT_KEY = "sw"
KIT_NAME = "swkit"
SRC = paths.src_dir("sw")


def _spawn() -> ChildMcp:
    env = {"PYTHONPATH": SRC + (os.pathsep + os.environ["PYTHONPATH"]
                                if os.environ.get("PYTHONPATH") else "")}
    return ChildMcp([sys.executable, "-m", "swkit.mcp.server"],
                    name="swkit-mcp", env_extra=env)


def _schema_for(tool: dict) -> dict:
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    if not isinstance(schema, dict) or schema.get("type") != "object":
        schema = {"type": "object", "properties": {}, "additionalProperties": True}
    return schema


def build_kit() -> Kit:
    kit = Kit(key=KIT_KEY, name=KIT_NAME, version="proxy",
              instructions=("swkit：SolidWorks 2025 自动化。建模/装配/出图走 swkit MCP（代理），"
                            "分步 FEA / Motion 列表 / 批量扫描 / DocumentMgr 索引直接跑 "
                            "mcp-patches 脚本。返回统一为 {ok,reads,checks,errors}。"))

    remote_tools: list = []
    try:
        child = _spawn()
        child.initialize()
        remote_tools = child.list_tools()
    except Exception as exc:                         # noqa: BLE001
        log("swkit 代理启动失败：%s" % exc)
        kit.add(ToolSpec("sw_unavailable",
                         "swkit 代理不可用（子进程启动/握手失败），返回诊断。",
                         {"type": "object", "properties": {}, "additionalProperties": False},
                         lambda _a: normalize(KIT_KEY, "unavailable", ok=False,
                                              errors=[str(exc)]),
                         timeout_s=30))

    def make_handler(remote_name: str):
        def handler(args: dict) -> dict:
            result = child.call_tool(remote_name, args or {})
            payload, is_error = unwrap(result)
            payload["remote_tool"] = remote_name

            # swkit 的返回是 {"result": {ok, tool, api, detail, checks}}：
            # 它**自带**判据（如 version_readable / count_matches），代理层必须
            # 把它们抬上来，不能只留一个 backend_ok——否则等于把判据丢了。
            inner = payload.get("result")
            if not isinstance(inner, dict):
                inner = payload

            checks = [{"check": "backend_ok", "got": not is_error,
                       "want": True, "ok": not is_error}]
            # 上游给了自己的 `ok` 时，它的 `checks` 就是**说明性**的：swkit 已经把
            # "object_created and (segments_increased or text_matches)" 这类取舍
            # 算进 ok 了。代理层再要求每个 check 都为真，会把 ok 翻回 false
            # （实测 sw_sketch_text：后端 ok=true、text_matches=false、segments 0→1）。
            backend_verdict = inner.get("ok")
            informative = isinstance(backend_verdict, bool)
            inner_checks = inner.get("checks")
            if isinstance(inner_checks, dict):
                for key, value in inner_checks.items():
                    checks.append({"check": key, "want": True,
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
                         if k not in ("ok", "checks", "tool", "api")}

            if not is_error and inner.get("ok", True):
                errors = []
            else:
                text = str(payload.get("text") or inner.get("error") or "").strip()
                if not text:
                    # 后端只回 ok=false、不给原因时，用失败判据拼一条可读原因
                    bad = [c.get("check") for c in checks
                           if isinstance(c, dict)
                           and (c.get("ok") is False or c.get("got") is False)]
                    bad = [str(x) for x in bad if x]
                    if bad:
                        text = "后端判据未通过：%s" % "、".join(bad[:4])
                    else:
                        text = "backend error（后端未给出原因）"
                errors = [text[:400]]

            return apply_checks(
                normalize(KIT_KEY, remote_name,
                          ok=bool(not is_error and inner.get("ok", True)),
                          reads=reads, errors=errors),
                checks)
        return handler

    def remote_call(remote_name: str, call_args: dict) -> dict:
        """给 hub 侧组合工具用的最小代理调用器（只要 ok/reads/errors）。"""
        result = child.call_tool(remote_name, call_args or {})
        payload, is_error = unwrap(result)
        inner = payload.get("result")
        if not isinstance(inner, dict):
            inner = payload
        reads = inner.get("detail") if isinstance(inner.get("detail"), dict) else {}
        if not reads:
            reads = {k: v for k, v in inner.items()
                     if k not in ("ok", "checks", "tool", "api")}
        ok = bool(not is_error and inner.get("ok", True))
        errors = [] if ok else [str(payload.get("text") or inner.get("error")
                                    or "backend error")[:300]]
        return {"ok": ok, "reads": reads, "errors": errors}

    for tool in remote_tools:
        remote_name = tool.get("name") or ""
        if not remote_name:
            continue
        local = remote_name if remote_name.startswith("sw_") else "sw_" + remote_name
        kit.add(ToolSpec(local,
                         (tool.get("description") or "").strip() or ("swkit: %s" % remote_name),
                         _schema_for(tool),
                         make_handler(remote_name),
                         timeout_s=3600,
                         # 代理层**必然**给出 backend_ok 判据（见 make_handler），
                         # 所以"必须有判据"对每个代理工具都成立；这样 checks 非空
                         # 就从"实测如此"变成"内核强制"。
                         must_have_checks=True))

    kit.add(ToolSpec("sw_proxy_tools",
                     "列出被代理的 swkit 原始工具名（诊断用）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     lambda _a: normalize(KIT_KEY, "proxy_tools", ok=True,
                                          reads={"count": len(remote_tools),
                                                 "tools": [t.get("name") for t in remote_tools]}),
                     timeout_s=30))

    # 脚本类工具（分步 FEA / Motion 列表 / 批量扫描 / DocumentMgr 索引）：
    # 直接跑 mcp-patches\*.py，不依赖 swkit MCP 子进程是否起得来。
    from .sw_scripts import script_tools
    for spec in script_tools():
        kit.add(spec)

    # 融入自 CAD-Agent-Hub 的纯算法工具（齿轮/减速器/参数化零件/特征图编译）：
    # 不碰 COM，判据是数学，不需要开 SolidWorks。
    try:
        from .hubsw_tools import hubsw_tools
        for spec in hubsw_tools():
            kit.add(spec)
    except Exception as exc:                          # noqa: BLE001
        log("hubsw 工具加载失败：%s" % exc)

    # 特征树编辑（hub 的 interactive 层 + 我们自己的 COM 附加）：
    # 不启动 SolidWorks，只附加到已运行的实例读/改特征树。
    try:
        from .hubsw_feat import hubsw_feature_tools
        for spec in hubsw_feature_tools():
            kit.add(spec)
    except Exception as exc:                          # noqa: BLE001
        log("hubsw 特征工具加载失败：%s" % exc)

    # Phase 2：Feature Graph 执行（新零件里建模型 + 读回体积做判据）
    try:
        from .hubsw_exec import exec_tools
        for spec in exec_tools():
            kit.add(spec)
    except Exception as exc:                          # noqa: BLE001
        log("hubsw 执行工具加载失败：%s" % exc)

    # 选择类（草图线段/特征）：解锁 swkit 里"必须先选中"的那批工具
    try:
        from .hubsw_select import select_tools
        for spec in select_tools():
            kit.add(spec)
    except Exception as exc:                          # noqa: BLE001
        log("hubsw 选择工具加载失败：%s" % exc)

    # 装配链修复（先建装配 → 开零件 → 插组件）：绕开 swkit 要求零件预先打开
    try:
        from .hubsw_asm import asm_tools
        for spec in asm_tools(remote_call):
            kit.add(spec)
    except Exception as exc:                          # noqa: BLE001
        log("hubsw 装配工具加载失败：%s" % exc)

    # Phase 3：一步到位封装（plan + execute 缝成一次调用）
    try:
        from .hubsw_create import create_tools
        for spec in create_tools():
            kit.add(spec)
    except Exception as exc:                          # noqa: BLE001
        log("hubsw create 封装加载失败：%s" % exc)
    return kit

"""codesyskit 适配器：CODESYS 3.5 常驻服务（socket + token）的 MCP 外壳。

codesyskit 的执行模型和其它 kit 不同：IDE 里跑一个常驻服务（IronPython），
外部用换行分隔 JSON 走 socket；服务地址/token 写在 ``%LOCALAPPDATA%\\codesyskit\\service.json``。
所以这里不启动任何进程，只做转发。
"""

from __future__ import annotations

import os
import sys

from ..tools import Kit, ToolSpec, apply_checks, normalize

from . import codesys_tools

KIT_KEY = "codesys"
KIT_NAME = "codesyskit"
SRC = os.environ.get("CODESYSKIT_SRC", r"D:\bililive\codesyskit\src")

COMMANDS = {
    "ping": "往返检查（最轻量，先用它判断服务在不在）",
    "version": "服务与 IDE 版本",
    "projects": "列出已打开工程",
    "project.info": "当前工程信息",
    "project.create": "args: path, device?（新建工程）",
    "project.open": "args: path",
    "project.save": "args: path?",
    "tree": "args: path?, depth?（对象树）",
    "read": "args: path, part?（declaration/implementation）",
    "write": "args: path, part?, text",
    "find": "args: query, limit?（搜声明/实现）",
    "libs": "已引用与可用库",
    "export.xml": "PLCopenXML 导出",
    "import.xml": "PLCopenXML 导入",
    "archive": "整包归档",
    "compile": "编译并回读诊断",
}


def _import():
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    from codesyskit import client
    return client


def build_kit() -> Kit:
    client_mod = _import()
    kit = Kit(key=KIT_KEY, name=KIT_NAME, version="service",
              instructions=("codesyskit：CODESYS 3.5 自动化。执行走 IDE 内的常驻服务，"
                            "先用 codesys_status 确认服务在；具体命令用 codesys_call 转发。"))

    def _state_path(args: dict) -> str:
        return args.get("state_path") or client_mod.DEFAULT_STATE

    def status(args: dict) -> dict:
        path = _state_path(args)
        if not os.path.isfile(path):
            return apply_checks(
                normalize(KIT_KEY, "status", ok=False,
                          reads={"state_path": path},
                          errors=["找不到服务状态文件；先在 CODESYS 里"
                                  " codesyskit start 起常驻服务"]),
                [{"check": "service_reachable", "got": False, "want": True,
                  "ok": False}])
        try:
            state = client_mod.load_state(path)
        except Exception as exc:                    # noqa: BLE001
            return normalize(KIT_KEY, "status", ok=False,
                             errors=["状态文件读取失败：%s" % exc])
        reads = {"state_path": path, "port": state.get("port"),
                 "pid": state.get("pid"), "has_token": bool(state.get("token"))}
        try:
            # 注意：不能用 `with CodesysClient(...)`——它的 __exit__ 会发 quit，
            # 把常驻服务直接关掉（实测踩过）。这里只断开 socket，不停服务。
            c = client_mod.CodesysClient(state_path=path, timeout=15.0)
            try:
                reads["version"] = c.version()
                reads["ping"] = c.ping()
            finally:
                try:
                    c._disconnect()
                except Exception:                   # noqa: BLE001
                    pass
            return apply_checks(
                normalize(KIT_KEY, "status", ok=True, reads=reads),
                [{"check": "service_reachable", "got": True, "want": True, "ok": True},
                 {"check": "version_present", "got": bool(reads.get("version")),
                  "want": True, "ok": bool(reads.get("version"))},
                 {"check": "ping_ok", "got": bool(reads.get("ping")),
                  "want": True, "ok": bool(reads.get("ping"))}])
        except Exception as exc:                    # noqa: BLE001
            return apply_checks(
                normalize(KIT_KEY, "status", ok=False, reads=reads,
                          errors=["服务无响应：%s" % exc]),
                [{"check": "service_reachable", "got": False, "want": True,
                  "ok": False}])

    def call(args: dict) -> dict:
        cmd = (args.get("cmd") or "").strip()
        if not cmd:
            return normalize(KIT_KEY, "call", ok=False,
                             errors=["需要 cmd；可用：%s" % ", ".join(sorted(COMMANDS))])
        payload = args.get("args") or {}
        if not isinstance(payload, dict):
            return normalize(KIT_KEY, "call", ok=False, errors=["args 必须是对象"])
        timeout = float(args.get("timeout_s") or 120.0)
        try:
            c = client_mod.CodesysClient(state_path=_state_path(args), timeout=timeout)
            try:
                result = c.call(cmd, timeout_ms=int(timeout * 1000), **payload)
            finally:
                try:
                    c._disconnect()
                except Exception:                   # noqa: BLE001
                    pass
            # 判据只能是结构性的：服务回了、结果不是空的
            checks = [{"check": "result_present", "got": result is not None,
                       "want": True, "ok": result is not None}]
            if isinstance(result, dict) and "ok" in result:
                checks.append({"check": "service_ok", "got": result.get("ok"),
                               "want": True, "ok": bool(result.get("ok"))})
            return apply_checks(
                normalize(KIT_KEY, "call", ok=True,
                          reads={"cmd": cmd, "result": result}),
                checks)
        except Exception as exc:                    # noqa: BLE001
            return normalize(KIT_KEY, "call", ok=False,
                             reads={"cmd": cmd}, errors=["%s: %s" % (type(exc).__name__, exc)])

    def commands(_args: dict) -> dict:
        return normalize(KIT_KEY, "commands", ok=True,
                         reads={"commands": [{"cmd": k, "hint": v}
                                             for k, v in sorted(COMMANDS.items())]})

    kit.add(ToolSpec("codesys_status",
                     "检查常驻服务：状态文件、端口、ping、version。",
                     {"type": "object",
                      "properties": {"state_path": {"type": "string"}},
                      "additionalProperties": False},
                     status, timeout_s=90))
    kit.add(ToolSpec("codesys_commands", "列出常推荐的 services 命令与参数提示。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     commands, timeout_s=30))
    kit.add(ToolSpec("codesys_call",
                     "转发一条命令到 IDE 常驻服务（cmd + args），返回服务原始结果。",
                     {"type": "object",
                      "properties": {"cmd": {"type": "string",
                                             "description": "如 project.info / tree / read"},
                                     "args": {"type": "object"},
                                     "timeout_s": {"type": "number"},
                                     "state_path": {"type": "string"}},
                      "required": ["cmd"], "additionalProperties": False},
                     call, timeout_s=600))
    # ── P4：服务命令 → 工具（带数字判据，见 codesys_tools.py）──────────
    def _call_raw(cmd: str, payload: dict) -> object:
        """给 codesys_tools 用的"只要原始 result"的通道。"""
        c = client_mod.CodesysClient(state_path=_state_path({"args": payload}), timeout=180.0)
        try:
            return c.call(cmd, timeout_ms=180000, **payload)
        finally:
            try:
                c._disconnect()
            except Exception:                   # noqa: BLE001
                pass

    kit.tools.extend(codesys_tools.build_tools(_call_raw, prefix=KIT_KEY, timeout_s=300.0))

    return kit

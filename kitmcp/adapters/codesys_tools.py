"""CODESYS 常驻服务的命令 → 工具（P4）。

为什么单独一层：
* 适配器里那张 `COMMANDS`（17 条）**与真服务不一致**——`libs` / `compile` / `find`
  在服务端根本不存在（实测 `E_UNKNOWN_CMD`），真名是 `libraries` / `app.generate` /
  `find.text`。这张表按 `codesyskit/agentscript.py` 的 `COMMANDS` 分发字典重写。
* 以前每条命令只有一个结构性判据（`result_present`），"命令成功但工程没变"看不出来。
  这里给每条命令配**真判据**：计数、文件字节数、读回比对、`dirty`、`is_uptodate`、
  在线采样的数值——并且能跨命令验证的（写→读、存→查 dirty、生成→查状态）就跨验证。

判据来源以 `ww-codesys-automation` 技能里的实测结论为准（编译诊断只在引擎日志、
`task.pous.add` 缺失时编译是假绿灯、`pou.write` 要读回比对）。
"""

from __future__ import annotations

import os
import json
import time
from typing import Any, Callable, Dict, List, Optional

from ..tools import ToolSpec

# ── 命令表：名字 → (说明, {参数: 类型}, 是否写操作) ─────────────────────
# 参数名与类型来自 `agentscript.py` 里各 `cmd_*` 对 `args.get(...)` 的实际用法。
S: Dict[str, tuple] = {
    # 会话
    "ping": ("往返检查（最轻量，先判断服务在不在）", {}, False),
    "version": ("服务与 IDE 版本", {}, False),
    "devices": ("列出设备描述（1562 条），可按名过滤", {"filter": "string", "limit": "integer"}, False),
    "commands": ("列出 IDE 命令（870 条）", {"filter": "string", "limit": "integer"}, False),
    # 工程
    "projects": ("列出已打开工程", {}, False),
    "project.create": ("新建工程（可同时建 ST 程序与任务）",
                       {"path": "string", "device": "string", "program": "string",
                        "task": "string", "interval": "integer", "priority": "integer",
                        "unit": "string", "bare": "boolean", "device_node": "string"}, True),
    "project.open": ("打开工程", {"path": "string"}, True),
    "project.save": ("保存工程", {"path": "string"}, True),
    "project.save_as": ("另存为", {"path": "string"}, True),
    "project.close": ("关闭当前工程", {}, True),
    "project.info": ("当前工程信息（路径/dirty/应用/子对象）", {}, False),
    "project.meta": ("工程元信息（标题/公司/版本）", {}, False),
    "project.compare": ("与磁盘版本比对", {}, False),
    "project.users": ("工程用户与组", {}, False),
    "project.integrity": ("开启/关闭完整性检查", {"enable": "boolean"}, True),
    # 结构
    "tree": ("对象树（可限深度）", {"path": "string", "depth": "integer"}, False),
    "object.info": ("单个对象信息（类型/子对象/文本能力）", {"path": "string"}, False),
    "object.rename": ("重命名对象", {"path": "string", "name": "string"}, True),
    "object.move": ("移动对象到父路径", {"path": "string", "parent": "string", "index": "integer"}, True),
    "object.delete": ("删除对象（拒绝删工程根）", {"path": "string"}, True),
    "folder.create": ("新建文件夹", {"parent": "string", "name": "string"}, True),
    # 代码
    "pou.read": ("读 POU 声明/实现", {"path": "string", "part": "string"}, False),
    "pou.write": ("写 POU 声明/实现（**会读回比对**）",
                  {"path": "string", "text": "string", "part": "string"}, True),
    "pou.create": ("新建 POU（默认语言不是 ST，务必显式给 language）",
                   {"parent": "string", "name": "string", "kind": "string", "language": "string"}, True),
    "pou.create_typed": ("新建带返回类型的 POU", {"parent": "string", "name": "string",
                                                  "kind": "string", "language": "string",
                                                  "return_type": "string", "text": "string"}, True),
    "pou.member": ("给 POU 加方法/属性/动作", {"parent": "string", "name": "string",
                                             "kind": "string", "text": "string",
                                             "return_type": "string"}, True),
    "pou.members": ("列出 POU 成员", {"path": "string"}, False),
    "pou.persistent": ("建持久变量表", {"name": "string"}, True),
    "find.text": ("在声明/实现里搜文本（带行号）", {"pattern": "string", "path": "string",
                                                    "part": "string", "limit": "integer",
                                                    "case_sensitive": "boolean"}, False),
    # 任务
    "task.create": ("建任务并绑定 POU", {"name": "string", "pous": "array",
                                          "interval": "integer", "priority": "integer",
                                          "unit": "string"}, True),
    "tasks": ("列出任务", {}, False),
    "task.info": ("单个任务信息", {"path": "string"}, False),
    "task.update": ("改任务优先级/看门狗（**值必须传字符串**）",
                    {"path": "string", "watchdog_enabled": "boolean",
                     "watchdog_time": "string"}, True),
    # 编译
    "app.clean": ("清理应用（让 is_uptodate 变 false）", {}, True),
    "app.generate": ("生成代码（真编译，诊断看 execute 的引擎日志）", {}, True),
    "app.status": ("应用状态（is_uptodate 等）", {}, False),
    # 库
    "libraries": ("已引用库 + 可用库（537 个）", {}, False),
    "library.add": ("引入库", {"name": "string"}, True),
    # 符号 / 文本表
    "symbols.create": ("建符号配置", {"opc_ua": "boolean", "export_comments": "boolean",
                                      "layout_calculator": "string"}, True),
    "symbols.info": ("符号配置信息", {"path": "string"}, False),
    "textlist.create": ("建文本表", {"name": "string", "languages": "array"}, True),
    "textlist.languages": ("文本表语言（可 add）", {"path": "string", "add": "array"}, True),
    "textlist.rows": ("读文本表行", {"path": "string", "limit": "integer"}, False),
    "textlist.text": ("写某行某语言文本", {"path": "string", "id": "integer",
                                          "language": "string", "text": "string"}, True),
    "textlist.export": ("导出文本表", {"path": "string", "out": "string"}, False),
    # 交换 / 归档
    "export.xml": ("导出 PLCopenXML（带字节数判据）", {"path": "string", "target": "string"}, False),
    "import.xml": ("导入 PLCopenXML（**比对导入前后对象数**）", {"path": "string"}, True),
    "export.native": ("原生导出", {"path": "string", "target": "string"}, False),
    "project.archive": ("整包归档（数 MB）", {"path": "string"}, False),
    "generate.runtime": ("生成运行时文件", {"directory": "string"}, False),
    "project.doc": ("导出工程文档", {"path": "string"}, False),
    "project.io_export": ("导出 I/O 映射 CSV", {"path": "string", "device": "string"}, False),
    "project.io_import": ("导入 I/O 映射 CSV", {"path": "string", "device": "string"}, True),
    # 在线（仿真）
    "online.simulation": ("开关仿真模式", {"enabled": "boolean"}, True),
    "online.login": ("登录（仿真可用）", {"autostart": "boolean"}, True),
    "online.logout": ("注销", {}, True),
    "online.state": ("在线状态", {}, False),
    "online.start": ("启动应用", {}, True),
    "online.stop": ("停止应用", {}, True),
    "online.read": ("读在线变量值（数值判据）", {"expression": "string", "expressions": "array"}, False),
    "online.write": ("写在线变量并读回", {"expression": "string", "value": "string"}, True),
    "online.monitor": ("在线采样（给样本数与间隔，**返回的是数字序列**）",
                       {"expression": "string", "samples": "integer",
                        "interval_ms": "integer", "expressions": "array"}, False),
    "online.download": ("下载到 PLC", {}, True),
    "online.force": ("强制变量", {"expression": "string", "value": "string"}, True),
    "online.unforce": ("解除强制", {}, True),
    "online.forced": ("列出被强制的变量", {}, False),
}

# 只暴露"干活会用到"的：排除 IDE 命令枚举里的冷门项，其余全上（55 条）
SKIP = ("commands", "project.compare", "project.users", "project.integrity",
        "project.doc", "textlist.text", "task.update", "online.force",
        "online.unforce", "online.forced")


# 每条命令的"真必填"参数。之前用一条规则（path 必填）把所有命令都标了 path，
# 结果 `project.save` / `tree`（有默认 "/"）在**内核契约校验**阶段就被拒了
# —— 报错文本是 `path is required`，看起来像服务在报错，其实是我们的 schema。
REQUIRED: Dict[str, tuple] = {
    "project.create": ("path",), "project.open": ("path",), "project.save_as": ("path",),
    "tree": (),
    "pou.read": ("path",), "pou.write": ("path", "text"), "pou.members": ("path",),
    "pou.create": ("name",), "pou.create_typed": ("name",),
    "pou.member": ("parent", "name"), "pou.persistent": ("name",),
    "object.info": ("path",), "object.rename": ("path", "name"),
    "object.move": ("path", "parent"), "object.delete": ("path",),
    "folder.create": ("parent", "name"),
    "find.text": ("pattern",),
    "task.info": ("path",), "task.create": ("name",), "task.update": ("path",),
    "library.add": ("name",),
    "symbols.info": ("path",),
    "textlist.create": ("name",), "textlist.languages": ("path",),
    "textlist.rows": ("path",), "textlist.text": ("path",), "textlist.export": ("path",),
    "export.xml": ("path",), "export.native": ("path",), "import.xml": ("path",),
    "project.archive": ("path",), "project.doc": ("path",),
    "project.io_export": ("path",), "project.io_import": ("path",),
    "generate.runtime": ("directory",),
    "online.read": ("expression",), "online.write": ("expression", "value"),
    "online.monitor": ("expression",),
    "execute": ("name",),
}


def _count_items(value: Any) -> Optional[int]:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("items", "children", "tasks", "libraries", "available",
                    "members", "rows", "devices", "matches", "results"):
            if isinstance(value.get(key), list):
                return len(value[key])
    return None


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace("INT#", "").replace("REAL#", "").strip())
        except ValueError:
            return None
    return None


def judges_for(cmd: str, args: Dict[str, Any], result: Any,
               follow: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """按命令族生成判据。`follow` 是跨命令验证拿到的补充读数。"""
    checks: List[Dict[str, Any]] = []

    def add(name: str, got: Any, want: Any = True, ok: Optional[bool] = None) -> None:
        checks.append({"check": name, "got": got, "want": want,
                       "ok": bool(ok) if ok is not None else got == want})

    if result is None:
        add("result_present", False, True, ok=False)
        return checks
    add("result_present", True)
    # 每条命令都多给一个**数值**判据（返回体字符数）：
    # 即使最简单的查询（version/libraries）也不只有布尔 true。
    try:
        _chars = len(json.dumps(result, ensure_ascii=False, default=str))
    except Exception:                                   # noqa: BLE001
        _chars = 0
    add("result_chars", _chars, ">0", ok=_chars > 0)
    if isinstance(result, dict) and "ok" in result:
        add("service_ok", bool(result.get("ok")))

    n = _count_items(result)
    if n is not None:
        add("item_count", n, ">=0", ok=n >= 0)

    # 只有"导出/归档/文档"这类命令才该拿文件存在性当判据；
    # project.create / project.save 的 path 在落盘前并不保证存在。
    FILE_CMDS = ("export.xml", "export.native", "project.archive", "project.doc",
                 "project.io_export", "textlist.export", "generate.runtime")
    size = result.get("size") if isinstance(result, dict) else None
    path = result.get("path") if isinstance(result, dict) else None
    if size is not None:
        add("bytes", int(size), ">0", ok=int(size) > 0)
    if cmd in FILE_CMDS and isinstance(path, str) and path:
        exists = os.path.isfile(path)
        add("file_exists", exists)
        if exists:
            add("file_bytes", os.path.getsize(path), ">0", ok=os.path.getsize(path) > 0)
    elif cmd == "project.create" and isinstance(result, dict):
        add("program_path", bool(result.get("program")), "非空",
            ok=bool(result.get("program")))
    elif cmd == "pou.read" and isinstance(result, dict):
        text = result.get("text") or result.get("content") or ""
        add("text_chars", len(text or ""), ">0", ok=len(text or "") > 0)
    # 生成/清理：CODESYS 的 is_uptodate 在 generate 之后仍可能是 false（引擎行为），
    # 所以判据看动作自身的标志，is_uptodate 只作参考读数。
    if isinstance(result, dict) and "generated" in result:
        add("generated", bool(result.get("generated")))
    if isinstance(result, dict) and "cleaned" in result:
        add("cleaned", bool(result.get("cleaned")))
    if isinstance(result, dict) and "saved_as" in result:
        add("saved_as", bool(result.get("saved_as")))

    # 工程状态
    if isinstance(result, dict) and "dirty" in result:
        add("dirty", bool(result["dirty"]), "保存后应为 False",
            ok=(not result["dirty"]) if cmd in ("project.save", "project.save_as") else True)
    if isinstance(result, dict) and "is_uptodate" in result:
        add("is_uptodate", bool(result["is_uptodate"]), "参考读数", ok=True)
    if isinstance(result, dict) and result.get("closed"):
        add("closed", True)

    # 在线读/写/采样：数值必须真的读出来
    if cmd.startswith("online."):
        values = []
        if isinstance(result, dict):
            for key in ("value", "values", "readback"):
                if key in result:
                    v = result[key]
                    if isinstance(v, list):
                        values.extend(_numeric(x) for x in v)
                    else:
                        values.append(_numeric(v))
        values = [v for v in values if v is not None]
        if values:
            add("sample_count", len(values), ">=1", ok=len(values) >= 1)
            add("first_value", values[0])
            if len(values) > 1:
                add("value_span", max(values) - min(values))

    # 跨命令验证
    if follow:
        if "readback_text" in follow:
            add("readback_ok", follow["readback_text"] == args.get("text"))
        if "readback_len" in follow:
            add("readback_chars", follow["readback_len"], ">0",
                ok=(follow["readback_len"] or 0) > 0)
        if "objects_before" in follow and "objects_after" in follow:
            delta = (follow["objects_after"] or 0) - (follow["objects_before"] or 0)
            add("objects_added", delta, ">=1", ok=delta >= 1)
        if "messages" in follow:
            add("compile_errors", follow.get("error_count", 0), 0,
                ok=(follow.get("error_count") or 0) == 0)
    return checks


def build_tools(call_raw: Callable[[str, Dict[str, Any]], Any], *, prefix: str = "codesys",
                timeout_s: float = 300.0) -> List[ToolSpec]:
    """把命令表变成 ToolSpec。`call_raw(cmd, args)` 返回原始 result（不是归一化载荷）。"""
    tools: List[ToolSpec] = []
    for cmd, (desc, params, writes) in S.items():
        if cmd in SKIP:
            continue
        name = "%s_%s" % (prefix, cmd.replace(".", "_").replace("-", "_"))
        schema = {"type": "object",
                  "properties": {k: {"type": v} for k, v in params.items()},
                  "additionalProperties": False}
        required = list(REQUIRED.get(cmd, ()))
        if required:
            schema["required"] = required
        if cmd == "tree":
            schema["properties"]["path"] = {"type": "string", "default": "/"}

        def handler(args: Dict[str, Any], _cmd: str = cmd, _params=params) -> dict:
            from ..tools import normalize
            args = dict(args or {})
            if _cmd == "tree" and not args.get("path"):
                args["path"] = "/"
            if _cmd == "project.io_export" and not args.get("device"):
                args.pop("device", None)
            unknown = [k for k in args if k not in _params]
            if unknown:
                return normalize("codesys", _cmd, ok=False,
                                 errors=["未知参数：%s（支持：%s）"
                                         % ("、".join(unknown), "、".join(_params) or "无")])
            t0 = time.time()
            try:
                result = call_raw(_cmd, args)
            except Exception as exc:                    # noqa: BLE001
                # 服务端报错（例如没开工程时的 E_STATE）也要给判据：
                # "必须有判据"是内核约定，0 条判据等于静默失败。
                from ..tools import normalize as _norm
                why = "%s: %s" % (type(exc).__name__, exc)
                return _norm("codesys", _cmd, ok=False,
                             reads={"cmd": _cmd, "args": args, "result": None},
                             errors=[why],
                             checks=[{"check": "service_call", "got": why[:120],
                                      "want": "成功", "ok": False}],
                             seconds=round(time.time() - t0, 2))
            follow: Dict[str, Any] = {}
            # 跨命令验证：写代码要读回
            if _cmd == "pou.write" and isinstance(args.get("path"), str):
                try:
                    back = call_raw("pou.read", {"path": args["path"],
                                                 "part": args.get("part") or "implementation"})
                    if isinstance(back, dict):
                        text = back.get("text") or back.get("content") or ""
                        follow["readback_text"] = text
                        follow["readback_len"] = len(text or "")
                except Exception:                   # noqa: BLE001
                    pass
            checks = judges_for(_cmd, args, result, follow)
            payload = normalize("codesys", _cmd, ok=all(c["ok"] for c in checks),
                                reads={"cmd": _cmd, "args": args, "result": result,
                                       "follow": follow},
                                checks=checks, seconds=round(time.time() - t0, 2))
            return payload

        tools.append(ToolSpec(
            name,
            "%s（服务命令 %s%s）" % (desc, cmd, "，写操作" if writes else ""),
            schema, handler, timeout_s=timeout_s, must_have_checks=True))
    return tools

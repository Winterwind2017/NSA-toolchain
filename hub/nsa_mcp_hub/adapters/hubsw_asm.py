"""SW 装配链的 hub 侧修复：`sw_assembly_build` / `sw_assembly_add`。

## 为什么要在 hub 侧做

swkit 的 `sw_insert_component` 调的是

    doc.AddComponent5(file_path, 0, "", fixed, x, y, z)      # 只有 7 个参数

而 `IAssemblyDoc::AddComponent5` 是 **8 个参数**：

    AddComponent5(CompConfig, UseConfigForPart, NewPartPath,
                  ConfigOption, InsertedOption, X, Y, Z)

参数少一个 → 晚绑定报"非选择性的参数" → 返回 None → 调用方只看到
`components_after = 0` + "backend error"（2026-11-04 实测）。

## 实测出来的正确顺序（三个条件缺一不可）

1. 零件必须**预先在同一个 SolidWorks 会话里打开**（否则 AddComponent5 也返回 None）；
2. 装配体必须是 **ActiveDoc**（打开零件会把活动文档切成零件）；
3. `AddComponent5("", False, path, 0, 0, x, y, z)` —— 8 参、配置空、用零件自带配置。

三条都满足时实测 `AddComponent5 -> <component>`、`GetComponents` 数到 1。

所以这里不代理 swkit 的插入，而是**在本进程直接用 COM**：先按需打开零件、
再 `ActivateDoc3` 把装配体切回活动、最后 8 参 AddComponent5；判据用组件数读回。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ..tools import ToolSpec, normalize

KIT = "sw"

SW_DOC_ASSEMBLY = 2

_SCHEMA = {
    "type": "object",
    "properties": {
        "parts": {"type": "array", "items": {"type": "string"},
                  "description": "零件文件路径（.SLDPRT），按顺序插入"},
        "spacing_mm": {"type": "number",
                       "description": "沿 X 方向的间距（mm），默认 100"},
    },
    "required": ["parts"],
    "additionalProperties": False,
}


def _as_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if str(v).strip()]


def _attach() -> Any:
    import pythoncom                      # noqa: I001  按调用线程初始化 COM
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.GetActiveObject("SldWorks.Application")


def _documents(app: Any) -> List[Any]:
    docs = app.GetDocuments              # 注意：本机是**属性**，不是方法
    return list(docs or [])


def _find_assembly(app: Any) -> Optional[Any]:
    for doc in _documents(app):
        try:
            if int(doc.GetType) == SW_DOC_ASSEMBLY:
                return doc
        except Exception:                # noqa: BLE001
            continue
    return None


def _activate(app: Any, doc: Any) -> bool:
    import pythoncom
    import win32com.client
    err = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    try:
        app.ActivateDoc3(str(doc.GetTitle), False, 0, err)
    except Exception:                    # noqa: BLE001
        pass
    try:
        return int(app.ActiveDoc.GetType) == SW_DOC_ASSEMBLY
    except Exception:                    # noqa: BLE001
        return False


def _component_count(asm: Any) -> Optional[int]:
    try:
        comps = asm.GetComponents(False)
    except Exception:                    # noqa: BLE001
        return None
    if comps is None:
        return 0
    try:
        return len(list(comps))
    except TypeError:
        return None


def _insert(app: Any, asm: Any, path: str, x: float, y: float, z: float) -> Any:
    return asm.AddComponent5("", False, path, 0, 0, float(x), float(y), float(z))


def asm_tools(call: Callable[[str, Dict[str, Any]], Dict[str, Any]]) -> List[Any]:
    """`call(remote_name, args)` 是适配器给的代理调用器（只用到建装配/开零件）。"""

    def _run(parts: List[str], spacing: float, capability: str,
             create_assembly: bool) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = []
        problems: List[str] = []
        try:
            app = _attach()
        except Exception as exc:         # noqa: BLE001
            return normalize(KIT, capability, ok=False,
                             errors=["附加 SolidWorks 失败：%s: %s"
                                     % (type(exc).__name__, str(exc)[:160])])

        if create_assembly:
            created = call("sw_create_assembly", {})
            steps.append({"tool": "sw_create_assembly", "ok": bool(created.get("ok"))})
            if not created.get("ok"):
                return normalize(KIT, capability, ok=False, reads={"steps": steps},
                                 errors=["建装配失败：%s" % (created.get("errors") or "未知")])

        asm = _find_assembly(app)
        if asm is None:
            return normalize(KIT, capability, ok=False, reads={"steps": steps},
                             errors=["当前 SolidWorks 里没有装配体文档"])

        before = _component_count(asm)
        inserted = 0
        for index, part in enumerate(parts):
            opened = call("sw_open_document", {"path": part})
            steps.append({"tool": "sw_open_document", "ok": bool(opened.get("ok")),
                          "part": part,
                          "note": None if opened.get("ok")
                          else str(opened.get("errors"))[:120]})
            if not _activate(app, asm):
                problems.append("装配体没能激活（第 %d 个零件）" % (index + 1))
                break
            try:
                comp = _insert(app, asm, part, index * spacing, 0.0, 0.0)
            except Exception as exc:     # noqa: BLE001
                problems.append("AddComponent5 抛错（%s）：%s" % (part, str(exc)[:120]))
                continue
            steps.append({"tool": "AddComponent5", "ok": comp is not None, "part": part})
            if comp is None:
                problems.append("AddComponent5 返回 None（%s）" % part)
            else:
                inserted += 1

        after = _component_count(asm)
        expected = (before or 0) + len(parts)
        checks = [
            {"check": "parts_inserted", "got": inserted, "want": len(parts),
             "ok": inserted == len(parts)},
            {"check": "component_count", "got": after, "want": expected,
             "ok": after is not None and after == expected},
        ]
        return normalize(KIT, capability, ok=not problems,
                         reads={"steps": steps, "components_before": before,
                                "components_after": after, "spacing_mm": spacing},
                         checks=checks, errors=problems)

    def _build(args: Dict[str, Any]) -> Dict[str, Any]:
        parts = _as_list(args.get("parts"))
        if not parts:
            return normalize(KIT, "assembly_build", ok=False,
                             errors=["parts 不能为空（给零件文件路径，至少一个）"])
        return _run(parts, float(args.get("spacing_mm") or 100.0),
                    "assembly_build", create_assembly=True)

    def _add(args: Dict[str, Any]) -> Dict[str, Any]:
        parts = _as_list(args.get("parts"))
        if not parts:
            return normalize(KIT, "assembly_add", ok=False,
                             errors=["parts 不能为空（当前装配体需已打开）"])
        return _run(parts, float(args.get("spacing_mm") or 100.0),
                    "assembly_add", create_assembly=False)

    return [
        ToolSpec("sw_assembly_build",
                 "建装配体并逐个插零件（hub 侧修复 swkit 的 7 参 AddComponent5 bug："
                 "开零件→激活装配→8 参插入）。判据=组件数读回。",
                 _SCHEMA, _build, timeout_s=600),
        ToolSpec("sw_assembly_add",
                 "往当前装配体里追加零件（同样先开零件、再激活装配、8 参插入）。",
                 _SCHEMA, _add, timeout_s=600),
    ]

"""MCP 风格的工具面（对照 CADCraft `crates/mcp` 的三分法：命令/检查/渲染）。

三件事：
1. **只暴露 verified 的能力**（registry 是唯一事实来源，未验证的不许出现在工具列表里）；
2. 每个工具带 JSON Schema（类型/必填/范围），**参数校验发生在动图之前**——
   agent 拿到的是"参数 3 必须是数字，给的是 'abc'"，而不是 AutoCAD 的原始异常；
3. 返回**判据信封** `{ok, checks, detail, error}`，让调用方知道"为什么算成功"。

本模块不依赖 AutoCAD（dispatch 时才需要传 doc），所以可离线测试。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .. import caps, registry


class ToolError(ValueError):
    """工具名不存在 / 参数不合法 / 执行失败。"""


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: Dict[str, Any]
    capability_id: str
    level: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "inputSchema": self.schema, "capability": self.capability_id}


def _schema_for(cap) -> Dict[str, Any]:                      # noqa: ANN001
    """从能力的默认参数推 schema（默认值类型即声明类型）。"""
    props: Dict[str, Any] = {}
    for key, value in (cap.params or {}).items():
        if isinstance(value, bool):
            props[key] = {"type": "boolean"}
        elif isinstance(value, int):
            props[key] = {"type": "integer"}
        elif isinstance(value, float):
            props[key] = {"type": "number"}
        elif isinstance(value, (list, tuple)):
            props[key] = {"type": "array", "items": {"type": "number"}}
        elif isinstance(value, dict):
            props[key] = {"type": "object"}
        else:
            props[key] = {"type": "string"}
    return {"type": "object", "properties": props,
            "required": [], "additionalProperties": True}


def list_tools() -> List[ToolSpec]:
    """只列 verified 的能力（未验证的不该被 agent 看见）。"""
    data = registry.load()
    verified = {c["id"] for c in data["capabilities"] if c.get("status") == "verified"}
    out: List[ToolSpec] = []
    for cap in caps.CAPS:
        if cap.id not in verified:
            continue
        out.append(ToolSpec(name=cap.id.replace(".", "_"),
                            description="%s（%s）" % (cap.title, cap.level),
                            schema=_schema_for(cap), capability_id=cap.id,
                            level=cap.level))
    return out


def find(name: str) -> ToolSpec:
    for spec in list_tools():
        if spec.name == name or spec.capability_id == name:
            return spec
    raise ToolError("没有这个工具：%r（用 list_tools() 看可用列表）" % name)


def _check_type(value: Any, expect: str) -> bool:
    if expect == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expect == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expect == "boolean":
        return isinstance(value, bool)
    if expect == "string":
        return isinstance(value, str)
    if expect == "array":
        return isinstance(value, (list, tuple))
    if expect == "object":
        return isinstance(value, dict)
    return True


def validate(name: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """校验参数：类型错/未知键/非有限数值都在这里拦。"""
    spec = find(name)
    params = dict(params or {})
    props = spec.schema.get("properties") or {}
    extra = [k for k in params if k not in props]
    if extra:
        raise ToolError("不认识的参数：%s（可用：%s）"
                        % (", ".join(sorted(extra)), ", ".join(sorted(props)) or "无"))
    for key, value in params.items():
        expect = (props[key] or {}).get("type")
        if expect and not _check_type(value, expect):
            raise ToolError("参数 %s 应为 %s，实际 %r"
                            % (key, expect, type(value).__name__))
        if isinstance(value, float) and (value != value or abs(value) == float("inf")):
            raise ToolError("参数 %s 是非有限数值：%r" % (key, value))
    return params


def dispatch(name: str, params: Optional[Dict[str, Any]], doc: Any,
             *, judge: Optional[Callable[[Any, Dict[str, Any]], Dict[str, Any]]] = None
             ) -> Dict[str, Any]:
    """执行一个工具：build → 读回 → 判据 → 信封。

    `judge` 不传时只返回 build 的痕迹（调用方自己补判据）；传了就返回判据结果。
    """
    spec = find(name)
    clean = validate(name, params)
    envelope: Dict[str, Any] = {"tool": spec.name, "capability": spec.capability_id,
                                "ok": False, "checks": {}, "detail": {}}
    try:
        caps.build(spec.capability_id, doc, clean)
    except Exception as exc:                                  # noqa: BLE001
        from ..core.diag import classify

        d = classify(exc)
        envelope.update({"error": d.raw, "kind": d.kind,
                         "hint": d.hint, "retryable": d.retryable})
        return envelope
    if judge is None:
        envelope["ok"] = True
        envelope["detail"] = {"note": "只执行了 build，没有判据"}
        return envelope
    try:
        result = judge(doc, {"params": clean})
    except Exception as exc:                                  # noqa: BLE001
        envelope.update({"error": "%s: %s" % (type(exc).__name__, exc)})
        return envelope
    envelope.update({"ok": bool(result.get("ok")),
                     "checks": result.get("checks") or {},
                     "detail": result.get("detail") or {}})
    return envelope


def dumps(specs: List[ToolSpec]) -> str:
    return json.dumps([s.to_dict() for s in specs], ensure_ascii=False, indent=2)

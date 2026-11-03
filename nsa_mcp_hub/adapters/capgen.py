"""能力 → 工具 生成器（P0）。

背景：acadkit / nxkit / gxkit 的能力本来就是**任务形状**（id / title / params / 自带
judge），但对外只有一个 `*_run_capability(ids=[...])`，模型得先查能力表、再拼 id。
这里把一条能力直接变成一个任务级工具：

    geom.line → acad_geom_line(length_mm=60)   ← 参数就是能力的 params

判据、错误、超时全部沿用原能力（`*_run_capability` 那条路径），所以生成出来的工具
和原来的 `ok` 语义完全一致，不会出现"工具成功但几何没动"。

设计取舍：
* **不重复实现动作**：handler 只调用适配器已有的 `run_capability`，保证单一执行路径。
* **参数类型从默认值推断**：能力表里多数只有默认值没有类型；推断规则见
  `schema_from_params`，`None` 默认值当作必填。
* **能力名保留在描述里**：排查时能一眼对上 `acadkit` 的能力表。
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from ..tools import ToolSpec

_NAME_SAFE = re.compile(r"[^0-9a-zA-Z_]+")


def tool_name(prefix: str, cap_id: str) -> str:
    """`geom.line` + `acad` → `acad_geom_line`。"""
    raw = "%s_%s" % (prefix, cap_id.replace(".", "_"))
    return _NAME_SAFE.sub("_", raw).strip("_").lower()


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def schema_from_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把能力的默认参数表转成 JSON Schema（类型从默认值推断）。"""
    props: Dict[str, Any] = {}
    required: List[str] = []
    for key, value in (params or {}).items():
        props[key] = {"type": _json_type(value)}
        if value is None:
            required.append(key)
    schema: Dict[str, Any] = {"type": "object", "properties": props,
                              "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def build_tools(caps: Iterable[Any], *, prefix: str, call: Callable[[str, Dict[str, Any]], dict],
                only: Optional[Sequence[str]] = None, skip: Sequence[str] = (),
                timeout_s: float = 300.0, level_filter: Optional[Callable[[str], bool]] = None,
                note: str = "") -> List[ToolSpec]:
    """把能力列表变成 ToolSpec 列表。

    caps        : 能力对象（需有 id / title / params / level）
    prefix      : 工具名前缀，通常就是 kit key
    call        : (cap_id, params) -> 已归一化的 payload；由适配器提供
    only        : 只生成这些能力 id（策展清单）；None 表示全部
    skip        : 显式排除
    level_filter: 额外过滤（例如只保留 L1 以上）
    """
    wanted = set(only) if only else None
    skipped = set(skip)
    tools: List[ToolSpec] = []
    seen: set = set()
    for cap in caps:
        cap_id = str(getattr(cap, "id", "") or "")
        if not cap_id or cap_id in skipped:
            continue
        if wanted is not None and cap_id not in wanted:
            continue
        level = str(getattr(cap, "level", "") or "")
        if level_filter is not None and not level_filter(level):
            continue
        name = tool_name(prefix, cap_id)
        if name in seen:                            # 能力 id 撞名（极少见）时跳过并留下痕迹
            continue
        seen.add(name)
        title = str(getattr(cap, "title", "") or cap_id)
        schema = schema_from_params(getattr(cap, "params", None))

        def handler(args: Dict[str, Any], _cap_id: str = cap_id) -> dict:
            return call(_cap_id, dict(args or {}))

        tools.append(ToolSpec(
            name,
            "%s｜能力 %s%s（级别 %s）。判据沿用该能力自带的 judge。"
            % (title, cap_id, ("，" + note) if note else "", level or "?"),
            schema,
            handler,
            timeout_s=timeout_s,
            must_have_checks=True,
        ))
    return tools


def merge_params(cap_params: Optional[Dict[str, Any]], given: Dict[str, Any]) -> Dict[str, Any]:
    """能力默认参数 + 调用方覆盖，并拒绝未知键（早报错好过静默忽略）。"""
    base = dict(cap_params or {})
    unknown = [k for k in given if k not in base]
    if unknown:
        raise ValueError("未知参数：%s（该能力支持：%s）"
                         % ("、".join(sorted(unknown)),
                            "、".join(sorted(base)) or "无"))
    merged = dict(base)
    merged.update({k: v for k, v in given.items() if v is not None})
    return merged

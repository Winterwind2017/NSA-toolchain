"""判据基座：读回形状 + `verdict()` 收口。

`docs/JUDGE_SPEC.md` 第五节的三条约定，在这里落成代码：

1. `ok` 只能是 `all(checks.values())` —— 由 :func:`verdict` 唯一出口计算，
   别处**没有**写 `ok=True` 的机会；
2. `detail` 里必须有**人能核对**的数字（半径/面积/长度/页数），不能只有布尔；
3. 失败时保留原始读回值（`raw`），方便定位是"没做"还是"做错"。

判据函数本身是**纯函数**：只吃 :class:`Readback` / 普通字典，不碰 COM。
这样同一份判据既能被真机用例驱动，也能用离线构造的读回值做正反例单测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class JudgeError(RuntimeError):
    """判据自身违反约定（不是被测能力失败）。"""


# ── 读回形状 ────────────────────────────────────────────────────────
@dataclass
class Entity:
    """一个模型空间实体的一次读回。"""

    handle: str
    type: str
    attrs: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.attrs.get(key, default)


@dataclass
class Drawing:
    """某个时刻（内存 / 重开文件 / DXF 解析）的图面读回。

    `source` 只会是以下几种，判据会把它写进 detail，防止"拿内存值冒充重开值"：

        before   动作前
        memory   动作后、未落盘
        reopened DWG 存盘重开
        dxf      文件层解析（ezdxf 或最小解析器）
        dxf-reopened 把 DXF 重新装进 AutoCAD 后
    """

    source: str
    insunits: Optional[int] = None
    entities: List[Entity] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    # -- 统计 ------------------------------------------------------
    @property
    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self.entities:
            out[e.type] = out.get(e.type, 0) + 1
        return out

    def count(self, type_name: str) -> int:
        return self.counts.get(type_name, 0)

    def of_type(self, type_name: str) -> List[Entity]:
        return [e for e in self.entities if e.type == type_name]

    def by_handle(self, handle: str) -> Optional[Entity]:
        for e in self.entities:
            if e.handle and e.handle == handle:
                return e
        return None

    @property
    def handles(self) -> set:
        return {e.handle for e in self.entities if e.handle}

    # -- 单位 ------------------------------------------------------
    @property
    def unit_scale_mm(self) -> Optional[float]:
        """1 个图形单位 = 多少 mm。INSUNITS: 1=in 2=ft 4=mm 5=cm 6=m。"""
        return {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}.get(self.insunits)


@dataclass
class Readback:
    """一条用例的三个读回点（JUDGE_SPEC 的 L1–L4 就靠这三份数据）。"""

    before: Drawing
    memory: Drawing
    reopened: Optional[Drawing] = None
    dxf: Optional[Drawing] = None
    dxf_reopened: Optional[Drawing] = None


# ── 收口：ok 只能是 all(checks) ─────────────────────────────────────
def verdict(checks: Dict[str, bool],
            detail: Optional[Dict[str, Any]] = None,
            raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把一组布尔检查收成判据结果。

    * checks 里**只许**出现真布尔：`None` 表示"没测"，不许混进来当 False 用；
    * ok 只在这里算一次。
    """
    bad = sorted(k for k, v in checks.items() if not isinstance(v, bool))
    if bad:
        raise JudgeError("checks 必须全是 bool，发现 %r" % (bad,))
    if not checks:
        raise JudgeError("checks 不能为空（空集 all() 恒真，等于没判）")
    return {
        "ok": all(checks.values()),
        "checks": dict(checks),
        "detail": detail or {},
        "raw": raw or {},
    }


# ── 数值比较 ────────────────────────────────────────────────────────
def num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def close(a: Any, b: Any, tol: float = 1e-6) -> bool:
    fa, fb = num(a), num(b)
    return fa is not None and fb is not None and abs(fa - fb) <= tol


def rel_close(a: Any, b: Any, rel: float = 1e-9) -> bool:
    fa, fb = num(a), num(b)
    if fa is None or fb is None:
        return False
    scale = max(abs(fa), abs(fb), 1e-12)
    return abs(fa - fb) / scale <= rel


def pt3(v: Any) -> Optional[Tuple[float, float, float]]:
    """把 VARIANT/序列点读成 (x, y, z)。"""
    try:
        vals = [float(x) for x in v]
    except (TypeError, ValueError):
        return None
    if len(vals) < 2:
        return None
    return (vals[0], vals[1], vals[2] if len(vals) > 2 else 0.0)


def pt_close(a: Any, b: Any, tol: float = 1e-6) -> bool:
    pa, pb = pt3(a), pt3(b)
    if pa is None or pb is None:
        return False
    return all(abs(x - y) <= tol for x, y in zip(pa, pb))


# ── 新实体定位 ──────────────────────────────────────────────────────
def new_entities(rb: Readback, type_name: str) -> List[Entity]:
    """动作后新增的、指定类型的实体（按 handle 差集）。"""
    old = rb.before.handles
    return [e for e in rb.memory.of_type(type_name) if e.handle not in old]


def find_in(drawing: Optional[Drawing],
            ref: Entity) -> Optional[Entity]:
    """在另一份读回里找同一个实体：先按 handle，找不到再按几何唯一匹配。"""
    if drawing is None or ref is None:
        return None
    hit = drawing.by_handle(ref.handle)
    if hit is not None:
        return hit
    same = drawing.of_type(ref.type)
    if len(same) == 1 and len(drawing.of_type(ref.type)) == 1:
        return same[0]
    return None


def value_same(a: Any, b: Any, tol: float = 1e-6) -> bool:
    """通用"读回值是否一致"：数、点、点列、字符串、布尔都能比。

    早先 `reopen_check` 只用 `close()`，于是字符串（PatternName/TextString）
    和点列（多段线 vertices）一律判不等 —— 三条判据因此误报，已修。
    """
    if isinstance(a, (list, tuple)):
        if a and isinstance(a[0], (list, tuple)):
            return (isinstance(b, (list, tuple)) and len(a) == len(b)
                    and all(value_same(x, y, tol) for x, y in zip(a, b)))
        return pt_close(a, b, tol)
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return close(a, b, tol)
    return str(a) == str(b)


def reopen_check(rb: Readback, ref: Entity,
                 keys: Tuple[str, ...]) -> Tuple[bool, Dict[str, Any]]:
    """L4 的通用形态：重开后按 handle 找到同一实体，逐个属性比对。

    `keys` 里的属性用 :func:`value_same` 比较；没读到的算失败并写进 detail。
    """
    detail: Dict[str, Any] = {"reopened_source": None, "mismatch": {}}
    if rb.reopened is None:
        detail["mismatch"]["reopened"] = "没有重开读回"
        return False, detail
    detail["reopened_source"] = rb.reopened.source
    hit = find_in(rb.reopened, ref)
    if hit is None:
        detail["mismatch"]["handle"] = "%s 重开后找不到" % (ref.handle,)
        return False, detail
    ok = True
    for key in keys:
        want = ref.get(key)
        got = hit.get(key)
        if not value_same(want, got):
            ok = False
            detail["mismatch"][key] = [want, got]
    detail["reopened_handle"] = hit.handle
    return ok, detail

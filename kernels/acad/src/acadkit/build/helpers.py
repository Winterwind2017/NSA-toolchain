"""builders 共用的小工具。

* VARIANT 数组（点/坐标/对象数组）；
* `ms_of(doc)`：取 ModelSpace 并做一次 `Count` 自检 —— AutoCAD 刚建完文档时
  代理会偶发失效（`AttributeError: Add.ModelSpace`），这不是"没有这个属性"；
* `send(doc, lisp)`：走命令行执行一小段 LISP（不加载文件、不碰 TRUSTEDPATHS）；
* `handles_of` / `newest`：按句柄定位刚建出来的实体。
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

from ..core import com

try:                                    # 非 Windows / 没装 pywin32 也能 import 本包
    import pythoncom
    import win32com.client as w
except Exception:                       # noqa: BLE001
    pythoncom = None                    # type: ignore[assignment]
    w = None                            # type: ignore[assignment]

VT_ARRAY, VT_R8 = 8, 5
VT_DISPATCH = 9
if pythoncom is not None:
    VT_ARRAY, VT_R8 = pythoncom.VT_ARRAY, pythoncom.VT_R8
    VT_DISPATCH = pythoncom.VT_DISPATCH


def _require_com() -> None:
    if pythoncom is None or w is None:
        raise RuntimeError(
            "需要 pywin32（Windows）：pip install pywin32 —— "
            "本包在非 Windows 上只能做离线判据（judges/）")


def pt(x: float, y: float, z: float = 0.0):
    _require_com()
    return w.VARIANT(VT_ARRAY | VT_R8, (float(x), float(y), float(z)))


def dbl(vals):
    _require_com()
    return w.VARIANT(VT_ARRAY | VT_R8, [float(v) for v in vals])


def objs(lst: Iterable[Any]):
    _require_com()
    return w.VARIANT(VT_ARRAY | VT_DISPATCH, list(lst))


def ms_of(doc: Any, attempts: int = 6) -> Any:
    """取 ModelSpace，带自检与重试（AutoCAD 忙/刚建文档时代理会失效）。"""
    last: Optional[BaseException] = None
    for _ in range(attempts):
        try:
            ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
            int(com.retry(lambda: ms.Count, label="ModelSpace.Count"))
            return ms
        except Exception as exc:                        # noqa: BLE001
            last = exc
            time.sleep(0.4)
    if last is not None:
        raise last
    return doc.ModelSpace


def send(doc: Any, lisp: str, settle: float = 0.35) -> None:
    """把一小段 LISP 丢到命令行执行。

    **不加载 .lsp 文件**：`(load ...)` 受 SECURELOAD/TRUSTEDPATHS 管控，而那两个
    变量是持久化的，探针忘还原就会污染用户的 VANILLA 配置（本项目踩过三次）。
    直接 `SendCommand` 一段 `(progn ...)` 不需要任何信任设置。

    `RPC_E_CALL_REJECTED` 说明 AutoCAD 正忙、命令**还没被执行**，重试是安全的；
    实测预选对象后紧接着发命令必被拒收。
    """
    com.retry(lambda: doc.SendCommand(lisp.rstrip() + "\n"),
              attempts=20, delay=0.5, label="SendCommand")
    time.sleep(settle)


def handle_of(entity: Any) -> str:
    return str(com.retry(lambda: entity.Handle, label="Handle"))


def handles_of(entities: Iterable[Any]) -> List[str]:
    return [handle_of(e) for e in entities]


def lisp_handles(handles: Iterable[str]) -> str:
    return " ".join('(handent "%s")' % h for h in handles)


def add(ms: Any, method: str, *args, label: Optional[str] = None) -> Any:
    """`ms.AddXxx(...)` + 忙重试。"""
    fn = getattr(ms, method)
    return com.retry(lambda: fn(*args), label=label or method)


def basic_drawing(doc: Any):
    """一圆一线——导出类用例的最小图。"""
    ms = ms_of(doc)
    add(ms, "AddCircle", pt(10, 10, 0), 25.0, label="AddCircle")
    add(ms, "AddLine", pt(0, 0, 0), pt(60, 0, 0), label="AddLine")
    return ms


def define_block(doc: Any, name: str = "BOM_MARK"):
    """定义带两个属性的块（真块 + Attdef）。"""
    blocks = com.retry(lambda: doc.Blocks, label="Blocks")
    blk = com.retry(lambda: blocks.Add(pt(0, 0, 0), name), label="Blocks.Add")
    com.retry(lambda: blk.AddCircle(pt(0, 0, 0), 5.0), label="block.AddCircle")
    com.retry(lambda: blk.AddAttribute(2.5, 0, "Part No.", pt(-5, 6, 0),
                                       "PART_NO", "P-001"), label="AddAttribute")
    com.retry(lambda: blk.AddAttribute(2.5, 0, "Material", pt(-5, -8, 0),
                                       "MATERIAL", "Q235"), label="AddAttribute")
    return blk


def insert_block(doc: Any, values: Dict[str, str], name: str = "BOM_MARK",
                 insertion=(100, 0, 0)):
    ms = ms_of(doc)
    ref = com.retry(lambda: ms.InsertBlock(pt(*insertion), name,
                                           1.0, 1.0, 1.0, 0.0),
                    label="InsertBlock")
    for at in ref.GetAttributes():
        tag = str(at.TagString)
        if tag in values:
            at.TextString = values[tag]
    return ref


def add_solid(doc: Any, kind: str, **kw) -> Any:
    """建一个 3D 实体（AddBox/Cylinder/Sphere/Cone/Wedge/Torus）。"""
    ms = ms_of(doc)
    k = kind.lower()
    if k == "box":
        return add(ms, "AddBox", pt(*kw.get("origin", (0, 0, 0))),
                   float(kw["l"]), float(kw["w"]), float(kw["h"]), label="AddBox")
    if k == "cylinder":
        return add(ms, "AddCylinder", pt(*kw.get("center", (0, 0, 0))),
                   float(kw["r"]), float(kw["h"]), label="AddCylinder")
    if k == "sphere":
        return add(ms, "AddSphere", pt(*kw.get("center", (0, 0, 0))),
                   float(kw["r"]), label="AddSphere")
    if k == "cone":
        return add(ms, "AddCone", pt(*kw.get("center", (0, 0, 0))),
                   float(kw["r"]), float(kw["h"]), label="AddCone")
    if k == "wedge":
        return add(ms, "AddWedge", pt(*kw.get("origin", (0, 0, 0))),
                   float(kw["l"]), float(kw["w"]), float(kw["h"]), label="AddWedge")
    if k == "torus":
        return add(ms, "AddTorus", pt(*kw.get("center", (0, 0, 0))),
                   float(kw["r"]), float(kw["tube"]), label="AddTorus")
    raise ValueError("未知实体类型：%r" % (kind,))


def region_from_polyline(ms: Any, points, close: bool = True) -> Any:
    flat: List[float] = []
    for p in points:
        flat.extend([float(p[0]), float(p[1])])
    pl = com.retry(lambda: ms.AddLightWeightPolyline(dbl(flat)), label="AddPolyline")
    pl.Closed = bool(close)
    regs = com.retry(lambda: ms.AddRegion(objs([pl])), label="AddRegion")
    reg = regs[0] if isinstance(regs, (tuple, list)) else regs.Item(0)
    try:
        pl.Delete()
    except Exception:                                   # noqa: BLE001
        pass
    return reg


def boolean(doc: Any, op: str, entities: List[Any], settle: float = 1.2) -> Dict[str, Any]:
    """布尔运算：走命令行（ActiveX `Solid3D.Boolean` 在本机不可靠）。

    本机实测（2026-10-21）：
    * `box.Boolean(1, other)` 把 union 算成 4000（应为 12000），
      `Boolean(3, other)` 直接报"参数 Operation 无效"；
    * 命令行 `_.UNION` 得到 12000；且 `(command …)` 版本偶发挂起，
      `(vl-cmdf …)`（非交互）稳定；
    * **SUBTRACT 有两组选择集**：先选"被减的"，回车，再选"减去的"，
      回车 —— 一次给两个句柄会把第二个当成第一组的第二项。
    * 命令执行后第二个实体已被删除，**句柄必须在执行前取好**。
    """
    cmd = {"union": "UNION", "subtract": "SUBTRACT",
           "intersect": "INTERSECT"}.get(op.lower())
    if cmd is None:
        raise ValueError("未知布尔操作：%r" % (op,))
    handles = handles_of(entities)
    if len(handles) < 2:
        raise ValueError("布尔运算至少需要两个实体")
    hn = lisp_handles(handles)
    if op.lower() == "subtract":
        args = '%s "" %s ""' % (lisp_handles(handles[:1]),
                                lisp_handles(handles[1:]))
    else:
        args = '%s ""' % hn
    send(doc, '(vl-cmdf "_.%s" %s)' % (cmd, args), settle=settle)
    return {"op": op.lower(), "command": cmd, "handles": handles}


"""swkit.verified.equations —— 方程 / 全局变量 / 参考轴

判据：

| 工具 | 判据 |
|---|---|
| `list_equations` | `IEquationMgr.GetCount()` 可读，逐条 `Equation(i)`/`Value(i)` |
| `set_global_variable` | 写后计数 **+1**，且新条目 `Value` 读回等于写入值 |
| `create_reference_axis` | `RefAxis` 特征数 **+1** |

实测要点：
* `IModelDoc2` **没有** `AddEquation`；方程要走 `IEquationMgr`，而它在 pywin32 下
  `GetEquationMgr()` 就报"找不到成员" → **必须 comtypes**。
* 全局变量语法是 **`"名字" = 数值`**（名字带引号、不带 `@`）；`Add(-1, expr)`
  成功返回 **下标**（首条是 0），失败返回 **-1**。
* `GetCount` / `Value` / `Equation` 在 comtypes 下是**方法**，要带括号。
* 参考轴要选 **两个** 基准面（只选一个时 `InsertAxis2` 返回 bool 但不出特征）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.com import none_dispatch, pyw, val
from ._common import iter_features

__all__ = ["list_equations", "set_global_variable", "create_reference_axis",
           "equation_manager"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def equation_manager(doc: Any) -> Any:
    """取 `IEquationMgr`（comtypes 强类型）。"""
    from ._common import com_doc
    _sw, md = com_doc()
    return md.GetEquationMgr()


def list_equations(doc: Any) -> Dict[str, Any]:
    """列方程/全局变量。判据：计数可读，逐条能读出表达式与数值。"""
    out = _result("sw_get_equations", "IEquationMgr.GetCount/Equation/Value")
    try:
        em = equation_manager(doc)
        n = em.GetCount()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    rows = []
    for i in range(n):
        try:
            expr = em.Equation(i)
        except Exception:
            expr = None
        try:
            value = em.Value(i)
        except Exception:
            value = None
        rows.append({"index": i, "equation": expr, "value": value})
    out["detail"] = {"count": n, "equations": rows}
    out["checks"] = {"count_readable": isinstance(n, int) and n >= 0,
                     "entries_readable": len(rows) == n}
    out["ok"] = all(out["checks"].values())
    return out


def set_global_variable(doc: Any, name: str = "myvar",
                        value: float = 5.0) -> Dict[str, Any]:
    """写全局变量（`"name" = value`）。判据：计数 +1 且 Value 读回。"""
    out = _result("sw_set_global_variable", "IEquationMgr.Add(-1, expr)")
    try:
        em = equation_manager(doc)
        before = em.GetCount()
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    expr = '"%s" = %s' % (name, value)
    out["detail"].update({"expression": expr, "count_before": before})
    try:
        idx = em.Add(-1, expr)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = em.GetCount()
    back = None
    got_expr = None
    if isinstance(idx, int) and idx >= 0:
        try:
            back = em.Value(idx)
            got_expr = em.Equation(idx)
        except Exception:
            pass
    out["detail"].update({"returned_index": idx, "count_after": after,
                          "readback_value": back, "readback_equation": got_expr})
    out["checks"] = {
        "count_increased": after == before + 1,
        "value_readback": isinstance(back, (int, float))
        and abs(float(back) - float(value)) < 1e-9,
    }
    out["ok"] = all(out["checks"].values())
    return out


def create_reference_axis(doc: Any, plane1: str = "前视基准面",
                          plane2: str = "上视基准面") -> Dict[str, Any]:
    """由两个基准面建参考轴。判据：`RefAxis` 数 +1。"""
    out = _result("sw_create_reference_axis", "IModelDoc2.InsertAxis2")
    before = sum(1 for f in iter_features(doc)
                 if str(val(f, "GetTypeName2")) == "RefAxis")
    out["detail"].update({"plane1": plane1, "plane2": plane2, "axis_before": before})
    try:
        doc.ClearSelection2(True)
        ok1 = doc.Extension.SelectByID2(plane1, "PLANE", 0, 0, 0, False, 0,
                                       none_dispatch(), 0)
        ok2 = doc.Extension.SelectByID2(plane2, "PLANE", 0, 0, 0, True, 0,
                                       none_dispatch(), 0)
        picked = doc.SelectionManager.GetSelectedObjectCount2(-1)
        out["detail"].update({"selected_1": ok1, "selected_2": ok2, "selected": picked})
        if picked < 2:
            out["detail"]["error"] = "需要选中两个基准面"
            return out
        ret = doc.InsertAxis2(True)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = sum(1 for f in iter_features(doc)
                if str(val(f, "GetTypeName2")) == "RefAxis")
    out["detail"].update({"axis_after": after, "returned": ret})
    out["checks"] = {"axis_added": after == before + 1}
    out["ok"] = out["checks"]["axis_added"]
    return out

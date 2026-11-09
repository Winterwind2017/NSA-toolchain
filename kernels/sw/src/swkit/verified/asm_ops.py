"""swkit.verified.asm_ops —— 装配侧其余实测通过的实现

| 工具 | 真实 API | 判据 |
|---|---|---|
| `check_interference` | `IAssemblyDoc.InterferenceDetectionManager` → `GetInterferenceCount` | 计数可读；A/B 下重叠=1、分开=0 |
| `fix_component` | `IAssemblyDoc.FixComponent()` + `IComponent2.IsFixed` | `IsFixed=True` |
| `show_all_components` | `IAssemblyDoc.ShowComponent()` + `SetComponentVisibility` | 调用不抛异常且组件可见 |
| `explode_assembly` | `IAssemblyDoc.AutoExplode()` | 爆炸视图数 +1 |

注意（都是实测踩过的）：

* `GetInterferenceCount` / `GetInterferences` / `GetComponentCount` 在 pywin32 下是**属性**；
* `IInterference` 的成员用 pywin32 拿不到，要 `QueryInterface(sw.IInterference)`；
* `IBody2.GetMassProperties(density)` **必须传密度**，否则拿不到体积；
* 干涉数为 0 是**正常结果**，不能当失败——判据是"能读到计数"。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.com import val
from ._common import com_doc, sw_module, wrap

__all__ = ["check_interference", "fix_component", "show_all_components",
           "explode_assembly", "move_component"]


def _result(tool: str, api: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api, "detail": {}, "checks": {}}


def _components(asm_doc_w: Any) -> List[Any]:
    try:
        return list(asm_doc_w.GetComponents(False) or [])
    except Exception:
        return []


def check_interference(asm_doc_w: Any, treat_coincidence: bool = True,
                       include_multibody: bool = True) -> Dict[str, Any]:
    """干涉检查。返回干涉数与（尽量）明细；`count=0` 也算成功。"""
    out = _result("sw_check_interference", "IAssemblyDoc.InterferenceDetectionManager")
    try:
        mgr = wrap(asm_doc_w.InterferenceDetectionManager)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    for prop, flag in (("TreatCoincidenceAsInterference", treat_coincidence),
                       ("IncludeMultibodyPartInterference", include_multibody)):
        try:
            setattr(mgr, prop, flag)
        except Exception:
            pass
    count = val(mgr, "GetInterferenceCount")
    out["detail"]["count"] = count
    items = []
    for name in ("GetInterferences", "IGetInterferences"):
        raw = val(mgr, name)
        if raw is None or isinstance(raw, int):
            continue
        try:
            items = list(raw)
        except TypeError:
            items = [raw]
        if items:
            break
    out["detail"]["items"] = len(items)
    details = []
    for i, it in enumerate(items[:5]):
        entry: Dict[str, Any] = {"index": i}
        try:
            obj = it.QueryInterface(sw_module().IInterference)
        except Exception:
            obj = wrap(it)
        entry["component_count"] = val(obj, "GetComponentCount")
        try:
            body = val(obj, "GetInterferenceBody")
            if body is not None:
                b2 = body if hasattr(body, "GetMassProperties") else \
                    body.QueryInterface(sw_module().IBody2)
                mp = b2.GetMassProperties(1000.0)
                if isinstance(mp, (list, tuple)) and len(mp) > 3:
                    entry["volume_m3"] = round(float(mp[3]), 12)
        except Exception as exc:                    # noqa: BLE001
            entry["volume_error"] = str(exc)[:60]
        details.append(entry)
    out["detail"]["details"] = details
    try:
        val(mgr, "Done")
    except Exception:
        pass
    out["checks"] = {"count_readable": count is not None}
    out["ok"] = out["checks"]["count_readable"]
    out["detail"]["verdict"] = ("发现 %s 处干涉" % count
                                if (count or 0) > 0 else "无干涉")
    return out


def fix_component(asm_doc_w: Any, component_index: int = 0) -> Dict[str, Any]:
    """固定组件（`IsFixed=True` 为判据）。"""
    out = _result("sw_fix_component", "IAssemblyDoc.FixComponent")
    comps = _components(asm_doc_w)
    out["detail"]["components"] = len(comps)
    if not comps:
        out["detail"]["error"] = "装配里没有组件"
        return out
    target = wrap(comps[max(0, min(component_index, len(comps) - 1))])
    attempts = []
    fixed = False
    for mark in (0, 1):
        try:
            asm_doc_w.ClearSelection2(True)
            target.Select2(False, mark)
        except Exception:
            pass
        try:
            asm_doc_w.FixComponent()
        except Exception as exc:                    # noqa: BLE001
            attempts.append({"mark": mark, "error": str(exc)[:80]})
            continue
        fixed = bool(val(target, "IsFixed", False))
        attempts.append({"mark": mark, "is_fixed": fixed})
        if fixed:
            break
    out["detail"]["attempts"] = attempts
    out["detail"]["is_fixed"] = fixed
    out["checks"] = {"is_fixed": fixed}
    out["ok"] = fixed
    return out


def show_all_components(asm_doc_w: Any) -> Dict[str, Any]:
    """显示所有组件。"""
    out = _result("sw_show_all_components", "IAssemblyDoc.ShowComponent")
    comps = _components(asm_doc_w)
    out["detail"]["components"] = len(comps)
    if not comps:
        out["detail"]["error"] = "装配里没有组件"
        return out
    try:
        asm_doc_w.ClearSelection2(True)
        wrap(comps[0]).Select2(False, 0)
    except Exception:
        pass
    called = True
    try:
        asm_doc_w.ShowComponent()
    except Exception as exc:                        # noqa: BLE001
        called = False
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
    try:
        asm_doc_w.SetComponentVisibility(True, 0, None)
        out["detail"]["visibility_set"] = True
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["visibility_error"] = str(exc)[:80]
    def _is_hidden(comp: Any) -> Optional[bool]:
        # IComponent2.IsHidden(ConsiderSuppressed) 需要 1 个参数，不能用无参的 val()
        cw = wrap(comp)
        try:
            return bool(cw.IsHidden(False))
        except Exception:
            try:
                return bool(cw.IsHidden[False])
            except Exception:
                return None

    hidden = [_is_hidden(c) for c in comps]
    out["detail"]["is_hidden"] = hidden
    visible = all(h is False for h in hidden if h is not None)
    out["checks"] = {"show_called": called, "all_visible": visible}
    out["ok"] = called and visible
    return out


def explode_assembly(asm_doc_w: Any) -> Dict[str, Any]:
    """自动爆炸。判据：爆炸视图数 +1。"""
    out = _result("sw_explode_assembly", "IAssemblyDoc.AutoExplode")
    before = val(asm_doc_w, "GetExplodedViewCount", 0)
    # AutoExplode 在 pywin32 下是**属性**：读取即触发，返回值是 bool
    try:
        result = val(asm_doc_w, "AutoExplode")
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    after = val(asm_doc_w, "GetExplodedViewCount", 0)
    out["detail"].update({"views_before": before, "views_after": after,
                          "returned": str(result)})
    out["checks"] = {"exploded_view_created": (after or 0) > (before or 0)}
    out["ok"] = out["checks"]["exploded_view_created"]
    return out

def _insert_temp(asm_ct: Any, path: str, xyz: List[float]):
    """插临时件，返回 `(组件, 实际平移)`。"""
    tmp = asm_ct.AddComponent5(path, 0, "", False, "",
                               float(xyz[0]), float(xyz[1]), float(xyz[2]))
    if tmp is None:
        return None, None
    got = list(tmp.GetTotalTransform(False).ArrayData)[9:12]
    return tmp, [float(v) for v in got]


def _delete_temp(md: Any, asm_ct: Any, tmp: Any) -> bool:
    """删临时件。三条路径都试（`EditDelete2` 在 comtypes 下会失败，实测）：

    1. `IModelDocExtension.DeleteSelection2(bool)`
    2. `IAssemblyDoc.DeleteSelections(1 参)`
    3. `IModelDoc2.EditDelete2(bool)`
    """
    for attempt in ("extension", "assembly", "edit"):
        try:
            md.ClearSelection2(True)
            tmp.Select2(False, 0)
            if attempt == "extension":
                md.Extension.DeleteSelection2(True)
            elif attempt == "assembly":
                asm_ct.DeleteSelections(0)
            else:
                md.EditDelete2(True)
            return True
        except Exception:
            continue
    return False


def move_component(asm_doc_w: Any, delta_x: float = 0.05,
                   part_path: str = "") -> Dict[str, Any]:
    """平移组件（三轴都校验）。**变换拷贝法**：

    `IMathUtility` 在本机 comtypes 下拿不到可用变换（向量读成垃圾），所以改走：

    1. 在目标位置插一个临时件；
    2. **量出临时件的实际平移**——`AddComponent5` 的落点带固定偏置（实测 Z 差半个件高），
       所以按 `desired - actual` 校正后重插一次；
    3. 把临时件的 `Transform2` 赋给目标件；
    4. 读回三轴平移，删掉临时件。

    判据：Δx 与目标差 < 1e-4 m **且** Δy/Δz 都 < 1e-4 m（不允许"只对 X"）。
    """
    out = _result("sw_move_component", "IComponent2.Transform2（拷贝临时件变换）")
    sw, md = com_doc()
    asm_ct = md.QueryInterface(sw.IAssemblyDoc)
    comps = _components(asm_doc_w)
    n_components_before = len(comps)
    if not comps:
        out["detail"]["error"] = "装配里没有组件"
        return out
    first = wrap(comps[0])
    name = val(first, "Name2") or val(first, "Name")
    try:
        target = asm_ct.GetComponentByName(name)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "GetComponentByName(%s): %s" % (name, str(exc)[:80])
        return out
    base = [float(v) for v in list(target.GetTotalTransform(False).ArrayData)[9:12]]
    desired = [base[0] + float(delta_x), base[1], base[2]]
    out["detail"].update({"component": name, "before": [round(v, 6) for v in base],
                          "delta_x": float(delta_x)})
    path = part_path
    if not path:
        for c in comps:
            got = val(wrap(c), "GetPathName")
            if isinstance(got, str) and got.lower().endswith(".sldprt"):
                path = got
                break
    if not path:
        out["detail"]["error"] = "找不到可用的零件路径（请显式传 part_path）"
        return out

    tmp, actual = _insert_temp(asm_ct, path, desired)
    if tmp is None:
        out["detail"]["error"] = "临时件未插入"
        return out
    correction = [d - a for d, a in zip(desired, actual)]
    if any(abs(c) > 1e-6 for c in correction):
        out["detail"]["bias"] = [round(c, 6) for c in correction]
        _delete_temp(md, asm_ct, tmp)
        tmp, actual = _insert_temp(asm_ct, path,
                                   [d + c for d, c in zip(desired, correction)])
        if tmp is None:
            out["detail"]["error"] = "校正后重插失败"
            return out
    out["detail"]["temp_actual"] = [round(v, 6) for v in actual]
    try:
        target.Transform2 = tmp.Transform2
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "赋变换: %s" % str(exc)[:90]
        return out
    after = [float(v) for v in list(target.GetTotalTransform(False).ArrayData)[9:12]]
    deltas = [after[i] - base[i] for i in range(3)]
    out["detail"].update({"after": [round(v, 6) for v in after],
                          "deltas": [round(d, 6) for d in deltas]})
    out["detail"]["temp_removed"] = _delete_temp(md, asm_ct, tmp)
    out["detail"]["components_after"] = len(_components(asm_doc_w))
    out["checks"] = {
        "dx_matches": abs(deltas[0] - float(delta_x)) < 1e-4,
        "dy_zero": abs(deltas[1]) < 1e-4,
        "dz_zero": abs(deltas[2]) < 1e-4,
        "components_unchanged": len(_components(asm_doc_w)) == n_components_before,
    }
    out["ok"] = all(out["checks"].values())
    return out
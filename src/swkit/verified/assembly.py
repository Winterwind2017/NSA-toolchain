"""swkit.verified.assembly —— 装配侧"实测通过"的实现（带自证）

这里的每条函数都对应一次真实 A/B 实测（见 `docs/UNSUPPORTED.md` 与
`docs/RECIPES.md`），返回值统一是**证据字典**，而不是"调用了"：

```
{"ok": bool, "tool": str, "api": str, "detail": {...}, "checks": {...}}
```

所以"建出特征了"不可能被误读成"可交付"。

已实测（2026-10-20，SW 2025 SP4.1，测试件 box_hole + box_off）：

* `pattern_component(linear, count=3)` → 组件 2→4、特征 17→20、`IsPatternInstance`×2
* `pattern_component(linear, count=4)` → 组件 2→5、特征 17→21、`IsPatternInstance`×3
* `pattern_component(circular, 120°)` → 组件 2→4、`IsPatternInstance`×2
* `mirror_components()` → 特征 `镜像零部件1`、组件 2→4、`IsMirrored`×2
* 负面对照：把组件/方向标记换回旧值（4/1）→ 精确复现 `组件 2→2、特征 17→17、返回 None`
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..core.com import none_dispatch, pyw, val, var_dispatch_array, var_i4_array
from ..core.marks import (
    COMPONENT_DIR1, COMPONENT_TO_PATTERN, NULL_DIMENSION_NAME,
)

__all__ = [
    "components", "component_names", "find_feature", "pattern_component",
    "mirror_components",
]

# swFeatureNameID_e.swFmMirrorComponent
SW_FM_MIRROR_COMPONENT = 116
# swMirrorType_e
MIRROR_TYPE_BBOX, MIRROR_TYPE_COM, MIRROR_TYPE_ORIGIN = 0, 1, 2
# swOrientation_MirroredX_MirroredY
ORIENT_MX_MY = 0

_PLANE_NAMES = ("前视基准面", "上视基准面", "右视基准面",
                "Front Plane", "Top Plane", "Right Plane")


def _wrap(obj: Any) -> Any:
    """把 COM 指针统一成 pywin32 dynamic 对象（已经是就原样返回）。"""
    if obj is None:
        return None
    try:
        return pyw().Dispatch(obj)
    except Exception:
        return obj


def components(asm_doc_w: Any) -> List[Any]:
    """顶层组件列表。必须走 pywin32（comtypes 下 `GetComponents` 抛 KeyError 9）。"""
    try:
        return list(asm_doc_w.GetComponents(False) or [])
    except Exception:
        return []


def component_names(asm_doc_w: Any) -> List[Optional[str]]:
    out = []
    for comp in components(asm_doc_w):
        out.append(val(_wrap(comp), "Name2"))
    return out


def find_feature(doc_w: Any, name: str) -> Optional[Any]:
    """按名字找特征（基准面、镜像面等）。"""
    for getter in ("FeatureByName",):
        try:
            return getattr(doc_w, getter)(name)
        except Exception:
            continue
    return None


def _assembly_title_base(doc_w: Any) -> str:
    title = str(val(doc_w, "GetTitle", "") or "")
    for ext in (".SLDASM", ".sldasm", ".SLDPRT", ".sldprt"):
        if title.endswith(ext):
            return title[: -len(ext)]
    return title


def _component_box(comp: Any) -> Optional[List[float]]:
    """组件在**装配坐标**下的包围盒（米）：`[xmin,ymin,zmin,xmax,ymax,zmax]`。

    这是"方向边"能选中的前提——以前按假定零件坐标算点，组件一有平移就全落空。
    """
    for target in (_wrap(comp), comp):
        try:
            box = target.GetBox(False, False)
            if box is not None and len(box) >= 6:
                return [float(v) for v in box]
        except Exception:
            continue
    return None


def _edge_candidates(box: Sequence[float]) -> List[Tuple[float, float, float]]:
    """包围盒 12 条棱的中点——每条都落在真实几何上，逐个试选中。"""
    xmin, ymin, zmin, xmax, ymax, zmax = box[:6]
    xm, ym, zm = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0
    return [(xm, ymin, zmin), (xm, ymax, zmin), (xm, ymin, zmax), (xm, ymax, zmax),
            (xmin, ym, zmin), (xmax, ym, zmin), (xmin, ym, zmax), (xmax, ym, zmax),
            (xmin, ymin, zm), (xmax, ymin, zm), (xmin, ymax, zm), (xmax, ymax, zm)]


def _select_direction(asm_doc_w: Any, box: Sequence[float],
                      mark: int = COMPONENT_DIR1) -> Optional[Tuple[float, float, float]]:
    for pt in _edge_candidates(box):
        asm_doc_w.ClearSelection2(True)
        try:
            hit = asm_doc_w.Extension.SelectByID2(
                "", "EDGE", pt[0], pt[1], pt[2], False, mark, none_dispatch(), 0)
        except Exception:
            hit = False
        if hit:
            return pt
    return None


def _select_component(asm_doc_w: Any, comp: Any, name: Optional[str],
                      mark: int = COMPONENT_TO_PATTERN) -> bool:
    """组件选择：优先 `名字@装配标题`，退回对象选择（`SelectByMark`/`Select4`）。"""
    base = _assembly_title_base(asm_doc_w)
    cands = []
    if name:
        cands.append(name)
        if base:
            cands.append("%s@%s" % (name, base))
    for cname in cands:
        try:
            if asm_doc_w.Extension.SelectByID2(
                    cname, "COMPONENT", 0, 0, 0, True, mark, none_dispatch(), 0):
                return True
        except Exception:
            continue
    w = _wrap(comp)
    for meth, args in (("SelectByMark", (True, mark)),
                       ("Select4", (True, None, False)),
                       ("Select2", (True, mark))):
        try:
            if getattr(w, meth)(*args):
                return True
        except Exception:
            continue
    return False


def _count_components(asm_doc_w: Any) -> int:
    return len(components(asm_doc_w))


def _count_features(doc_w: Any) -> int:
    """特征数。`FirstFeature` 在不同绑定下可能是属性也可能是方法 → 用 `val`。"""
    n = 0
    feat = val(doc_w, "FirstFeature")
    while feat is not None and n < 500:
        n += 1
        feat = val(_wrap(feat), "GetNextFeature")
    return n


def _flag_count(asm_doc_w: Any, flag: str) -> int:
    n = 0
    for comp in components(asm_doc_w):
        try:
            if bool(getattr(_wrap(comp), flag)):
                n += 1
        except Exception:
            continue
    return n


def pattern_component(asm_doc_w: Any, kind: str = "linear", count: int = 3,
                      spacing: float = 0.05, angle: float = 2.0943951023932,
                      component_index: int = 0,
                      dmark: int = COMPONENT_DIR1,
                      cmark: int = COMPONENT_TO_PATTERN) -> Dict[str, Any]:
    """组件阵列（linear / circular）。

    `dmark`/`cmark` 默认取**官方正确值**（方向=2、组件=1），暴露出来只为做负面对照。
    """
    kind = (kind or "linear").lower()
    api = ("IFeatureManager.FeatureCircularPattern5" if kind == "circular"
           else "IFeatureManager.FeatureLinearPattern5")
    out: Dict[str, Any] = {"ok": False, "tool": "sw_pattern_component_%s" % kind,
                           "api": api, "detail": {}, "checks": {}}
    comps = components(asm_doc_w)
    names = component_names(asm_doc_w)
    out["detail"]["components_before"] = len(comps)
    out["detail"]["component_names"] = names
    if not comps:
        out["detail"]["error"] = "装配里没有组件"
        return out
    idx = max(0, min(component_index, len(comps) - 1))
    target, tname = comps[idx], names[idx] if idx < len(names) else None

    box = _component_box(target)
    if box is None:
        out["detail"]["error"] = "取不到组件包围盒（GetBox）"
        return out
    out["detail"]["component_box_mm"] = [round(v * 1000.0, 4) for v in box]
    out["detail"]["target"] = tname

    n0, f0 = _count_components(asm_doc_w), _count_features(asm_doc_w)
    pt = _select_direction(asm_doc_w, box, dmark)
    out["detail"]["direction_point_mm"] = ([round(v * 1000.0, 4) for v in pt]
                                          if pt else None)
    out["detail"]["direction_mark"] = dmark
    out["detail"]["component_mark"] = cmark
    if pt is None:
        out["detail"]["error"] = "方向边未选中（12 条棱中点全失败）"
        return out

    if not _select_component(asm_doc_w, target, tname, cmark):
        out["detail"]["error"] = "组件未选中"
        return out
    try:
        out["detail"]["selection_count"] = asm_doc_w.SelectionManager.GetSelectedObjectCount2(-1)
    except Exception:
        out["detail"]["selection_count"] = None

    fmw = asm_doc_w.FeatureManager
    if kind == "circular":
        ok, res = _call(fmw.FeatureCircularPattern5, int(count), float(angle),
                        False, NULL_DIMENSION_NAME, False, True, False, False,
                        False, False, 0, 0, NULL_DIMENSION_NAME, False)
    else:
        ok, res = _call(fmw.FeatureLinearPattern5, int(count), float(spacing),
                        1, 0.0, False, False, NULL_DIMENSION_NAME,
                        NULL_DIMENSION_NAME, False, False, False, False,
                        False, False, True, True, False, False, 0.0, 0.0,
                        False, False)
    out["detail"]["returned"] = type(res).__name__ if ok and res is not None else (
        res if not ok else None)
    if not ok:
        out["detail"]["error"] = res
        return out

    n1, f1 = _count_components(asm_doc_w), _count_features(asm_doc_w)
    instances = _flag_count(asm_doc_w, "IsPatternInstance")
    out["detail"].update({"components_after": n1, "features_before": f0,
                          "features_after": f1,
                          "is_pattern_instance": instances})
    out["checks"] = {
        "feature_created": res is not None,
        "components_increased": n1 > n0,
        "has_pattern_instances": instances > 0,
    }
    out["ok"] = all(out["checks"].values())
    return out


def mirror_components(doc_w: Any, plane_name: str = "前视基准面",
                      component_filter: str = "",
                      mirror_type: int = MIRROR_TYPE_ORIGIN) -> Dict[str, Any]:
    """镜像组件（现代 definition API）。

    关键：`IAssemblyDoc.MirrorComponents3` 在 SW2025 已 **Obsolete**，
    必须 `CreateDefinition(116)` → 设属性 → `CreateFeature`。
    """
    out: Dict[str, Any] = {"ok": False, "tool": "sw_mirror_component",
                           "api": "IFeatureManager.CreateDefinition/CreateFeature",
                           "detail": {}, "checks": {}}
    comps = components(doc_w)
    names = component_names(doc_w)
    out["detail"]["components_before"] = len(comps)
    out["detail"]["component_names"] = names
    if not comps:
        out["detail"]["error"] = "装配里没有组件"
        return out

    plane = None
    used_plane = None
    for nm in (plane_name,) + _PLANE_NAMES:
        if not nm:
            continue
        plane = find_feature(doc_w, nm)
        if plane is not None:
            used_plane = nm
            break
    out["detail"]["mirror_plane"] = used_plane
    if plane is None:
        out["detail"]["error"] = "找不到镜像面：%s" % plane_name
        return out

    pick, pick_names = [], []
    for comp, nm in zip(comps, names):
        if not component_filter or (nm and component_filter in nm):
            pick.append(comp)
            pick_names.append(nm)
    out["detail"]["mirrored_names"] = pick_names
    if not pick:
        out["detail"]["error"] = "没有匹配 component_filter 的组件"
        return out

    fmw = doc_w.FeatureManager
    ok, dataw = _call(fmw.CreateDefinition, SW_FM_MIRROR_COMPONENT)
    if not ok or dataw is None:
        out["detail"]["error"] = "CreateDefinition 失败：%s" % (dataw,)
        return out

    steps = [
        ("MirrorPlane", plane),
        ("MirrorType", int(mirror_type)),
        ("ComponentOrientationsAlignToComponentOrigin",
         var_i4_array([ORIENT_MX_MY] * len(pick))),
        ("ComponentsToInstanceAlignToComponentOrigin", var_dispatch_array(pick)),
        ("SyncFlexibleSubAssemblies", True),
        ("PreserveZAxis", True),
        ("CreateDerivedConfigurations", False),
    ]
    for prop, value in steps:
        try:
            setattr(dataw, prop, value)
        except Exception as exc:
            out["detail"]["error"] = "属性 %s 设置失败：%s" % (prop, exc)
            return out

    # 回读校验：comtypes 会静默丢弃对象数组，只有回读长度能发现
    try:
        back = dataw.ComponentsToInstanceAlignToComponentOrigin
        n_back = len(back) if back is not None else -1
    except Exception:
        n_back = -2
    out["detail"]["array_readback_len"] = n_back
    if n_back != len(pick):
        out["detail"]["error"] = "组件数组未真正传入（回读 %d，期望 %d）" % (n_back, len(pick))
        return out

    n0 = _count_components(doc_w)
    ok, feat = _call(fmw.CreateFeature, dataw)
    if not ok:
        out["detail"]["error"] = "CreateFeature 失败：%s" % (feat,)
        return out
    n1 = _count_components(doc_w)
    mirrored = _flag_count(doc_w, "IsMirrored")
    fname = val(_wrap(feat), "Name") if feat is not None else None
    out["detail"].update({"feature_name": fname, "components_after": n1,
                          "is_mirrored": mirrored})
    out["checks"] = {
        "feature_created": feat is not None,
        "components_increased": n1 > n0,
        "has_mirrored_components": mirrored > 0,
    }
    out["ok"] = all(out["checks"].values())
    return out


def _call(fn, *args) -> Tuple[bool, Any]:
    """调用 COM 方法：返回 `(ok, result|错误串)`。"""
    try:
        return True, fn(*args)
    except Exception as exc:      # noqa: BLE001
        return False, "%s: %s" % (type(exc).__name__, exc)

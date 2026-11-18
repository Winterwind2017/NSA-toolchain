"""从 COM 文档读回快照（晚绑定）。

判据只认这里读回来的值，**不认**任何调用方的返回值 —— 这是 JUDGE_SPEC 第〇节
第一条。所以读回要尽量全：类型、几何、属性、块表、表格单元格、图纸单位。

晚绑定的几个坑（本仓库实测）：

* `doc.ModelSpace.Count` / `Item(i)` 是唯一可靠的枚举方式（`list(...)` 不可用）；
* 实体类型要读 `ObjectName`（`AcDbCircle`），不要读 `EntityType` 常量号；
* 逐实体读属性必须**按类型白名单**读，乱读会在每个实体上抛一串异常；
* 表格单元格只能用 `GetText(r, c)`，`Rows`/`Columns` 是属性不是方法。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import time

from ..core import com
from .base import Drawing, Entity

# AcDbXxx → 判据里用的类型名
TYPE_MAP = {
    "AcDbLine": "LINE",
    "AcDbCircle": "CIRCLE",
    "AcDbArc": "ARC",
    "AcDbPolyline": "LWPOLYLINE",
    "AcDb2dPolyline": "POLYLINE",
    "AcDb3dPolyline": "POLYLINE",
    "AcDbEllipse": "ELLIPSE",
    "AcDbSpline": "SPLINE",
    "AcDbHatch": "HATCH",
    "AcDbText": "TEXT",
    "AcDbMText": "MTEXT",
    "AcDbRotatedDimension": "ROTATEDDIMENSION",
    "AcDbAlignedDimension": "ALIGNEDDIMENSION",
    "AcDbDiametricDimension": "DIAMETRICDIMENSION",
    "AcDbRadialDimension": "RADIALDIMENSION",
    "AcDbRadialDimensionLarge": "RADIALDIMENSION",
    "AcDb2LineAngularDimension": "ANGULARDIMENSION",
    "AcDb3PointAngularDimension": "ANGULARDIMENSION",
    "AcDbArcDimension": "ARCDIMENSION",
    "AcDbOrdinateDimension": "ORDINATEDIMENSION",
    "AcDbTable": "ACDBTABLE",
    "AcDbBlockReference": "BLOCKREFERENCE",
    "AcDbAttributeDefinition": "ATTRIBUTEDEFINITION",
    "AcDbAttribute": "ATTRIBUTE",
    "AcDbMLeader": "MULTILEADER",
    "AcDbFcf": "ACDBFCF",            # 形位公差
    "AcDbRegion": "REGION",
    "AcDb3dSolid": "3DSOLID",
    "AcDbSurface": "SURFACE",
    "AcDbWipeout": "WIPEOUT",
}

_DIM_TYPES = ("ROTATEDDIMENSION", "ALIGNEDDIMENSION", "DIAMETRICDIMENSION",
              "RADIALDIMENSION", "ANGULARDIMENSION", "ARCDIMENSION",
              "ORDINATEDIMENSION")

# 每类实体只读这些属性（乱读会大量抛异常，且慢）
PROPS = {
    "LINE": ("StartPoint", "EndPoint", "Length", "Angle", "Linetype"),
    "CIRCLE": ("Center", "Radius", "Area", "Circumference"),
    "ARC": ("Center", "Radius", "StartAngle", "EndAngle", "TotalAngle", "Area"),
    "LWPOLYLINE": ("Closed", "Length", "Area", "Coordinates"),
    "POLYLINE": ("Closed", "NumberOfVertices", "Length", "Area", "Coordinates"),
    "ELLIPSE": ("Center", "MajorRadius", "MinorRadius", "StartAngle",
                "EndAngle", "Area"),
    "SPLINE": ("NumberOfControlPoints", "NumberOfFitPoints", "Closed"),
    "HATCH": ("PatternName", "PatternScale", "Area"),
    "TEXT": ("TextString", "InsertionPoint", "Height", "Rotation", "StyleName"),
    "MTEXT": ("TextString", "InsertionPoint", "Width", "Height"),
    "ACDBTABLE": ("Rows", "Columns", "Width", "Height"),
    "BLOCKREFERENCE": ("Name", "EffectiveName", "InsertionPoint", "Rotation",
                       "XScaleFactor", "YScaleFactor", "HasAttributes"),
    "MULTILEADER": ("TextString", "LeaderType"),
    "ACDBFCF": ("TextString",),
    "3DSOLID": ("Volume", "Centroid", "SolidType"),
    "REGION": ("Area", "Centroid"),
    "SURFACE": ("Area",),
    "WIPEOUT": (),
}
for _t in _DIM_TYPES:
    # StyleName 是 `dim.update` 的判据需要（"更新后样式沿用"）；不读它就只能拿
    # 建图时的返回值当结论，违反"判据只吃读回"的约定。
    PROPS[_t] = ("Measurement", "TextPosition", "TextOverride", "StyleName")


def _get(e: Any, prop: str, attempts: int = 2, delay: float = 0.2) -> Any:
    """读一个属性，给"AutoCAD 还没准备好"留一次机会。

    本机实测：刚创建/刚激活的文档上偶发 `AttributeError: <unknown>.X`
    （DISPID 查询失败，不是属性不存在）。判据不能因此谎报"没做到"，但也不能
    无限重试——所以只多试一次，失败就如实不写入该属性（判据会看见缺值）。
    """
    last: Optional[BaseException] = None
    for _ in range(attempts):
        try:
            return getattr(e, prop)
        except AttributeError as exc:
            last = exc
            time.sleep(delay)
        except Exception:                               # noqa: BLE001
            raise
    assert last is not None
    raise last


def type_of(entity: Any) -> str:
    """实体类型名。读不到 ObjectName 时返回空串（判据会因此失败，不会瞎猜）。"""
    try:
        name = str(_get(entity, "ObjectName", attempts=1))
    except Exception:                                   # noqa: BLE001
        return ""
    return TYPE_MAP.get(name, name.replace("AcDb", "").upper())


def _call(fn, default: Any = None, label: str = "") -> Any:
    """跑一个 COM 读操作：忙/拒收就重试，其它失败按 `default` 处理。

    读回路径上也会撞到 `RPC_E_CALL_REJECTED`（AutoCAD 正忙），把它当"读不到"
    会让判据误报。读不到是判失败的理由，但不能因为忙就判失败。
    """
    try:
        return com.retry(fn, label=label)
    except Exception:                                   # noqa: BLE001
        return default


def getvar(doc: Any, name: str) -> Optional[int]:
    val = _call(lambda: doc.GetVariable(name), None, "GetVariable(%s)" % name)
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _pts(v: Any) -> Optional[List[List[float]]]:
    """VARIANT 平铺坐标 → [[x, y], ...]。"""
    try:
        vals = [float(x) for x in v]
    except (TypeError, ValueError):
        return None
    if len(vals) % 2:
        return None
    return [[vals[i], vals[i + 1]] for i in range(0, len(vals), 2)]


def read_attributes(ref: Any) -> List[Dict[str, Any]]:
    """块引用的属性（Tag/Value 读回，含位置与是否可见）。"""
    out: List[Dict[str, Any]] = []
    try:
        if not bool(getattr(ref, "HasAttributes")):
            return out
    except Exception:                                   # noqa: BLE001
        return out
    try:
        atts = ref.GetAttributes()
    except Exception:                                   # noqa: BLE001
        return out
    if atts is None:
        return out
    try:
        items = list(atts)
    except TypeError:
        items = [atts]
    for at in items:
        if at is None:
            continue
        row: Dict[str, Any] = {}
        for key in ("TagString", "TextString", "PromptString", "Invisible",
                    "Constant", "Height", "InsertionPoint", "Handle"):
            try:
                row[key] = getattr(at, key)
            except Exception:                           # noqa: BLE001
                pass
        if "InsertionPoint" in row:
            try:
                row["InsertionPoint"] = [float(x) for x in row["InsertionPoint"]]
            except Exception:                           # noqa: BLE001
                pass
        out.append(row)
    return out


def read_table_cells(tbl: Any) -> Dict[str, Any]:
    """表格读回：行列数 + 全部单元格文字。"""
    out: Dict[str, Any] = {"rows": None, "columns": None, "cells": []}
    try:
        rows, cols = int(tbl.Rows), int(tbl.Columns)
    except Exception:                                   # noqa: BLE001
        return out
    out["rows"], out["columns"] = rows, cols
    grid = []
    for r in range(rows):
        line = []
        for c in range(cols):
            try:
                line.append(str(tbl.GetText(r, c)))
            except Exception:                           # noqa: BLE001
                line.append(None)
        grid.append(line)
    out["cells"] = grid
    return out


def _read_block_table(doc: Any) -> Dict[str, Dict[str, Any]]:
    """块表：名字 → {count, attdefs:[{tag,value}], types:{type: n}}。"""
    out: Dict[str, Dict[str, Any]] = {}
    try:
        blocks = com.retry(lambda: doc.Blocks, label="Blocks")
        n = int(com.retry(lambda: blocks.Count, label="Blocks.Count"))
    except Exception:                                   # noqa: BLE001
        return out
    for i in range(n):
        try:
            blk = blocks.Item(i)
            name = str(blk.Name)
            count = int(blk.Count)
        except Exception:                               # noqa: BLE001
            continue
        # 布局块（*Model_Space / *Paper_Space…）不是用户块，但读一下无妨；
        # 判据只按块名精确查。
        row: Dict[str, Any] = {"count": count, "attdefs": [], "types": {}}
        for j in range(count):
            try:
                sub = blk.Item(j)
            except Exception:                           # noqa: BLE001
                continue
            t = type_of(sub)
            row["types"][t] = row["types"].get(t, 0) + 1
            if t == "ATTRIBUTEDEFINITION":
                item = {}
                for key in ("TagString", "TextString", "PromptString",
                            "Height", "Mode", "Handle", "InsertionPoint"):
                    try:
                        item[key] = getattr(sub, key)
                    except Exception:                   # noqa: BLE001
                        pass
                row["attdefs"].append(item)
        out[name] = row
    return out


def _color_value(obj: Any) -> Any:
    """图层/文字的颜色：可能是 int，也可能是 AcCmColor 对象。"""
    if obj is None:
        return None
    for attr in ("ColorIndex", "RGB"):
        try:
            return int(getattr(obj, attr))
        except Exception:                               # noqa: BLE001
            continue
    try:
        return str(obj)
    except Exception:                                   # noqa: BLE001
        return None


def _read_named_table(collection: Any, props: tuple,
                      label: str) -> Dict[str, Dict[str, Any]]:
    """把 Layers / TextStyles / DimStyles / Layouts 这类命名表读成字典。"""
    out: Dict[str, Dict[str, Any]] = {}
    try:
        n = int(com.retry(lambda: collection.Count, label=label + ".Count"))
    except Exception:                                   # noqa: BLE001
        return out
    for i in range(n):
        try:
            item = com.retry(lambda i=i: collection.Item(i), label=label + ".Item")
            name = str(item.Name)
        except Exception:                               # noqa: BLE001
            continue
        row: Dict[str, Any] = {}
        for prop in props:
            try:
                row[prop] = _get(item, prop, attempts=1)
            except Exception:                           # noqa: BLE001
                continue
        out[name] = row
    return out


_TABLE_PROPS = {
    "layers": ("Color", "Linetype", "Lineweight", "Plottable", "Freeze", "Lock",
               "LayerOn"),
    "textstyles": ("FontFile", "BigFontFile", "Height", "Width", "LastHeight"),
    "dimstyles": ("DimScale", "DimTxt", "DimAsz"),
}


_META_VARS = ("DIMTXT", "DIMTOL", "DIMTP", "DIMTM", "MEASUREMENT",
              "CLAYER", "CVPORT", "VIEWSIZE")


def _read_meta(doc: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"vars": {}, "view": {}}
    for name in _META_VARS:
        val = _call(lambda n=name: doc.GetVariable(n), None, "GetVariable(%s)" % name)
        if val is None:
            continue
        if name == "CLAYER":
            out["vars"][name] = str(val)
            continue
        try:
            out["vars"][name] = float(val)
        except (TypeError, ValueError):
            out["vars"][name] = val
    for name, key in (("VIEWCTR", "center"), ("VIEWSIZE", "size"),
                      ("VIEWDIR", "dir")):
        val = _call(lambda n=name: doc.GetVariable(n), None, "GetVariable(%s)" % name)
        if key == "size":
            try:
                out["view"][key] = float(val)
            except (TypeError, ValueError):
                pass
        else:
            try:
                out["view"][key] = [float(x) for x in val]
            except (TypeError, ValueError):
                pass
    return out


def _retry_get(obj: Any, attr: str, attempts: int = 3) -> Any:
    """取属性：AutoCAD 刚打开文档时命名表可能还没就绪，短重试。"""
    for i in range(attempts):
        try:
            return getattr(obj, attr)
        except Exception:                           # noqa: BLE001
            if i == attempts - 1:
                return None
            time.sleep(0.3)
    return None


def _retry_call(fn: Any, label: str, attempts: int = 3) -> Any:
    for i in range(attempts):
        try:
            return fn()
        except Exception:                           # noqa: BLE001
            if i == attempts - 1:
                return None
            time.sleep(0.3)
    return None


def read_tables(doc: Any) -> Dict[str, Any]:
    """读命名表（图层/文字样式/标注样式/布局）。判据用来做"表级"复核。"""
    out: Dict[str, Any] = {"layers": {}, "textstyles": {}, "dimstyles": {},
                           "layouts": {}, "active_layer": None,
                           "active_dimstyle": None}
    for key, attr in (("layers", "Layers"), ("textstyles", "TextStyles"),
                      ("dimstyles", "DimStyles"), ("layouts", "Layouts")):
        try:
            coll = com.retry(lambda a=attr: getattr(doc, a), label=attr)
        except Exception:                               # noqa: BLE001
            continue
        out[key] = _read_named_table(coll, _TABLE_PROPS.get(key, ()), attr)
    for key, attr in (("active_layer", "ActiveLayer"),
                      ("active_dimstyle", "ActiveDimStyle")):
        try:
            out[key] = str(getattr(getattr(doc, attr), "Name"))
        except Exception:                               # noqa: BLE001
            pass
    # 每个布局里的视口数（layout.multipage 的判据要用）
    out["layout_viewports"] = {}
    layouts = _retry_get(doc, "Layouts")
    if layouts is not None:
        try:
            n_lay = int(layouts.Count)
        except Exception:                           # noqa: BLE001
            n_lay = 0
        for i in range(n_lay):
            lay = _retry_call(lambda i=i: layouts.Item(i), "Layouts.Item")
            if lay is None:
                continue
            name = str(getattr(lay, "Name", ""))
            if not name:
                continue
            n = 0
            blk = _retry_get(lay, "Block")
            if blk is not None:
                try:
                    for j in range(int(blk.Count)):
                        if str(blk.Item(j).ObjectName) == "AcDbViewport":
                            n += 1
                except Exception:                   # noqa: BLE001
                    pass
            out["layout_viewports"][name] = n
    # 颜色对象归一化成 int
    for name, row in out["layers"].items():
        if "Color" in row:
            row["Color"] = _color_value(row["Color"])
    return out


def read_drawing(doc: Any, source: str = "memory") -> Drawing:
    """把一个文档读成 :class:`Drawing`。"""
    d = Drawing(source=source, insunits=getvar(doc, "INSUNITS"))
    try:
        d.meta["doc_name"] = str(doc.Name)
    except Exception:                                   # noqa: BLE001
        d.meta["doc_name"] = None
    d.meta["dismassoc"] = getvar(doc, "DIMASSOC")
    d.meta["blocks"] = _read_block_table(doc)
    d.meta["tables"] = read_tables(doc)
    d.meta.update(_read_meta(doc))

    try:
        ms = com.retry(lambda: doc.ModelSpace, label="ModelSpace")
        n = int(com.retry(lambda: ms.Count, label="ModelSpace.Count"))
    except Exception as exc:                            # noqa: BLE001
        d.meta["read_error"] = "%s: %s" % (type(exc).__name__, exc)
        return d

    for i in range(n):
        try:
            e = ms.Item(i)
        except Exception:                               # noqa: BLE001
            continue
        t = type_of(e)
        attrs: Dict[str, Any] = {}
        for prop in PROPS.get(t, ()):
            try:
                val = _get(e, prop)
            except Exception:                           # noqa: BLE001
                continue
            if prop in ("StartPoint", "EndPoint", "Center", "InsertionPoint",
                        "TextPosition"):
                try:
                    val = [float(x) for x in val]
                except Exception:                       # noqa: BLE001
                    pass
            if prop == "Coordinates":
                # 判据要的是顶点对，不是平铺的浮点数组
                attrs["vertices"] = _pts(val)
                continue
            attrs[prop] = val
        try:
            attrs["ObjectName"] = str(_get(e, "ObjectName", attempts=1))
        except Exception:                               # noqa: BLE001
            pass
        try:
            attrs["Layer"] = str(_get(e, "Layer", attempts=1))
        except Exception:                               # noqa: BLE001
            pass
        if t == "BLOCKREFERENCE":
            attrs["attributes"] = read_attributes(e)
        if t == "ACDBTABLE":
            attrs.update(read_table_cells(e))
        try:
            handle = str(_get(e, "Handle", attempts=1))
        except Exception:                               # noqa: BLE001
            handle = ""
        d.entities.append(Entity(handle=handle, type=t, attrs=attrs))
    return d


def attrs_by_tag(ref_attrs: Dict[str, Any]) -> Dict[str, Any]:
    """块引用属性 → {Tag: TextString}。"""
    out: Dict[str, Any] = {}
    for a in ref_attrs.get("attributes") or []:
        tag = a.get("TagString")
        if tag is not None:
            out[str(tag)] = a.get("TextString")
    return out


def attdefs_by_tag(block_row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for a in block_row.get("attdefs") or []:
        tag = a.get("TagString")
        if tag is not None:
            out[str(tag)] = a.get("TextString")
    return out

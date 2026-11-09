"""DXF 读回：优先 ezdxf（spec 点名的做法），没有就用最小 group-code 解析器。

`docs/JUDGE_SPEC.md` 2.7 把"DXF 用 ezdxf 读回实体计数 == 内存计数"标为**最强
的一条**。这里把它做成两级：

* 装了 ezdxf → 用它，`reader` 字段写清版本（真机跑得到的就是这一级）；
* 没装 → 用本模块的 group-code 解析器数 `ENTITIES` 段，`reader` 写
  `minimal-groupcode`，并在 `limitations` 里说明"只数个数与类型，不解析几何"。

两级都返回**族直方图**（DIM/INSERT/TABLE…），因为 DXF 的实体名与 ActiveX 的
`AcDbXxx` 不是一一对应：七个标注类型在 DXF 里全是 `DIMENSION`。
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

# ActiveX 类型 → DXF 族（判据两边都按族比较）
_FAMILY_BY_ACTIVEX = {
    "LINE": "LINE",
    "CIRCLE": "CIRCLE",
    "ARC": "ARC",
    "LWPOLYLINE": "POLYLINE",
    "POLYLINE": "POLYLINE",
    "ELLIPSE": "ELLIPSE",
    "SPLINE": "SPLINE",
    "HATCH": "HATCH",
    "TEXT": "TEXT",
    "MTEXT": "TEXT",
    "ROTATEDDIMENSION": "DIM",
    "ALIGNEDDIMENSION": "DIM",
    "DIAMETRICDIMENSION": "DIM",
    "RADIALDIMENSION": "DIM",
    "ANGULARDIMENSION": "DIM",
    "ARCDIMENSION": "DIM",
    "ORDINATEDIMENSION": "DIM",
    "BLOCKREFERENCE": "INSERT",
    "ACDBTABLE": "TABLE",
    "ATTRIBUTEDEFINITION": "ATTDEF",
    "ATTRIBUTE": "ATTRIB",
    "MULTILEADER": "MULTILEADER",
    "ACDBFCF": "TOLERANCE",
    "REGION": "REGION",
    "3DSOLID": "3DSOLID",
    "SURFACE": "SURFACE",
}
_FAMILY_BY_DXF = {
    "LINE": "LINE",
    "CIRCLE": "CIRCLE",
    "ARC": "ARC",
    "LWPOLYLINE": "POLYLINE",
    "POLYLINE": "POLYLINE",
    "ELLIPSE": "ELLIPSE",
    "SPLINE": "SPLINE",
    "HATCH": "HATCH",
    "TEXT": "TEXT",
    "MTEXT": "TEXT",
    "DIMENSION": "DIM",
    "ARC_DIMENSION": "DIM",
    "LARGE_RADIAL_DIMENSION": "DIM",
    "INSERT": "INSERT",
    "ACAD_TABLE": "TABLE",
    "ATTDEF": "ATTDEF",
    "ATTRIB": "ATTRIB",
    "MULTILEADER": "MULTILEADER",
    "TOLERANCE": "TOLERANCE",
    "REGION": "REGION",
    "3DSOLID": "3DSOLID",
    "SURFACE": "SURFACE",
}


def family_of_activetype(type_name: str) -> str:
    return _FAMILY_BY_ACTIVEX.get(type_name, type_name or "UNKNOWN")


def family_of_dxftype(dxf_type: str) -> str:
    t = (dxf_type or "").upper()
    return _FAMILY_BY_DXF.get(t, t or "UNKNOWN")


def histogram(counts: Dict[str, int], family) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for k, n in counts.items():
        fam = family(k)
        out[fam] = out.get(fam, 0) + int(n)
    return out


def _iter_pairs(text: str):
    """容错的 (code, value) 扫描。

    严格的“每两行一对”在本机实测会错位：MTEXT 的 group 1 如果是空串，
    AutoCAD 会写出**空行**，偶发连续空行就把后面的对齐全推歪（实测
    probe.dxf 在 2656 行开始把 `1.0` 当成 code）。所以这里遇到解析不出
    整数的行就跳过去，让扫描自己重新对齐。
    """
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        try:
            code = int(lines[i].strip())
        except ValueError:
            i += 1
            continue
        if i + 1 >= n:
            return
        yield code, lines[i + 1].strip()
        i += 2


def _minimal_sections(data: bytes) -> Dict[str, int]:
    """数 ENTITIES 段里每个 type 的个数（code 0 的值）。"""
    text = data.decode("latin-1", "replace")
    counts: Dict[str, int] = {}
    section: Optional[str] = None
    pending = False
    for code, value in _iter_pairs(text):
        if code == 0:
            if value == "SECTION":
                pending = True
            elif value == "ENDSEC":
                section = None
            elif section == "ENTITIES":
                counts[value] = counts.get(value, 0) + 1
        elif code == 2 and pending:
            section = value
            pending = False
    return counts


def read(path: str) -> Dict[str, Any]:
    """读一个 DXF，返回 {counts, families, reader, sections, ok, why}。"""
    out: Dict[str, Any] = {
        "path": path, "bytes": 0, "reader": None, "counts": {},
        "families": {}, "total": 0, "sections": [], "ok": False,
        "why": "", "limitations": [],
    }
    try:
        with io.open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        out["why"] = "不可读：%s" % (exc,)
        return out
    out["bytes"] = len(data)
    if not data:
        out["why"] = "文件为空"
        return out

    with io.open(path, "rb") as fh:
        head = fh.read(2048)
    for tag in (b"SECTION", b"HEADER", b"ENTITIES"):
        if tag not in head and tag not in data[:65536]:
            out["why"] = "缺少标记 %s" % tag.decode()
            return out

    counts: Optional[Dict[str, int]] = None
    try:
        import ezdxf                                    # type: ignore
    except ImportError:
        ezdxf = None
    if ezdxf is not None:
        try:
            dxf = ezdxf.readfile(path)
            counts = {}
            for e in dxf.modelspace():
                t = e.dxftype()
                counts[t] = counts.get(t, 0) + 1
            out["reader"] = "ezdxf %s" % getattr(ezdxf, "__version__", "?")
        except Exception as exc:                        # noqa: BLE001
            out["why"] = "ezdxf 解析失败：%s: %s" % (type(exc).__name__, exc)
            return out
    else:
        counts = _minimal_sections(data)
        out["reader"] = "minimal-groupcode"
        out["limitations"].append("未安装 ezdxf：只数实体个数与类型，不解析几何")

    out["counts"] = counts
    out["families"] = histogram(counts, family_of_dxftype)
    out["total"] = sum(counts.values())
    out["sections"] = _sections(data)
    out["ok"] = True
    return out


def _sections(data: bytes) -> List[str]:
    text = data.decode("latin-1", "replace")
    out: List[str] = []
    pending = False
    for code, value in _iter_pairs(text):
        if code == 0 and value == "SECTION":
            pending = True
        elif code == 2 and pending:
            out.append(value)
            pending = False
    return out

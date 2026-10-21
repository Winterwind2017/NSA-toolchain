"""四级判据实现（`docs/JUDGE_SPEC.md`）。

四个族，与 `docs/registry.yaml` 的 family 对齐：

| 族 | 模块 | 判据 |
|---|---|---|
| `geom`（草图几何） | `geom.py` | circle / line / rect |
| `dim`（标注） | `dim.py` | linear / diametric / radial + 不存在的 API 负例 |
| `export`（导出） | `export.py` | dwg / dxf / pdf |
| `block-table`（块/属性/表格） | `block_table.py` | block.define / insert_with_attributes / table.bom |

每个判据满足 spec 第五节：

* `ok` 只在 `base.verdict()` 里由 `all(checks.values())` 算出；
* `detail` 里有能人工核对的数字（半径/面积/长度/页数/尺寸/件数）；
* 失败时 `raw` 保留原始读回值。

`JUDGES` 是机器可读清单：`registry` 字段指向 registry.yaml 的能力 id，
离线自检会核对"判据覆盖的 id 都真实存在"。
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import block_table, dim, export, geom
from .base import Drawing, Entity, JudgeError, Readback, verdict
from .read import attdefs_by_tag, attrs_by_tag, read_drawing

FAMILIES = {
    "geom": geom,
    "dim": dim,
    "export": export,
    "block-table": block_table,
}

# 判据清单：id → 元信息。id 与 registry 的能力 id 同名（负例额外标 negative）。
JUDGES: Dict[str, Dict[str, Any]] = {
    "geom.circle": {
        "fn": geom.judge_circle, "family": "geom", "level": "L1–L4",
        "registry": ["geom.circle"],
        "about": "圆：计数/类型/Center+Radius/面积≈πR²/重开复核",
    },
    "geom.line": {
        "fn": geom.judge_line, "family": "geom", "level": "L1–L4",
        "registry": ["geom.line"],
        "about": "直线：计数/类型/两端点/长度=√Δ²/重开复核",
    },
    "geom.rect": {
        "fn": geom.judge_rect, "family": "geom", "level": "L1–L4",
        "registry": ["geom.rect"],
        "about": "矩形：闭合多段线/4 顶点/面积=w×h/重开复核",
    },
    "dim.linear": {
        "fn": dim.judge_linear, "family": "dim", "level": "L1–L4",
        "registry": ["dim.linear"],
        "about": "线性标注：Measurement≈输入/文字在尺寸线外侧/重开复核",
    },
    "dim.diametric": {
        "fn": dim.judge_diametric, "family": "dim", "level": "L1–L4",
        "registry": ["dim.diametric"],
        "about": "直径标注：Measurement≈2R/重开复核",
    },
    "dim.radial": {
        "fn": dim.judge_radial, "family": "dim", "level": "L1–L4",
        "registry": ["dim.radial"],
        "about": "半径标注：Measurement≈R/重开复核",
    },
    "dim.api_missing": {
        "fn": dim.judge_raised, "family": "dim", "level": "负例",
        "registry": ["dim.diametric"], "negative": True,
        "about": "负例：AddDimLinear 不存在，调用必须抛 AttributeError",
    },
    "export.dwg": {
        "fn": export.judge_dwg, "family": "export", "level": "L0–L4",
        "registry": ["export.dwg"],
        "about": "DWG：文件新/AC10 魔数/重开后计数与句柄一致",
    },
    "export.dxf": {
        "fn": export.judge_dxf, "family": "export", "level": "L0–L4",
        "registry": ["export.dxf"],
        "about": "DXF：HEADER+ENTITIES 段/ezdxf 族计数=内存/重新导入计数一致",
    },
    "export.pdf": {
        "fn": export.judge_pdf, "family": "export", "level": "L0–L3",
        "registry": ["export.pdf"],
        "about": "PDF：%PDF- 头/1 页/A3 尺寸/解压后有绘图指令（非空白）",
    },
    "block.define": {
        "fn": block_table.judge_block_define, "family": "block-table",
        "level": "L1–L4", "registry": ["block.define"],
        "about": "块定义：Blocks 表新增/块内图元数/Attdef 数与默认值/重开复核",
    },
    "block.insert_with_attributes": {
        "fn": block_table.judge_block_insert, "family": "block-table",
        "level": "L1–L4", "registry": ["block.insert_with_attributes"],
        "about": "块插入：引用+1/块名/属性个数=Attdef 数/逐 Tag 比对/重开复核",
    },
    "block.short_attributes": {
        "fn": block_table.judge_block_insert, "family": "block-table",
        "level": "负例", "registry": ["block.insert_with_attributes"],
        "negative": True,
        "about": "负例：只填一半属性 → 属性个数判据必须失败",
    },
    "table.bom": {
        "fn": block_table.judge_table, "family": "block-table", "level": "L1–L4",
        "registry": ["table.bom"],
        "about": "BOM 表：ACDBTABLE/行列数/逐格文字/合计=明细之和/重开复核",
    },
}


def get(judge_id: str) -> Dict[str, Any]:
    if judge_id not in JUDGES:
        raise JudgeError("没有判据 %r（可用：%s）"
                         % (judge_id, ", ".join(sorted(JUDGES))))
    return JUDGES[judge_id]


def by_family(family: str) -> List[str]:
    return sorted(k for k, v in JUDGES.items() if v["family"] == family)


def registry_ids() -> List[str]:
    out = set()
    for meta in JUDGES.values():
        out.update(meta.get("registry") or [])
    return sorted(out)


__all__ = [
    "Drawing", "Entity", "Readback", "JudgeError", "verdict",
    "FAMILIES", "JUDGES", "by_family", "get", "registry_ids",
    "attdefs_by_tag", "attrs_by_tag", "read_drawing",
]

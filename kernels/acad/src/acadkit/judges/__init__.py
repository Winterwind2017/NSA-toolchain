"""判据实现（`docs/JUDGE_SPEC.md`）。

| 模块 | 内容 |
|---|---|
| `base.py` | `Readback` / `Drawing` / `Entity` / `verdict()`（ok 只由 all(checks) 算出）/ `value_same` |
| `read.py` | COM 读回：实体白名单、命名表、块表、属性、表格单元格、视图/变量 |
| `generic.py` | 通用判据：新增实体 / 多类型计数 / 命名表 / 体积 |
| `geom.py` `dim.py` `dim_extra.py` `text*` | 几何 / 标注 / 文字 |
| `symbol.py` `gdt*` `frame.py` | 符号 / 形位公差 / 图框布局 |
| `block_table.py` `table*` | 块 / 属性 / 表格 |
| `layer.py` `env.py` `view.py` | 图层 / 系统变量 / 视图 |
| `solid.py` `fit.py` | 3D 体积、布尔、剖切 / 配合代号表 |
| `export.py` `pdfinfo.py` `dxfinfo.py` | DWG/DXF/PDF 导出判据与最小解析器 |
| `case.py` | 用例执行器：文档生命周期 + 存盘重开 + 合并 checks |
| `envguard.py` | 环境自检护栏 |

能力 → 判据的映射在 `acadkit/caps.py`（唯一事实来源），这里只提供实现。
"""

from __future__ import annotations

from .base import (Drawing, Entity, JudgeError, Readback, value_same, verdict)
from .read import attdefs_by_tag, attrs_by_tag, read_drawing, read_tables

__all__ = [
    "Drawing", "Entity", "Readback", "JudgeError", "verdict", "value_same",
    "attdefs_by_tag", "attrs_by_tag", "read_drawing", "read_tables",
]

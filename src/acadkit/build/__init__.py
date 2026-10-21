"""造图动作（builders）：把"怎么画"从测试里搬出来。

分开的理由：**测试不该拥有生产代码**。

* `build/`  ——怎么画（本包）：参数化动作，CLI 与测试共用；
* `judges/` ——怎么证明画对了；
* `caps.py` ——把两者接起来（能力表 + 用例）。
"""

from __future__ import annotations

from . import (block_table, boolean, dim, envvars, export, frame, gdt, geom,
               layer, lisp, solid, symbol, table, text, view)
from .helpers import (add, add_solid, basic_drawing, dbl, define_block,
                      handle_of, insert_block, lisp_handles, ms_of, objs, pt,
                      region_from_polyline, send)

__all__ = [
    "pt", "dbl", "objs", "ms_of", "send", "add", "add_solid",
    "basic_drawing", "define_block", "insert_block",
    "region_from_polyline", "handle_of", "lisp_handles",
    "block_table", "boolean", "dim", "envvars", "export", "frame", "gdt",
    "geom", "layer", "lisp", "solid", "symbol", "table", "text", "view",
]

"""纯算法子集：不碰 COM、不依赖 MCP SDK 的几何与特征图模块。

* ``contracts``        —— 输入契约校验
* ``feature_graph``    —— Feature Graph IR 的校验与编译
* ``part_generators``  —— 参数化零件（block/cylinder/tube/flange/stepped_shaft）
* ``involute_gear``    —— 渐开线直齿轮
* ``gearbox``          —— 两级平行轴减速器
* ``output_shaft``     —— 按图纸的输出轴
* ``interactive`` / ``native_features`` / ``primitives`` —— 特征树与基础几何
"""

from . import (contracts, feature_graph, gearbox, helical_gear, interactive,
               internal_gear, involute_gear, keyways, native_features,
               output_shaft, part_generators, primitives, spline)  # noqa: F401

__all__ = [
    "contracts", "feature_graph", "part_generators", "involute_gear",
    "gearbox", "output_shaft", "helical_gear", "internal_gear", "spline",
    "keyways", "interactive", "native_features", "primitives",
]

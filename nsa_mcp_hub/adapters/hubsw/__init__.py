"""CAD-Agent-Hub 的纯算法子集（MIT，见 ATTRIBUTION.md）。

只保留**不碰 COM、不依赖 mcp** 的模块：齿轮数学、特征图编译、零件生成器，
以及“只操作传入的 COM 对象、自身不建立连接”的特征交互层。
"""

from . import (contracts, feature_graph, gearbox, interactive, involute_gear,
               native_features, output_shaft, part_generators)  # noqa: F401

__all__ = ["contracts", "feature_graph", "gearbox", "interactive", "involute_gear",
           "native_features", "output_shaft", "part_generators"]

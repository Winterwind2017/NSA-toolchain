"""SolidWorks 特征交互层（只操作传入的 COM 对象，自身不建立连接）。

本目录只保留不依赖外部 COM 会话、也不依赖 MCP SDK 的部分：
`interactive` 封装特征树读写，`native_features` 做原生特征翻译，
`primitives` 提供基础几何参数。
"""

from . import interactive, native_features, primitives  # noqa: F401

__all__ = ["interactive", "native_features", "primitives"]

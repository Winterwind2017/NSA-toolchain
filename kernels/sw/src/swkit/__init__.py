"""swkit —— 一套自己的 SolidWorks 自动化工具内核

四层：

1. `swkit.core`     —— COM 双栈（pywin32 / comtypes）桥接、选择标记常量、错误类型
2. `swkit.api`      —— 高层对象 API（`SolidWorksApp`：文档/草图/特征/配合/出图）
3. `swkit.verified` —— **实测通过**的实现（带自证字典），与 registry 对应
4. `swkit.mcp` / `swkit.cli` —— 两个入口，同一套能力

设计原则：**宁可少一个工具，也不要一个"看起来能跑"的工具。**
每个宣称可用的能力都在 `swkit.registry` 里有登记，附 API 名与实测判据。
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "SolidWorksApp", "pattern_component", "mirror_components",
    "REGISTRY", "summary", "__version__",
]

from .api.app import SolidWorksApp          # noqa: E402
from .registry import REGISTRY, summary     # noqa: E402
from .verified.assembly import mirror_components, pattern_component  # noqa: E402

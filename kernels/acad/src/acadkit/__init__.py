"""acadkit —— AutoCAD 自动化内核。

设计原则（与 swkit 同构）：

1. **判据优先**：每个能力都要能证明"做对了"，说不清判据的不标 verified。
2. **只附加，不启动**：`status` 类只读命令绝不隐式拉起 AutoCAD
   （`win32com.client.Dispatch` 在未运行时**会启动一个隐藏实例**，本仓库踩过）。
3. **环境不外泄**：任何用例前后都要验 profile / TRUSTEDPATHS / .sv$ 残留。
"""

__version__ = "0.1.0"

__all__ = ["__version__"]

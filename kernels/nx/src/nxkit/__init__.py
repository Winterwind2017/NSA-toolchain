"""nxkit —— UG NX 2512 自动化内核（Python journal + 判据）。

宿主侧（普通 Python 3.12）只负责：拼 job、起 run_journal、收 result、跑判据。
真正碰 NX 的代码在 `nxkit.runtime`，由 run_journal 在 NX 进程内 import。
"""

__version__ = "0.1.0"
__all__ = ["__version__"]

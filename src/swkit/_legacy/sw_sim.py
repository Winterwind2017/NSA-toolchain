# -*- coding: utf-8 -*-
"""兼容层：真正的实现已合并到 D:\\bililive\\mcp-patches\\sw_sim.py（2026-11-03）。

为什么保留这个文件：`swkit._legacy.runner` 的 SCRIPTS 表里 `"sim": "sw_sim.py"`，
工具仍按这个路径找脚本。以前这里是一份 22 KB 的旧实现，于是出现
「主脚本修好了、工具走的还是旧脚本」的假修复（`--timeout` 不被识别、
CreateMesh 单位没换算、没有网格规模闸门）。现在只做转发，单一来源。
"""

from __future__ import annotations

import os
import runpy
import sys

CANON = os.environ.get("SWKIT_SIM_SCRIPT") or r"D:\bililive\mcp-patches\sw_sim.py"

if not os.path.isfile(CANON):
    raise SystemExit("找不到主脚本：%s" % CANON)

sys.argv[0] = CANON
runpy.run_path(CANON, run_name="__main__")

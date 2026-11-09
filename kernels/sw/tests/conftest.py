"""tests/conftest.py —— pytest 配置

真机测试默认**跳过**（它们要开 SolidWorks、动文件、跑几分钟）。启用方式：

    pytest tests -q --live                 # 全部
    pytest tests -q --live -k drawing      # 只跑出图

为什么默认关：
* 这些用例需要本机装 SolidWorks 2025 且没有别的会话占用；
* 会在 `swkit` 的临时目录里建模、改文件——CI 上不该跑。

标记：
* `live` —— 需要真实 SolidWorks。
"""

from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
_vendor = os.environ.get("SWKIT_VENDOR")
if _vendor and os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--live", action="store_true", default=False,
                     help="跑需要真实 SolidWorks 的用例（默认跳过）")
    parser.addoption("--live-timeout", type=float, default=1800.0,
                     help="单个真机套件的超时秒数")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: 需要真实 SolidWorks 的用例")


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="需要真实 SolidWorks：加 --live 启用")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)

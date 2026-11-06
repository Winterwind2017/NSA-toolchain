"""输入契约校验。

生成器和特征图编译器只依赖两三条最基本的前提：数字必须是**有限正数**、
文本必须非空。不满足就抛 :class:`ContractError`，由工具层接住并转成
``{ok: false, errors: [...]}``，不会让一次坏参数炸掉整个 kit。
"""

from __future__ import annotations

import math
from typing import Any


class ContractError(ValueError):
    """参数不满足契约。"""


def require_text(value: Any, name: str) -> str:
    """要求非空文本，返回去空白后的值。"""
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string")
    return value.strip()


def require_positive(value: Any, name: str) -> float:
    """要求有限正数（接受 int/float/数字字符串）。"""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{name} must be a number") from exc
    if not math.isfinite(number):
        raise ContractError(f"{name} must be finite")
    if number <= 0.0:
        raise ContractError(f"{name} must be greater than zero")
    return number

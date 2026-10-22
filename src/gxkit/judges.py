"""判据：把 readings 与 expect 对上。容差按量级分档（同 nxkit 的做法）。"""

from __future__ import annotations

from typing import Any


def tol(value: float) -> float:
    v = abs(float(value))
    if v >= 100:
        return 0.5
    if v >= 1:
        return 1e-3
    return 1e-6


def check(name: str, got: Any, want: Any) -> str | None:
    """返回 None 表示通过，否则返回人类可读的失败原因。"""
    if isinstance(want, dict) and ("min" in want or "max" in want):
        if got is None:
            return "%s 缺失（期望 %s）" % (name, want)
        if not isinstance(got, (int, float)):
            return "%s 不是数字：%r" % (name, got)
        lo, hi = want.get("min"), want.get("max")
        if lo is not None and got < lo - tol(lo):
            return "%s 太小：%s < %s" % (name, got, lo)
        if hi is not None and got > hi + tol(hi):
            return "%s 太大：%s > %s" % (name, got, hi)
        return None
    if isinstance(want, float) or isinstance(want, int):
        if got is None:
            return "%s 缺失（期望 %r）" % (name, want)
        if not isinstance(got, (int, float)):
            return "%s 不是数字：%r" % (name, got)
        if abs(float(got) - float(want)) > tol(want):
            return "%s 不符：%s != %s" % (name, got, want)
        return None
    if got != want:
        return "%s 不符：%r != %r" % (name, got, want)
    return None


def judge(expect: dict, readings: dict) -> list[str]:
    fails = []
    for key, want in expect.items():
        why = check(key, readings.get(key), want)
        if why:
            fails.append(why)
    return fails

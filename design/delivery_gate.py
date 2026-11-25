"""
交付门禁：只接受这次任务新写下的文件。

旧文件、空文件、头签名不对的文件都是失败。调用成功但磁盘上还是上一轮的图，不算交付。
"""

from __future__ import annotations

import hashlib
import os


_MAGIC = {
    "pdf": b"%PDF",
    "step": b"ISO-10303-21",
}


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def _fail(check: str, got, want) -> dict:
    return {
        "ok": False,
        "checks": [{"check": check, "got": got, "want": want, "ok": False}],
        "errors": [check],
    }


def accept_new_file(path: str, not_before: float, min_bytes: int = 32, kind: str | None = None) -> dict:
    """not_before 用任务开始时的 time.time()。文件修改时间早于它即拒绝。"""
    if not os.path.isfile(path):
        return _fail("exists", False, True)
    size = os.path.getsize(path)
    mtime = os.path.getmtime(path)
    fresh = mtime + 1e-3 >= not_before
    big = size >= min_bytes
    magic_ok = True
    magic_got = ""
    if kind:
        expected = _MAGIC.get(kind)
        if expected is None:
            raise ValueError("kind 只能是 pdf 或 step")
        with open(path, "rb") as handle:
            magic_got = handle.read(len(expected)).decode("ascii", "replace")
        magic_ok = magic_got.encode("ascii", "replace").startswith(expected)
    checks = [
        {"check": "fresh", "got": round(mtime, 3), "want": not_before, "ok": fresh},
        {"check": "size", "got": size, "want": min_bytes, "ok": big},
    ]
    if kind:
        checks.append({
            "check": "magic",
            "got": magic_got,
            "want": _MAGIC[kind].decode("ascii"),
            "ok": magic_ok,
        })
    errors = [item["check"] for item in checks if not item["ok"]]
    return {"ok": not errors, "path": path, "checks": checks, "errors": errors}


def content_changed(path: str, previous_sha256: str) -> dict:
    """同一路径再次导出时，内容哈希必须变过。"""
    if not os.path.isfile(path):
        return _fail("exists", False, True)
    current = _sha256(path)
    changed = current != previous_sha256
    return {
        "ok": changed,
        "path": path,
        "checks": [{
            "check": "sha256_changed",
            "got": current,
            "want": "不同于 " + previous_sha256,
            "ok": changed,
        }],
        "errors": [] if changed else ["sha256_changed"],
    }

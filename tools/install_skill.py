"""把仓库里的技能安装到本机技能目录（带备份与版本戳）。

为什么需要：`~/.cursor/skills/solidworks-automation`（本机实际加载的那份）
与仓库里的 `skills/solidworks-automation` 曾经**长期分叉**——本机那份 5.1 KB
指向旧的 `user-solidworks` MCP，仓库那份才含 swkit 的 150 条已验证配方。
Agent 读的是本机那份，所以"内核再强也没用"。

本工具做的事：

1. 把 `skills/solidworks-automation/` 复制到每个目标根目录；
2. 目标已存在且内容不同 → 先备份到 `<根>/.swkit-backups/<name>-<时间戳>/`；
3. 写入 `.swkit-skill.json`：仓库版本、registry 计数、安装时间、文件哈希；
4. `--check` 只比对，不写盘；有目标缺失或过期 → 退出码 4。

用法：

    python tools/install_skill.py                 # 装到默认两个位置
    python tools/install_skill.py --check         # 只校验
    python tools/install_skill.py --to D:/x/skills
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from swkit.registry import summary  # noqa: E402

SRC = os.path.join(ROOT, "skills", "solidworks-automation")
NAME = "solidworks-automation"

DEFAULT_TARGETS = [
    os.path.join(os.path.expanduser("~"), ".dsh", "skills"),
    os.path.join(os.path.expanduser("~"), ".cursor", "skills"),
]


def _hash_tree(path: str) -> str:
    h = hashlib.sha256()
    for base, _dirs, files in os.walk(path):
        for f in sorted(files):
            if f == ".swkit-skill.json":
                continue
            full = os.path.join(base, f)
            rel = os.path.relpath(full, path).replace("\\", "/")
            h.update(rel.encode("utf-8"))
            with open(full, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def _stamp() -> dict:
    s = summary()
    return {
        "name": NAME,
        "source": SRC,
        "tree_sha256": _hash_tree(SRC),
        "registry": {k: s[k] for k in ("verified", "unstable", "unverified",
                                       "broken", "implemented")},
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _installed_stamp(dest: str) -> dict | None:
    p = os.path.join(dest, ".swkit-skill.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                               # noqa: BLE001
        return None


def install(root: str, dry: bool) -> tuple[str, str]:
    """返回 (状态, 说明)。状态：ok / created / updated / stale / missing。"""
    dest = os.path.join(root, NAME)
    src_hash = _hash_tree(SRC)
    if not os.path.isdir(dest):
        if dry:
            return "missing", dest
        os.makedirs(root, exist_ok=True)
        shutil.copytree(SRC, dest)
        with open(os.path.join(dest, ".swkit-skill.json"), "w", encoding="utf-8") as fh:
            json.dump(_stamp(), fh, ensure_ascii=False, indent=2)
        return "created", dest

    old = _installed_stamp(dest)
    if old and old.get("tree_sha256") == src_hash:
        return "ok", dest
    if dry:
        return "stale", dest

    backup_root = os.path.join(root, ".swkit-backups")
    os.makedirs(backup_root, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    shutil.move(dest, os.path.join(backup_root, "%s-%s" % (NAME, ts)))
    shutil.copytree(SRC, dest)
    with open(os.path.join(dest, ".swkit-skill.json"), "w", encoding="utf-8") as fh:
        json.dump(_stamp(), fh, ensure_ascii=False, indent=2)
    return "updated", dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写盘")
    ap.add_argument("--to", action="append", default=[], help="额外的目标根目录")
    args = ap.parse_args()

    roots = DEFAULT_TARGETS + [os.path.abspath(p) for p in args.to]
    worst = 0
    for r in roots:
        status, dest = install(r, args.check)
        label = {"ok": "已是最新", "created": "已安装", "updated": "已更新（旧版已备份）",
                 "stale": "过期", "missing": "未安装"}[status]
        print("%-10s %-46s %s" % (status, dest, label))
        if status in ("stale", "missing"):
            worst = 4
    if args.check and worst:
        print("\n跑 `python tools/install_skill.py` 安装/更新。")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())

"""把本技能安装到本机技能目录（名字固定 `ww-autocad-automation`）。

为什么需要：内核（acadkit）会持续更新，而 Agent 读到的是**安装副本**。
装本技能后，`python tools/install_skill.py --check` 能告诉你安装副本是否过期
（比对整棵树的 SHA-256）。

用法：

    python tools/install_skill.py                    # 装到默认两个位置
    python tools/install_skill.py --check            # 只校验
    python tools/install_skill.py --remove-legacy    # 顺带把旧名备份移除
    python tools/install_skill.py --to D:/x/skills
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = "ww-autocad-automation"
LEGACY = "autocad-automation"

DEFAULT_TARGETS = [
    os.path.join(os.path.expanduser("~"), ".dsh", "skills"),
    os.path.join(os.path.expanduser("~"), ".cursor", "skills"),
]

SKIP_IN_COPY = {".git", "__pycache__", ".pytest_cache", ".acadkit-skill.json"}


def _hash_tree(path: str) -> str:
    h = hashlib.sha256()
    for base, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_IN_COPY]
        for f in sorted(files):
            if f in SKIP_IN_COPY:
                continue
            full = os.path.join(base, f)
            rel = os.path.relpath(full, path).replace("\\", "/")
            h.update(rel.encode("utf-8"))
            with open(full, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def _snapshot_counts() -> dict:
    p = os.path.join(ROOT, "capabilities.json")
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh).get("counts", {})


def _stamp() -> dict:
    return {"name": NAME, "source": ROOT, "tree_sha256": _hash_tree(ROOT),
            "verified_caps": _snapshot_counts().get("verified"),
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def _copy(src: str, dst: str) -> None:
    def ignore(_d, names):
        return [n for n in names if n in SKIP_IN_COPY]
    shutil.copytree(src, dst, ignore=ignore)


def _backup(path: str) -> str:
    root = os.path.dirname(path)
    backups = os.path.join(root, ".acadkit-backups")
    os.makedirs(backups, exist_ok=True)
    dst = os.path.join(backups, "%s-%s" % (os.path.basename(path),
                                          time.strftime("%Y%m%d-%H%M%S")))
    shutil.move(path, dst)
    return dst


def install(root: str, dry: bool, remove_legacy: bool) -> tuple[str, str]:
    dest = os.path.join(root, NAME)
    src_hash = _hash_tree(ROOT)
    notes = []

    if not os.path.isdir(dest):
        if dry:
            return "missing", dest
        os.makedirs(root, exist_ok=True)
        _copy(ROOT, dest)
        with open(os.path.join(dest, ".acadkit-skill.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(_stamp(), fh, ensure_ascii=False, indent=2)
        status = "created"
    else:
        old = {}
        p = os.path.join(dest, ".acadkit-skill.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    old = json.load(fh)
            except Exception:                       # noqa: BLE001
                old = {}
        if old.get("tree_sha256") == src_hash:
            status = "ok"
        elif dry:
            return "stale", dest
        else:
            notes.append("旧版已备份到 %s" % _backup(dest))
            _copy(ROOT, dest)
            with open(os.path.join(dest, ".acadkit-skill.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(_stamp(), fh, ensure_ascii=False, indent=2)
            status = "updated"

    legacy = os.path.join(root, LEGACY)
    if remove_legacy and os.path.isdir(legacy):
        if dry:
            notes.append("旧名 %s 待移除" % legacy)
        else:
            notes.append("旧名已备份并移除：%s" % _backup(legacy))
    return status, dest + (("\n" + "\n".join("           " + n for n in notes))
                           if notes else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--remove-legacy", action="store_true")
    ap.add_argument("--to", action="append", default=[])
    args = ap.parse_args()

    roots = DEFAULT_TARGETS + [os.path.abspath(p) for p in args.to]
    worst = 0
    for r in roots:
        status, info = install(r, args.check, args.remove_legacy)
        label = {"ok": "已是最新", "created": "已安装", "updated": "已更新",
                 "stale": "过期", "missing": "未安装"}[status]
        print("%-9s %s  [%s]" % (status, info, label))
        if status in ("stale", "missing"):
            worst = 4
    if args.check and worst:
        print("\n跑 `python tools/install_skill.py` 安装/更新。")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())

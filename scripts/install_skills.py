#!/usr/bin/env python3
"""把 skills/ 装到 agent 的 skills 根，并支持增量更新。

    python scripts/install_skills.py --list
    python scripts/install_skills.py --target "$env:USERPROFILE\\.dsh\\skills"
    python scripts/install_skills.py --dry-run
    python scripts/install_skills.py --update          # 只覆盖 SKILL.md / capabilities.json

设计要点：
* 装完写 `.nsa-install.json` 清单（每个技能的 SKILL.md sha256），
  `--update` **只动清单里登记过的技能**，且只覆盖那两个文件——
  不会把你在目标目录里的本地改动冲掉；
* 默认 `--dry-run` 关，但会打印每个技能的文件数；
* 跳过 `__pycache__` / `.git` / `.pyc`。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
MANIFEST = ".nsa-install.json"
UPDATABLE = ("SKILL.md", "capabilities.json")
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules"}
SKIP_SUFFIX = {".pyc", ".pyo"}


@dataclass
class Plan:
    install: List[str] = field(default_factory=list)
    update: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    files: int = 0


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def discover(skills_root: str = SKILLS) -> Dict[str, str]:
    """{技能名: 目录}；只认含 SKILL.md 的目录。"""
    out: Dict[str, str] = {}
    if not os.path.isdir(skills_root):
        return out
    for name in sorted(os.listdir(skills_root)):
        path = os.path.join(skills_root, name)
        if os.path.isfile(os.path.join(path, "SKILL.md")):
            out[name] = path
    return out


def _walk_files(src: str) -> List[str]:
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1] in SKIP_SUFFIX:
                continue
            out.append(os.path.relpath(os.path.join(dirpath, fn), src))
    return sorted(out)


def load_manifest(target: str) -> Dict[str, object]:
    path = os.path.join(target, MANIFEST)
    if not os.path.isfile(path):
        return {"skills": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError:
        return {"skills": {}}


def make_plan(target: str, skills: Dict[str, str], *, update: bool) -> Plan:
    plan = Plan()
    manifest = load_manifest(target)
    installed = set((manifest.get("skills") or {}).keys())
    for name, src in skills.items():
        if update:
            if name in installed:
                plan.update.append(name)
            else:
                plan.skipped.append(name)
        else:
            plan.install.append(name)
        plan.files += len(_walk_files(src))
    return plan


def install(target: str, skills: Dict[str, str], *, update: bool = False,
            dry_run: bool = False) -> Dict[str, object]:
    plan = make_plan(target, skills, update=update)
    manifest = load_manifest(target)
    entries: Dict[str, object] = dict(manifest.get("skills") or {})
    done: List[Dict[str, object]] = []

    for name in plan.install + plan.update:
        src = skills[name]
        dst = os.path.join(target, name)
        if dry_run:
            done.append({"skill": name, "mode": "update" if update else "install",
                         "files": len(_walk_files(src)), "dry_run": True})
            continue
        os.makedirs(dst, exist_ok=True)
        if update:
            copied = []
            for fn in UPDATABLE:
                s = os.path.join(src, fn)
                if os.path.isfile(s):
                    shutil.copy2(s, os.path.join(dst, fn))
                    copied.append(fn)
        else:
            copied = []
            for rel in _walk_files(src):
                s = os.path.join(src, rel)
                t = os.path.join(dst, rel)
                os.makedirs(os.path.dirname(t) or dst, exist_ok=True)
                shutil.copy2(s, t)
                copied.append(rel)
        skill_md = os.path.join(dst, "SKILL.md")
        entries[name] = {"sha256": _sha256(skill_md) if os.path.isfile(skill_md) else "",
                         "files": len(copied),
                         "mode": "update" if update else "install",
                         "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        done.append({"skill": name, "mode": entries[name]["mode"],
                     "files": len(copied), "dry_run": False})

    if not dry_run:
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, MANIFEST), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "source": SKILLS, "skills": entries},
                      fh, ensure_ascii=False, indent=2)
    return {"target": target, "dry_run": dry_run,
            "done": done, "skipped": plan.skipped,
            "total_files": plan.files}


def default_target() -> str:
    home = os.path.expanduser("~")
    for cand in (os.path.join(home, ".dsh", "skills"),
                 os.path.join(home, ".claude", "skills")):
        if os.path.isdir(os.path.dirname(cand)):
            return cand
    return os.path.join(home, ".dsh", "skills")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="安装/更新 nsa-toolchain 技能")
    ap.add_argument("--target", default=default_target())
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    skills = discover()
    if not skills:
        print("没找到任何技能（skills/*/SKILL.md）")
        return 2

    if args.list:
        for name, path in skills.items():
            n = len(_walk_files(path))
            print("%-28s %3d 个文件  %s" % (name, n, path))
        return 0

    out = install(args.target, skills, update=args.update, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    tag = "（演练，未写盘）" if args.dry_run else ""
    print("目标：%s%s" % (args.target, tag))
    for item in out["done"]:
        print("  %-28s %s，%d 个文件" % (item["skill"], item["mode"], item["files"]))
    for name in out["skipped"]:
        print("  %-28s 跳过（目标里没装过，--update 不新增）" % name)
    print("合计 %d 个文件" % out["total_files"])
    if not args.dry_run:
        print("清单：%s" % os.path.join(args.target, MANIFEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())

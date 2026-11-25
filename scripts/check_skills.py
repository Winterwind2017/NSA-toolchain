#!/usr/bin/env python3
"""全局一致性检查：路由 skill + 各域 skill + 各 kernel 注册表。

    python scripts/check_skills.py            # 报告（有问题退出码 = 失败项数）
    python scripts/check_skills.py --check    # 只当门用（同上，语义更明确）
    python scripts/check_skills.py --json

为什么需要：每个 skill 自带 `tools/check_skill.py`，只保证**自己**和
`capabilities.json` 快照不矛盾；但它保证不了两件事：

1. 快照**和内核注册表**是否还一致（内核改了名/删了能力，skill 就成了"教错"）；
2. 路由 skill 列出的域是否都存在（漏一个域，agent 就永远走不到那条路）。

所以这里做编排 + 跨仓核对，并明确报告**核对不到的范围**（有些 kernel 没有注册表，
不能假装通过）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")

# skill 目录名 → kernel 目录名
SKILL_TO_KERNEL = {
    "ww-autocad-automation": "acad",
    "ww-nx-automation": "nx",
    "ww-gxworks-automation": "gx",
    "ww-solidworks-automation": "sw",
    "ww-autoshop-automation": "autoshop",
    "ww-codesys-automation": "codesys",
}

ROUTER = "nsa-toolchain"
STRICT = False

ALLOW_BEGIN = "<!-- allow:non-verified:BEGIN -->"
ALLOW_END = "<!-- allow:non-verified:END -->"

NOT_ID_SUFFIX = {
    "py", "md", "json", "yaml", "yml", "sh", "ps1", "dll", "exe", "tlb", "mdb",
    "accdb", "lin", "pc3", "lsp", "ttf", "shx", "dwg", "dxf", "pdf", "txt",
    "log", "ini", "toml", "cfg", "html", "css", "js", "ts", "csv", "xlsx",
}

ID_RE = re.compile(r"\b([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\b")

# 体积预算（KB）。技能是给模型读的，太长会挤掉判据。
WARN_KB, FAIL_KB = 8.0, 24.0
ROUTER_MAX_KB = 6.0


class RegistryError(RuntimeError):
    """注册表本身坏了（比「对不上」更严重）。"""


@dataclass
class Finding:
    level: str          # FAIL / WARN / INFO
    skill: str
    code: str
    message: str


@dataclass
class Report:
    findings: List[Finding] = field(default_factory=list)
    checked: Dict[str, object] = field(default_factory=dict)

    def add(self, level: str, skill: str, code: str, message: str) -> None:
        self.findings.append(Finding(level, skill, code, message))

    @property
    def failures(self) -> List[Finding]:
        return [f for f in self.findings if f.level == "FAIL"]

    def to_dict(self) -> dict:
        return {"findings": [f.__dict__ for f in self.findings],
                "checked": self.checked,
                "failures": len(self.failures)}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _kb(path: str) -> float:
    return os.path.getsize(path) / 1024.0


def strip_allow_blocks(text: str) -> str:
    out, inside = [], False
    for line in text.splitlines():
        if ALLOW_BEGIN in line:
            inside = True
            continue
        if ALLOW_END in line:
            inside = False
            continue
        if not inside:
            out.append(line)
    return "\n".join(out)


def ids_in(text: str) -> Set[str]:
    found = set()
    for m in ID_RE.finditer(text):
        suffix = m.group(2)
        if suffix in NOT_ID_SUFFIX:
            continue
        found.add(m.group(0))
    return found


# ── 注册表 ──────────────────────────────────────────────────────────
def load_registry(kernel: str) -> Optional[Dict[str, str]]:
    """返回 {id: status}；没有 registry.yaml 的内核返回 None（明确"无法核对"）。"""
    path = os.path.join(ROOT, "kernels", kernel, "docs", "registry.yaml")
    if not os.path.isfile(path):
        return None
    try:
        import yaml
    except ImportError:
        return None
    try:
        data = yaml.safe_load(_read(path)) or {}
    except Exception as exc:                                  # noqa: BLE001
        raise RegistryError("%s 不是合法 YAML：%s" % (os.path.relpath(path, ROOT), exc))
    out: Dict[str, str] = {}
    for cap in data.get("capabilities") or []:
        cid = cap.get("id")
        if cid:
            out[str(cid)] = str(cap.get("status") or "unknown")
    return out


def snapshot_negatives(skill_dir: str) -> Set[str]:
    """快照里标成负例的 id（这些本来就不该在 registry 的 capabilities 里）。"""
    path = os.path.join(skill_dir, "capabilities.json")
    if not os.path.isfile(path):
        return set()
    try:
        data = json.loads(_read(path))
    except json.JSONDecodeError:
        return set()
    out: Set[str] = set()
    levels = data.get("levels")
    if isinstance(levels, dict):
        for cid, level in levels.items():
            if str(level) in ("负例", "negative", "neg"):
                out.add(str(cid))
    for key in ("negatives", "non_verified"):
        block = data.get(key)
        if isinstance(block, list):
            for item in block:
                if isinstance(item, str):
                    out.add(item)
                elif isinstance(item, dict) and item.get("id"):
                    out.add(str(item["id"]))
    return out


def snapshot_ids(skill_dir: str) -> Optional[Set[str]]:
    """从 capabilities.json 里抽能力 id（各内核 schema 不同，按已知键依次尝试）。"""
    path = os.path.join(skill_dir, "capabilities.json")
    if not os.path.isfile(path):
        return None
    try:
        data = json.loads(_read(path))
    except json.JSONDecodeError:
        return None
    ids: Set[str] = set()

    levels = data.get("levels")
    if isinstance(levels, dict):
        ids |= set(map(str, levels.keys()))

    for key in ("verified", "non_verified", "pending"):
        block = data.get(key)
        if isinstance(block, list):
            for item in block:
                if isinstance(item, str):
                    ids.add(item)
                elif isinstance(item, dict):
                    for k in ("id", "name"):
                        if item.get(k):
                            ids.add(str(item[k]))
        elif isinstance(block, dict):
            ids |= set(map(str, block.keys()))

    fams = data.get("families")
    if isinstance(fams, dict):
        for val in fams.values():
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        ids.add(item)
                    elif isinstance(item, dict) and item.get("id"):
                        ids.add(str(item["id"]))
    return {i for i in ids if ID_RE.fullmatch(i)}


# ── 检查 ────────────────────────────────────────────────────────────
def check_frontmatter(rep: Report, name: str, text: str, dirname: str) -> None:
    if not text.startswith("---"):
        rep.add("FAIL", name, "frontmatter", "缺少 YAML frontmatter（--- 开头）")
        return
    end = text.find("\n---", 3)
    if end < 0:
        rep.add("FAIL", name, "frontmatter", "frontmatter 没有闭合的 ---")
        return
    block = text[3:end]
    m = re.search(r"(?m)^name:\s*(\S+)", block)
    if not m:
        rep.add("FAIL", name, "frontmatter", "缺 name 字段")
    elif m.group(1) != dirname:
        rep.add("FAIL", name, "frontmatter",
                "name=%r 必须与目录名 %r 一致" % (m.group(1), dirname))
    if not re.search(r"(?m)^description:\s*\S", block):
        rep.add("FAIL", name, "frontmatter", "缺 description（模型靠它触发）")


def check_size(rep: Report, name: str, path: str, limit_fail: float) -> None:
    kb = _kb(path)
    if kb > limit_fail:
        rep.add("FAIL", name, "size", "SKILL.md %.1f KB > %.0f KB" % (kb, limit_fail))
    elif kb > WARN_KB:
        rep.add("WARN", name, "size", "SKILL.md %.1f KB 偏长（>%.0f KB）" % (kb, WARN_KB))


def run_own_checker(rep: Report, name: str, skill_dir: str) -> Optional[str]:
    """跑 skill 自带的 tools/check_skill.py --check。"""
    script = os.path.join(skill_dir, "tools", "check_skill.py")
    if not os.path.isfile(script):
        rep.add("INFO", name, "own_checker", "没有 tools/check_skill.py，跳过")
        return None
    res = subprocess.run([sys.executable, script, "--check"], cwd=skill_dir,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    tail = (res.stdout or "").strip().splitlines()
    if res.returncode != 0:
        detail = " | ".join(tail[-4:]) if tail else (res.stderr or "").strip()[:300]
        rep.add("FAIL", name, "own_checker", "自带检查未通过：%s" % detail)
    return res.stdout


def check_against_registry(rep: Report, name: str, skill_dir: str,
                           kernel: str) -> None:
    try:
        reg = load_registry(kernel)
    except RegistryError as exc:
        rep.add("FAIL", name, "registry_broken", str(exc))
        return
    snap = snapshot_ids(skill_dir)
    if snap is None:
        rep.add("WARN", name, "snapshot", "没有 capabilities.json，无法核对")
        return
    if reg is None:
        rep.add("INFO", name, "registry",
                "kernels/%s 没有 docs/registry.yaml → **无法核对**（快照 %d 条）"
                % (kernel, len(snap)))
        rep.checked["%s.unverified_scope" % name] = len(snap)
        return

    negatives = snapshot_negatives(skill_dir)
    missing = sorted(snap - set(reg) - negatives)
    if missing:
        level = "FAIL" if STRICT else "WARN"
        rep.add(level, name, "drift",
                "快照里 %d 条在 kernels/%s 注册表里不存在（可能是内核版本不一致）：%s"
                % (len(missing), kernel, ", ".join(missing[:8])))
    if negatives:
        rep.add("INFO", name, "negatives",
                "%d 条负例（故意失败，不参与漂移判定）：%s"
                % (len(negatives), ", ".join(sorted(negatives))))

    verified = {k for k, v in reg.items() if v == "verified"}
    stale = sorted(verified - snap)
    if stale:
        rep.add("WARN", name, "stale",
                "注册表里 %d 条 verified 不在快照（跑 tools/sync_capabilities.py）：%s"
                % (len(stale), ", ".join(stale[:8])))

    skill_md = os.path.join(skill_dir, "SKILL.md")
    if os.path.isfile(skill_md):
        outside = ids_in(strip_allow_blocks(_read(skill_md)))
        dead = {k for k, v in reg.items() if v == "dead"}
        bad = sorted(outside & dead)
        if bad:
            rep.add("FAIL", name, "dead_recommended",
                    "把 dead 能力写在允许区块外：%s" % ", ".join(bad))
    rep.checked["%s.registry" % name] = {"kernel": kernel, "registry": len(reg),
                                         "snapshot": len(snap)}


def check_router(rep: Report, present: List[str]) -> None:
    path = os.path.join(SKILLS, ROUTER, "SKILL.md")
    if not os.path.isfile(path):
        rep.add("FAIL", ROUTER, "missing", "缺路由 skill：skills/%s/SKILL.md" % ROUTER)
        return
    text = _read(path)
    check_frontmatter(rep, ROUTER, text, ROUTER)
    kb = _kb(path)
    if kb > ROUTER_MAX_KB:
        rep.add("FAIL", "nsa-toolchain" if False else ROUTER, "size",
                "路由 skill %.1f KB > %.0f KB（它要能被随手加载）" % (kb, ROUTER_MAX_KB))

    listed = set(re.findall(r"`(ww-[a-z0-9-]+)`", text))
    for name in sorted(listed - set(present)):
        rep.add("FAIL", ROUTER, "router_ghost",
                "路由里列了不存在的 skill：`%s`" % name)
    for name in sorted(set(present) - listed):
        rep.add("FAIL", ROUTER, "router_missing",
                "存在 skill `%s` 但路由没列（agent 走不到）" % name)

    for kw in ("判据", "verified"):
        if kw not in text:
            rep.add("WARN", ROUTER, "router_discipline",
                    "路由里没提 %r（两个跨域铁律之一）" % kw)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="全局一致性检查（skills ↔ kernels）")
    ap.add_argument("--check", action="store_true", help="当门用（有失败即非零）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="把跨仓漂移也当成失败（发布门用；日常开发只告警）")
    args = ap.parse_args(argv)
    global STRICT
    STRICT = args.strict

    rep = Report()
    present = sorted(d for d in os.listdir(SKILLS)
                     if os.path.isdir(os.path.join(SKILLS, d)) and d != ROUTER)

    for name in present:
        skill_dir = os.path.join(SKILLS, name)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_md):
            rep.add("FAIL", name, "missing", "缺 SKILL.md")
            continue
        text = _read(skill_md)
        check_frontmatter(rep, name, text, name)
        check_size(rep, name, skill_md, FAIL_KB)
        run_own_checker(rep, name, skill_dir)
        kernel = SKILL_TO_KERNEL.get(name)
        if kernel is None:
            rep.add("INFO", name, "mapping", "未配置 kernel 映射，跳过注册表核对")
        else:
            check_against_registry(rep, name, skill_dir, kernel)

    check_router(rep, present)

    if args.json:
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    else:
        order = {"FAIL": 0, "WARN": 1, "INFO": 2}
        for f in sorted(rep.findings, key=lambda x: (order[x.level], x.skill, x.code)):
            print("[%-4s] %-26s %-18s %s" % (f.level, f.skill, f.code, f.message))
        fails = len(rep.failures)
        print("\n技能 %d 个 · 发现 %d 条（FAIL %d / WARN %d / INFO %d）"
              % (len(present), len(rep.findings), fails,
                 sum(1 for f in rep.findings if f.level == "WARN"),
                 sum(1 for f in rep.findings if f.level == "INFO")))
        for name, info in sorted(rep.checked.items()):
            if isinstance(info, dict) and "registry" in info:
                print("  核对 %s：注册表 %d 条 / 快照 %d 条（kernel=%s）"
                      % (name, info["registry"], info["snapshot"], info["kernel"]))
    return len(rep.failures)


if __name__ == "__main__":
    sys.exit(main())

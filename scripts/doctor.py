#!/usr/bin/env python3
"""统一环境诊断：一条命令说清"哪里坏了、下一步做什么"。

    python scripts/doctor.py
    python scripts/doctor.py --json
    python scripts/doctor.py --only acad,sw

为什么需要：6 个内核各有自己的 `status`，但口径不统一——
排查"为什么跑不动"时要分别记 6 条命令。这里把它们统一成一张表，
并且**只报能核对的事实**：包能否 import、引擎 exe 在不在、进程在不在、
skill 有没有装。查不到的写"未检查"，不猜。

退出码 = FAIL 条数（可直接当门用；全绿退出 0）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)


@dataclass
class KitSpec:
    name: str                 # 内核目录名，如 acad
    pkg: str                  # 可 import 的包名，如 acadkit
    process: str = ""         # 引擎进程名，如 acad.exe
    engine_paths: tuple = ()  # 常见安装位置（任一存在即可）
    skill: str = ""           # 对应技能目录名


KITS: List[KitSpec] = [
    KitSpec("acad", "acadkit", "acad.exe",
            (r"D:\Program Files\Autodesk\AutoCAD 2025\acad.exe",
             r"C:\Program Files\Autodesk\AutoCAD 2025\acad.exe"),
            "ww-autocad-automation"),
    KitSpec("sw", "swkit", "SLDWORKS.exe",
            (r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",),
            "ww-solidworks-automation"),
    KitSpec("nx", "nxkit", "ugraf.exe", (), "ww-nx-automation"),
    KitSpec("gx", "gxkit", "GDK.exe", (), "ww-gxworks-automation"),
    KitSpec("codesys", "codesyskit", "CODESYS.exe", (),
            "ww-codesys-automation"),
    KitSpec("autoshop", "autoshopkit", "AutoShop.exe", (),
            "ww-autoshop-automation"),
]

OPTIONAL_PY = [("cadquery", "离线 B-rep / STEP 出口"),
               ("yaml", "registry 与文档生成"),
               ("pytest", "离线测试"),
               ("gmsh", "FEA：体积网格"),
               ("sfepy", "FEA：Python 有限元框架"),
               ("skfem", "FEA：轻量装配库")]

# ccx 求解器候选（静态版自带运行时，动态版缺 MinGW DLL）
CCX_CANDIDATES = (
    os.environ.get("NSA_CCX", ""),
    "ccx_i4_static.exe",
    "ccx_i8_static.exe",
    "ccx",
)


@dataclass
class Check:
    level: str           # OK / WARN / FAIL / SKIP
    area: str
    message: str
    next_step: str = ""

    def to_dict(self) -> dict:
        return {"level": self.level, "area": self.area,
                "message": self.message, "next_step": self.next_step}


@dataclass
class Report:
    checks: List[Check] = field(default_factory=list)

    def add(self, level: str, area: str, message: str, next_step: str = "") -> None:
        self.checks.append(Check(level, area, message, next_step))

    @property
    def failures(self) -> List[Check]:
        return [c for c in self.checks if c.level == "FAIL"]

    def to_dict(self) -> dict:
        counts: Dict[str, int] = {}
        for c in self.checks:
            counts[c.level] = counts.get(c.level, 0) + 1
        return {"ok": not self.failures, "counts": counts,
                "checks": [c.to_dict() for c in self.checks]}

    def to_text(self) -> str:
        width = max((len(c.area) for c in self.checks), default=8)
        lines = []
        for c in self.checks:
            lines.append("[%-4s] %-*s %s" % (c.level, width, c.area, c.message))
            if c.next_step and c.level in ("FAIL", "WARN"):
                lines.append("       → %s" % c.next_step)
        counts = self.to_dict()["counts"]
        lines.append("")
        lines.append("结论：%s（%s）"
                     % ("可开工" if not self.failures else "有 %d 项阻塞" % len(self.failures),
                        ", ".join("%s=%d" % kv for kv in sorted(counts.items()))))
        return "\n".join(lines)


# ── 探针（可注入，便于测试）──
class Probes:
    def importable(self, pkg: str, path: str) -> bool:
        sys.path.insert(0, path)
        try:
            import importlib.util as u
            return u.find_spec(pkg) is not None
        except Exception:                                # noqa: BLE001
            return False
        finally:
            try:
                sys.path.remove(path)
            except ValueError:
                pass

    def any_path(self, paths) -> Optional[str]:
        for p in paths:
            if p and os.path.exists(p):
                return p
        return None

    def process_running(self, name: str) -> bool:
        if not name:
            return False
        try:
            res = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % name],
                                 capture_output=True, text=True, timeout=6)
            return name.lower() in (res.stdout or "").lower()
        except Exception:                                # noqa: BLE001
            return False

    def exists(self, path: str) -> bool:
        return os.path.exists(path)


def skills_state(target: str, skills_map: Optional[dict] = None) -> Optional[dict]:
    """读目标目录的安装清单，返回 install_skills.status 的结果。

    skills_map 可注入（测试用假技能表）；默认用仓库里的 skills/。
    任何异常都返回 None（doctor 不该因为技能状态读不出来而崩）。
    """
    try:
        import install_skills as IS                    # noqa: WPS433
        return IS.status(target, skills_map if skills_map is not None else IS.discover())
    except Exception:                                   # noqa: BLE001
        return None


def diagnose(specs: List[KitSpec], probes: Optional[object] = None,
             root: str = ROOT, skills_target: Optional[str] = None,
             skills_map: Optional[dict] = None) -> Report:
    pr = probes or Probes()
    rep = Report()

    # 全局
    rep.add("OK", "python", "%d.%d.%d" % sys.version_info[:3], "")
    for pkg, why in OPTIONAL_PY:
        ok = pr.importable(pkg, os.path.join(root, "kernels", "acad", "src"))
        rep.add("OK" if ok else "WARN", "包 %s" % pkg,
                ("可用（%s）" % why) if ok else "缺失（%s）" % why,
                "" if ok else "pip install %s" % pkg)

    # FEA 链路：网格器 / 框架 / 求解器三环，缺哪环说哪环
    ccx = pr.any_path(CCX_CANDIDATES)
    rep.add("OK" if ccx else "WARN", "FEA 求解器 ccx",
            ccx or "未找到（静态版 ccx_i4_static.exe）",
            "" if ccx else "下载 calculix_2.24_4win.zip 解包，或设 NSA_CCX 指向 ccx_i4_static.exe")

    skills_root = os.path.join(root, "skills")
    rep.add("OK" if pr.exists(skills_root) else "FAIL", "skills/",
            "存在" if pr.exists(skills_root) else "缺 skills/ 目录",
            "" if pr.exists(skills_root) else "从仓库根运行本脚本")

    # 技能安装状态（目标默认 ~/.dsh/skills）
    try:
        import install_skills as IS
        target = skills_target or IS.default_target()
    except Exception:                                   # noqa: BLE001
        target = skills_target or ""
    st = skills_state(target, skills_map) if target else None
    if st is None:
        rep.add("SKIP", "技能安装", "读不出技能清单（目标：%s）" % (target or "未指定"), "")
    elif not st["has_manifest"]:
        # 有目录但没清单：老版本装的，或手工拷进去的 —— 无法证明版本，要重装
        present = [r["skill"] for r in st["rows"] if r["state"] != "missing"]
        if present:
            rep.add("WARN", "技能安装",
                    "目标有 %d 个技能但没有安装清单（无法证明版本）：%s"
                    % (len(present), ", ".join(present[:4])),
                    "python scripts/nsa.py skills install（重装并写清单）")
        else:
            rep.add("SKIP", "技能安装", "目标还没装过技能：%s" % target,
                    "python scripts/nsa.py skills install")
    else:
        c = st["counts"]
        bad = [r["skill"] + ":" + r["state"] for r in st["rows"] if r["state"] != "fresh"]
        if st["fresh"]:
            rep.add("OK", "技能安装",
                    "全部最新（%d 个，目标 %s）" % (c["fresh"], target), "")
        else:
            rep.add("WARN", "技能安装",
                    "%d 个需处理（stale=%d modified=%d missing=%d）：%s"
                    % (len(bad), c["stale"], c["modified"], c["missing"],
                       ", ".join(bad[:4])),
                    "python scripts/nsa.py skills update（或 install 重装）")

    # cad-viewer（交互看件）：只看装没装 + node 在不在，不启动服务
    try:
        import viewer as VW
        try:
            viewer_dir = VW.viewer_root()        # 注意：不能叫 root，会盖掉仓库根
            node_ok = shutil.which("node") is not None
            rep.add("OK" if node_ok else "WARN", "cad-viewer",
                    "%s（node %s）" % (viewer_dir, "可用" if node_ok else "缺失"),
                    "" if node_ok else "装 Node.js 18+ 后可用；或设 NSA_CAD_VIEWER 指向 skill 目录")
        except FileNotFoundError as exc:
            rep.add("SKIP", "cad-viewer", str(exc),
                    "装 cad-viewer skill，或设 NSA_CAD_VIEWER")
    except Exception as exc:                            # noqa: BLE001
        rep.add("SKIP", "cad-viewer", "封装读不出来：%s" % exc, "")

    # 每个内核
    for spec in specs:
        src = os.path.join(root, "kernels", spec.name, "src")
        if not pr.exists(src):
            rep.add("SKIP", spec.name, "没有 kernels/%s/src" % spec.name, "")
            continue

        pkg_ok = pr.importable(spec.pkg, src)
        rep.add("OK" if pkg_ok else "FAIL", "%s 包" % spec.name,
                "%s 可 import" % spec.pkg if pkg_ok else "%s 不可 import" % spec.pkg,
                "" if pkg_ok else "pip install -e kernels/%s 或设 PYTHONPATH" % spec.name)

        engine = pr.any_path(spec.engine_paths)
        if not spec.engine_paths:
            rep.add("SKIP", "%s 引擎" % spec.name, "未登记安装路径（无法核对）", "")
        elif engine:
            rep.add("OK", "%s 引擎" % spec.name, engine, "")
        else:
            rep.add("FAIL", "%s 引擎" % spec.name, "登记路径都不存在",
                    "确认软件已装；或更新 scripts/doctor.py 的 KITS 路径")

        if spec.process:
            running = pr.process_running(spec.process)
            rep.add("OK" if running else "WARN", "%s 进程" % spec.name,
                    "%s %s" % (spec.process, "在运行" if running else "未运行"),
                    "" if running else "真机操作前需要先启动引擎")

        if spec.skill:
            sp = os.path.join(skills_root, spec.skill, "SKILL.md")
            ok = pr.exists(sp)
            rep.add("OK" if ok else "WARN", "%s 技能" % spec.name,
                    spec.skill if ok else "缺 skills/%s" % spec.skill,
                    "" if ok else "跑 scripts/install_skills.py 或补回目录")

    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="统一环境诊断")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", default="", help="逗号分隔，如 acad,sw")
    ap.add_argument("--skills-target", default="",
                    help="技能安装目标目录（默认自动探测 ~/.dsh/skills）")
    args = ap.parse_args(argv)

    specs = KITS
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        specs = [k for k in KITS if k.name in wanted]
        if not specs:
            print("没有匹配的内核：%s（可选：%s）"
                  % (args.only, ", ".join(k.name for k in KITS)))
            return 2

    rep = diagnose(specs, skills_target=args.skills_target or None)
    if args.json:
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(rep.to_text())
    return len(rep.failures)


if __name__ == "__main__":
    sys.exit(main())

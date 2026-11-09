#!/usr/bin/env python3
"""doctor.py —— 换机器自检：远端协议 / SSH key / comtypes / SolidWorks

只读检查，不改任何配置。任何机器 clone 下来都能跑：

    python scripts/doctor.py
    python scripts/doctor.py --json

为什么需要它：本仓库远端用 **SSH**。如果换机器后仍是 HTTPS 远端、又没有配置
凭据助手，`git push` 会**无输出挂死**（git-credential-manager 在等不可见的
凭据弹窗）——实测在本项目上挂过 11 分钟。这个脚本会提前把这件事喊出来。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS, WARN, SKIP, FAIL = "PASS", "WARN", "SKIP", "FAIL"


def _run(cmd, timeout=10, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=cwd or ROOT, stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, "command not found: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "timeout after %ss" % timeout


def check_python():
    v = sys.version_info
    ok = v >= (3, 10)
    return (PASS if ok else FAIL,
            "Python %d.%d.%d" % (v[0], v[1], v[2]),
            "" if ok else "需要 >= 3.10")


def check_remote():
    rc, out = _run(["git", "remote", "get-url", "origin"])
    url = out.strip()
    if rc != 0 or not url:
        return FAIL, "没有 origin 远端", "先 git remote add origin <url>"
    if url.startswith("git@") or url.startswith("ssh://"):
        return PASS, "远端 = %s（SSH）" % url, ""
    fix = ("git remote set-url origin git@github.com:<owner>/<repo>.git"
           "   ← 需要先配好 GitHub SSH key")
    return WARN, "远端 = %s（HTTPS）" % url, (
        "HTTPS 远端 + 无凭据助手时，git push 会卡在 git-credential-manager 无输出挂死。\n"
        "      修法：%s\n      或临时用：git -c credential.helper=\"!gh auth git-credential\" push" % fix)


def check_ssh():
    if not shutil.which("ssh"):
        return SKIP, "没有 ssh 客户端", "装 OpenSSH 后重试"
    rc, out = _run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=8", "-T", "git@github.com"], timeout=15)
    text = out.strip()
    if "successfully authenticated" in text:
        return PASS, text.splitlines()[0][:100], ""
    if "Permission denied" in text:
        return WARN, "SSH 能连上 GitHub，但**没有可用 key**", (
            "生成并登记 key：\n"
            "      ssh-keygen -t ed25519 -C \"you@machine\"\n"
            "      然后把 ~/.ssh/id_ed25519.pub 贴到 GitHub → Settings → SSH keys\n"
            "      ssh -T git@github.com   # 应看到 Hi <user>!")
    return SKIP, "SSH 探测结果：%s" % (text.splitlines()[0][:100] if text else "（无输出）"), ""


def check_comtypes():
    try:
        import comtypes  # noqa: F401
        return PASS, "comtypes 可导入", ""
    except ModuleNotFoundError:
        pass
    cands = [os.environ.get("SWKIT_VENDOR") or "",
             os.path.join(os.path.expanduser("~"), ".swkit", "vendor"),
             os.path.join(ROOT, "vendor")]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "comtypes")):
            return PASS, "comtypes 在 %s（会由 comtypes_bundle 自动加 sys.path）" % c, ""
    return WARN, "comtypes 不在 sys.path，也没找到 vendor 目录", (
        "comtypes 是必需依赖：pip install comtypes\n"
        "      或把现成的 comtypes 放到 ~/.swkit/vendor（本仓库会自动找）")


def check_solidworks():
    if sys.platform != "win32":
        return SKIP, "非 Windows，跳过 SolidWorks 探测", ""
    try:
        import win32com.client as w  # noqa: F401
    except Exception:
        return WARN, "没有 pywin32", "pip install pywin32"
    try:
        app = w.Dispatch("SldWorks.Application")
        rev = app.RevisionNumber
        n = app.GetDocumentCount
        return PASS, "SolidWorks %s，已打开 %s 个文档" % (rev, n), ""
    except Exception as exc:
        return WARN, "连不上 SolidWorks（%s）" % str(exc)[:70], (
            "确认 SolidWorks 已启动；首次用 COM 需要它至少运行过一次")


CHECKS = [
    ("python", check_python),
    ("remote", check_remote),
    ("ssh", check_ssh),
    ("comtypes", check_comtypes),
    ("solidworks", check_solidworks),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-solidworks", action="store_true")
    args = ap.parse_args()

    rows = []
    for name, fn in CHECKS:
        if args.no_solidworks and name == "solidworks":
            continue
        try:
            status, detail, hint = fn()
        except Exception as exc:                    # noqa: BLE001
            status, detail, hint = FAIL, "%s: %s" % (type(exc).__name__, exc), ""
        rows.append({"check": name, "status": status, "detail": detail, "hint": hint})

    if args.json:
        print(json.dumps({"repo": ROOT, "checks": rows}, ensure_ascii=False, indent=2))
    else:
        print("swkit doctor —— %s\n" % ROOT)
        for r in rows:
            print("[%-4s] %-11s %s" % (r["status"], r["check"], r["detail"]))
            if r["hint"]:
                print("       → %s" % r["hint"])
        bad = [r for r in rows if r["status"] == FAIL]
        warn = [r for r in rows if r["status"] == WARN]
        print("\n%d PASS / %d WARN / %d FAIL" % (
            sum(1 for r in rows if r["status"] == PASS), len(warn), len(bad)))
        if warn:
            print("有 WARN 时 git push / 真机套件可能失败，按上面的 → 提示处理。")

    return 0 if not [r for r in rows if r["status"] == FAIL] else 4


if __name__ == "__main__":
    raise SystemExit(main())

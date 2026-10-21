#!/usr/bin/env python3
"""doctor.py —— 换机器自检：远端协议 / SSH / pywin32 / AutoCAD / 配置。

只读检查，不改任何配置：

    python scripts/doctor.py
    python scripts/doctor.py --json

为什么需要它：本仓库远端必须是 **SSH**。如果换机器后仍是 HTTPS 远端、又没有
配置凭据助手，`git push` 会**无输出挂死**（git-credential-manager 在等一个看不见
的凭据弹窗）。这个脚本会提前喊出来。
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
    return (PASS if ok else FAIL, "Python %d.%d.%d" % (v[0], v[1], v[2]),
            "" if ok else "需要 >= 3.10")


def check_remote():
    rc, out = _run(["git", "remote", "get-url", "origin"])
    url = out.strip()
    if rc != 0 or not url:
        return FAIL, "没有 origin 远端", "先 git remote add origin <url>"
    if url.startswith("git@") or url.startswith("ssh://"):
        return PASS, "远端 = %s（SSH）" % url, ""
    return WARN, "远端 = %s（HTTPS）" % url, (
        "HTTPS 远端 + 无凭据助手时，git push 会卡在 git-credential-manager。\n"
        "      修法：git remote set-url origin "
        "git@github.com:Winterwind2017/autocad-agent-kit.git")


def check_ssh():
    if not shutil.which("ssh"):
        return SKIP, "没有 ssh 客户端", "装 OpenSSH 后重试"
    rc, out = _run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=8", "-T", "git@github.com"], timeout=15)
    text = out.strip()
    if "successfully authenticated" in text:
        return PASS, text.splitlines()[0][:100], ""
    if "Permission denied" in text:
        return WARN, "SSH 能连上 GitHub，但没有可用 key", (
            "ssh-keygen -t ed25519 -C \"you@machine\"，把公钥贴到 GitHub"
            " → Settings → SSH keys")
    return SKIP, "SSH 探测：%s" % (text.splitlines()[0][:100] if text else "（无输出）"), ""


def check_pywin32():
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
        return PASS, "pywin32 可导入", ""
    except Exception as exc:                        # noqa: BLE001
        return FAIL, "pywin32 不可用：%s" % exc, "pip install pywin32"


def check_autocad():
    try:
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from acadkit.core import launch
        exe = launch.find_acad_exe()
    except Exception as exc:                        # noqa: BLE001
        return FAIL, "找不到 acad.exe：%s" % exc, "需要 AutoCAD 完整版（非 LT）"
    return (PASS if exe else FAIL, "acad.exe = %s" % (exe or "未找到"),
            "" if exe else "确认已安装 AutoCAD 2025（完整版）")


def check_profile():
    """AutoCAD 是否在跑、以及跑的是哪个配置（只附加，不启动）。"""
    try:
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from acadkit.core import com, env, launch
    except Exception as exc:                        # noqa: BLE001
        return FAIL, "acadkit 不可导入：%s" % exc, "pip install -e ."
    app = com.attach_or_none()
    if app is None:
        return SKIP, "AutoCAD 未运行（只读检查不会启动它）", \
            "跑真机套件时会自动启动"
    prof = launch.read_profile(app)
    ok = prof is not None and prof.strip() == env.REQUIRED_PROFILE
    return (PASS if ok else WARN, "CPROFILE = %r" % (prof,),
            "" if ok else "必须用 `acad.exe /p \"%s\"` 启动" % env.REQUIRED_PROFILE)


CHECKS = [("python", check_python), ("remote", check_remote),
          ("ssh", check_ssh), ("pywin32", check_pywin32),
          ("autocad", check_autocad), ("profile", check_profile)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="acadkit 换机器自检（只读）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = []
    for name, fn in CHECKS:
        try:
            status, detail, fix = fn()
        except Exception as exc:                    # noqa: BLE001
            status, detail, fix = FAIL, "%s: %s" % (type(exc).__name__, exc), ""
        rows.append({"check": name, "status": status, "detail": detail,
                     "fix": fix})
    if args.json:
        print(json.dumps({"ok": all(r["status"] in (PASS, SKIP) for r in rows),
                          "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print("acadkit doctor —— 换机器自检（只读）\n")
        for r in rows:
            print("%-6s %-8s %s" % (r["status"], r["check"], r["detail"]))
            if r["fix"]:
                print("           修法：%s" % r["fix"])
        bad = [r for r in rows if r["status"] == FAIL]
        print("\n结论：%s" % ("全部通过" if not bad else "%d 项失败" % len(bad)))
    return 0 if all(r["status"] != FAIL for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())

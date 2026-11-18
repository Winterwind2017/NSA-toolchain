#!/usr/bin/env python3
"""构建 acadkit 的 .NET 插件骨架（`dotnet/`）。

    python dotnet/build.py                 # Release 构建，打印 DLL 路径
    python dotnet/build.py --acad-dir X    # 指定 AutoCAD 安装目录
    python dotnet/build.py --check         # 只检查工具链，不构建

为什么单独一个脚本：AutoCAD 2025 的托管 API 必须 .NET 8，且要引用安装目录里的
acdbmgd/acmgd/accoremgd。脚本负责"先检查再构建"，把缺件说清楚，而不是让
`dotnet build` 抛一堆 MSB 错误。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ACAD = r"D:\Program Files\Autodesk\AutoCAD 2025"
DLL_NAME = "AcadKit.Plugin.dll"

MANAGED = ("acdbmgd.dll", "acmgd.dll", "accoremgd.dll")


def dotnet() -> str:
    for cand in ("dotnet",):
        try:
            out = subprocess.run([cand, "--version"], capture_output=True, text=True,
                                 timeout=60)
            if out.returncode == 0:
                return cand
        except Exception:                           # noqa: BLE001
            pass
    return ""


def check(acad_dir: str) -> list:
    problems = []
    if not dotnet():
        problems.append("找不到 dotnet（需要 .NET SDK 8+）")
    if not os.path.isdir(acad_dir):
        problems.append("AutoCAD 目录不存在：%s" % acad_dir)
    else:
        for name in MANAGED:
            p = os.path.join(acad_dir, name)
            if not os.path.isfile(p):
                problems.append("缺托管程序集：%s" % p)
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="构建 acadkit .NET 插件")
    ap.add_argument("--acad-dir", default=DEFAULT_ACAD)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--configuration", default="Release")
    args = ap.parse_args(argv)

    problems = check(args.acad_dir)
    if problems:
        print("工具链检查未通过：")
        for p in problems:
            print("  - %s" % p)
        return 2
    print("工具链 OK：dotnet %s，AcadDir=%s"
          % (subprocess.run([dotnet(), "--version"], capture_output=True,
                            text=True).stdout.strip(), args.acad_dir))
    if args.check:
        return 0

    cmd = [dotnet(), "build", HERE, "-c", args.configuration,
           "-p:AcadDir=%s" % args.acad_dir, "-v", "minimal"]
    print("$ " + " ".join(cmd))
    rc = subprocess.run(cmd, cwd=HERE).returncode
    out = os.path.join(HERE, "bin", args.configuration, DLL_NAME)
    if rc == 0 and os.path.isfile(out):
        print("\n构建成功：%s（%d 字节）" % (out, os.path.getsize(out)))
        print("加载方式：AutoCAD 里 NETLOAD 选这个 DLL，或 python tools/netload.py")
        return 0
    print("\n构建失败（rc=%s）" % rc)
    return rc or 1


if __name__ == "__main__":
    sys.exit(main())

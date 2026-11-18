#!/usr/bin/env python3
"""部署/加载 acadkit 的 .NET 插件，并跑它的命令、**按图面读回**验收。

    python tools/netload.py --deploy          # 部署 bundle 到 ApplicationPlugins
    python tools/netload.py                   # 部署 + 启动 AutoCAD + 跑命令 + 验收
    python tools/netload.py --undeploy        # 卸载 bundle
    python tools/netload.py --no-launch       # 只部署，不动 AutoCAD

为什么不用 NETLOAD（实测 2026-11-18）：
    `_.NETLOAD` 会弹**模态文件对话框**，`SendCommand` 永久阻塞（FILEDIA=0 也不行），
    整轮用例挂死。所以改走 Autoloader：把 bundle 放进
    `%APPDATA%\\Autodesk\\ApplicationPlugins\\`，AutoCAD 启动时按
    PackageContents.xml 的 `LoadOnAutoCADStartup="True"` 自动加载。

验收方式：插件每条命令把结果写成图面上一行 MText（`AKRESULT <tag>: ...`），
这里用 acadkit 既有的"读回"提取，不看命令行文本、不信任返回值。
"""

from __future__ import annotations

import argparse
from typing import Any, Dict
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit.core import com, launch                       # noqa: E402
from acadkit.judges.case import CaseRunner                 # noqa: E402
from acadkit.judges.read import read_drawing               # noqa: E402

DLL_DEFAULT = os.path.join(ROOT, "dotnet", "bin", "Release", "AcadKit.Plugin.dll")
PKG_SRC = os.path.join(ROOT, "dotnet", "bundle", "PackageContents.xml")
BUNDLE = "AcadKit.Plugin.bundle"
RESULT_MARK = "AKRESULT"

# AutoCAD 安装目录（信任路径）+ 注册表 autoload 键
ACAD_DIR = os.environ.get("ACAD_DIR", r"D:\Program Files\Autodesk\AutoCAD 2025")
INSTALL_SUBDIR = os.path.join("Plugins", "AcadKit")
REG_ROOT = r"Software\Autodesk\AutoCAD\R25.0"
REG_APP = "AcadKitPlugin"


def plugins_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "Autodesk", "ApplicationPlugins")


def bundle_path() -> str:
    return os.path.join(plugins_dir(), BUNDLE)


def install_dir() -> str:
    return os.path.join(ACAD_DIR, INSTALL_SUBDIR)


def _reg_products():
    """列出本机所有 AutoCAD 产品键（可能多产品共存，例如 Electrical）。"""
    import winreg
    out = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return [n for n in out if n.startswith("ACAD-")]


def deploy(dll: str) -> Dict[str, Any]:
    """把 DLL 复制到 AutoCAD 安装目录，并在每个产品键下写 autoload（幂等）。"""
    import winreg
    if not os.path.isfile(dll):
        raise SystemExit("找不到 DLL：%s（先跑 python dotnet/build.py）" % dll)
    dst = install_dir()
    os.makedirs(dst, exist_ok=True)
    target = os.path.join(dst, os.path.basename(dll))
    shutil.copy2(dll, target)

    keys = []
    for prod in _reg_products():
        path = r"%s\%s\Applications\%s" % (REG_ROOT, prod, REG_APP)
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                    winreg.KEY_WRITE) as k:
                winreg.SetValueEx(k, "DESCRIPTION", 0, winreg.REG_SZ,
                                  "acadkit .NET channel")
                winreg.SetValueEx(k, "LOADER", 0, winreg.REG_SZ, target)
                winreg.SetValueEx(k, "MANAGED", 0, winreg.REG_DWORD, 1)
                # 2 = 启动时加载（实测 1 不加载；Autodesk 自带插件用 2/6/12）
                winreg.SetValueEx(k, "LOADCTRLS", 0, winreg.REG_DWORD, 2)
            keys.append(path)
        except OSError as exc:
            print("  写注册表失败 %s：%s" % (path, exc))
    return {"dll": target, "keys": keys,
            "bundle": os.path.join(plugins_dir(), BUNDLE)}


def undeploy() -> Dict[str, Any]:
    """删注册表键 + 安装目录副本 + 旧 bundle；返回做了什么。"""
    import winreg
    done = {"keys": [], "dir": False, "bundle": False}
    for prod in _reg_products():
        path = r"%s\%s\Applications\%s" % (REG_ROOT, prod, REG_APP)
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            done["keys"].append(path)
        except OSError:
            pass
    if os.path.isdir(install_dir()):
        shutil.rmtree(install_dir(), ignore_errors=True)
        done["dir"] = True
    b = bundle_path()
    if os.path.isdir(b):
        shutil.rmtree(b, ignore_errors=True)
        done["bundle"] = True
    return done


def _results(drawing) -> dict:
    out = {}
    for ent in drawing.of_type("MTEXT") + drawing.of_type("TEXT"):
        text = str(ent.get("TextString") or "")
        m = re.match(r"%s\s+([A-Z_]+):\s*(.*)" % RESULT_MARK, text, re.S)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _send(doc, line: str, settle: float = 0.8) -> None:
    com.retry(lambda: doc.SendCommand(line), label="SendCommand(%r)" % line[:24])
    time.sleep(settle)


def run(dll: str, keep: bool, workdir: str) -> int:
    info = launch.launch()
    app = info["app"]
    print("AutoCAD：%s（profile=%r）"
          % ("本次启动" if info["launched"] else "附加到已运行实例", info.get("profile")))
    runner = CaseRunner(app, workdir, log=lambda m: print(m))
    runner.ensure_baseline_doc()
    doc = runner.new_doc("netload")
    com.retry(lambda: int(doc.ModelSpace.Count), label="ready")

    for cmd in ("ACADKITVERSION", "ACADKITREVOLVE", "ACADKITLAYERSTATE", "ACADKITINFO"):
        print(">>> %s" % cmd)
        _send(doc, "%s\n" % cmd, settle=1.0)

    drawing = read_drawing(doc, "memory")
    res = _results(drawing)
    print("\n=== 读回结果 ===")
    if not res:
        print("  （没有 AKRESULT —— bundle 没被加载：AutoCAD 必须**新启动**才会读 ApplicationPlugins）")
    for k, v in res.items():
        print("  %-11s %s" % (k, v))

    checks = {}
    checks["loaded"] = "plugin=" in res.get("VERSION", "")
    m = re.search(r"volume=([\d.]+).*expected=([\d.]+).*ratio=([\d.]+)",
                  res.get("REVOLVE", ""))
    checks["revolve"] = bool(m) and abs(float(m.group(3)) - 1.0) <= 0.01
    checks["layerstate"] = "restored=1" in res.get("LAYERSTATE", "")
    checks["info"] = "commands=" in res.get("INFO", "")

    print("\n=== 判据 ===")
    for k, v in checks.items():
        print("  %-12s %s" % (k, "PASS" if v else "FAIL"))
    print("  合计 %d/%d" % (sum(1 for v in checks.values() if v), len(checks)))

    try:
        runner._close(doc, "netload")
        if info["launched"] and not keep:
            from acadkit.judges.case import finish
            fin = finish(app, runner.baseline_doc, quit_app=True)
            print("收尾：%s" % fin)
    except Exception as exc:                        # noqa: BLE001
        print("收尾失败：%s" % exc)
    return 0 if all(checks.values()) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="部署并验收 acadkit .NET 插件")
    ap.add_argument("--dll", default=DLL_DEFAULT)
    ap.add_argument("--deploy", action="store_true", help="只部署")
    ap.add_argument("--undeploy", action="store_true", help="卸载 bundle")
    ap.add_argument("--no-launch", action="store_true", help="只部署，不启动 AutoCAD")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workdir", default=None)
    args = ap.parse_args(argv)

    if args.undeploy:
        done = undeploy()
        print("已卸载：注册表 %d 个键、安装目录 %s、旧 bundle %s"
              % (len(done["keys"]), done["dir"], done["bundle"]))
        return 0

    info = deploy(args.dll)
    print("DLL 已安装：%s" % info["dll"])
    for k in info["keys"]:
        print("注册表：%s（LOADCTRLS=2, MANAGED=1）" % k)
    if not info["keys"]:
        print("!! 没找到 AutoCAD 产品键（%s），插件不会自动加载" % REG_ROOT)
    if args.deploy or args.no_launch:
        print("提示：autoload 只在 AutoCAD **启动时**生效；已在运行的实例需要重启。")
        return 0

    workdir = args.workdir or os.path.join(ROOT, "_scratch",
                                           "netload_%s" % time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(workdir, exist_ok=True)
    return run(args.dll, args.keep, workdir)


if __name__ == "__main__":
    sys.exit(main())

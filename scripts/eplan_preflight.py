#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""EPLAN 桥接前置自检：一条命令报出「现在卡在哪一环、下一步做什么」。

只读、不改任何东西。检查项（按桥接链条顺序）：

  1. 环境变量        EPLAN_EXE / EPLAN_BIN / EPLAN_MCP_PROFILE / EPLAN_MCP_WORKSPACE
  2. 平台本体        Eplan.exe 是否存在（env → 常见路径 → 注册表 → PATH）
  3. API 程序集      编译 Add-in 需要的 5 个 Eplan.EplApi.*.dll
  4. 编译器          Framework64 v4.0.30319\csc.exe
  5. pywin32         命名管道传输依赖（查 kit 用的那个 venv）
  6. Add-in 源码      addin/*.cs + build.ps1 / register.ps1 / launch-trial.ps1
  7. Add-in 产物      private/addin/Codex.EplAddin.Bridge.dll
  8. 发现目录        %LOCALAPPDATA%\\EplanMcp\\instances\\*.json + 对应进程是否活着
  9. 工作目录        private/artifacts（snapshot / 证据落盘）

用法：
    python scripts/eplan_preflight.py
    python scripts/eplan_preflight.py --json
退出码：全部就绪 0；有阻塞项 1（仅缺可选件时为 0）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # nsa-mcp-hub
HUB = Path(os.environ.get("CAD_SERVERS_HOME", os.path.expanduser(r"~\cad-servers")))
EPLAN_DIR = HUB / "MCP" / "EPLAN"
ADDIN_DIR = EPLAN_DIR / "addin"
PRIVATE = EPLAN_DIR / "private"
BUILT_DLL = PRIVATE / "addin" / "Codex.EplAddin.Bridge.dll"
# 与 addin/build.ps1 里 /reference 的五个完全一致（注意 EServicesu 是大写 S）
API_ASSEMBLIES = (
    "Eplan.EplApi.AFu.dll",
    "Eplan.EplApi.Baseu.dll",
    "Eplan.EplApi.DataModelu.dll",
    "Eplan.EplApi.HEServicesu.dll",
    "Eplan.EplApi.EServicesu.dll",
)

SEARCH_ROOTS = (
    r"C:\Program Files\EPLAN",
    r"C:\Program Files (x86)\EPLAN",
    r"D:\Program Files\EPLAN",
    r"D:\EPLAN",
)

rows: list[dict] = []


def add(group: str, name: str, state: str, detail: str, hint: str = "") -> None:
    rows.append({"group": group, "name": name, "state": state,
                 "detail": detail, "hint": hint})


def find_platform_exe() -> tuple[Path | None, str]:
    env = os.environ.get("EPLAN_EXE")
    if env:
        p = Path(env)
        return (p, "EPLAN_EXE") if p.is_file() else (None, "EPLAN_EXE 指向的文件不存在")
    for root in SEARCH_ROOTS:
        base = Path(root)
        if not base.is_dir():
            continue
        for candidate in base.glob("Platform/*/Bin/Eplan.exe"):
            return candidate, "常见路径 Platform\\*\\Bin"
        for candidate in base.glob("Electric P8/*/Bin/Eplan.exe"):
            return candidate, "常见路径 Electric P8\\*\\Bin"
    # 注册表（只看平台条目，License Client 不算）
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE,):
            for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                try:
                    with winreg.OpenKey(hive, sub) as root_key:
                        for index in range(winreg.QueryInfoKey(root_key)[0]):
                            try:
                                with winreg.OpenKey(root_key, winreg.EnumKey(root_key, index)) as item:
                                    display = str(winreg.QueryValueEx(item, "DisplayName")[0])
                                    try:
                                        location = str(winreg.QueryValueEx(item, "InstallLocation")[0])
                                    except OSError:
                                        location = ""
                            except OSError:
                                continue
                            lowered = display.lower()
                            if "eplan" not in lowered or "license" in lowered or "identity" in lowered:
                                continue
                            if location and Path(location).is_dir():
                                for candidate in Path(location).glob("**/Bin/Eplan.exe"):
                                    return candidate, "注册表 %s" % display
                except OSError:
                    continue
    except Exception:                                          # noqa: BLE001
        pass
    return None, "没找到 Eplan.exe"


def eplan_processes() -> list[dict]:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process EPLAN -ErrorAction SilentlyContinue | "
             "Select-Object Id,Path | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30).stdout.strip()
        if not out:
            return []
        data = json.loads(out)
        return data if isinstance(data, list) else [data]
    except Exception:                                          # noqa: BLE001
        return []


def instances_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "EplanMcp" / "instances"


def main() -> int:
    want_json = "--json" in sys.argv[1:]

    # 1. 环境变量
    env_hints = {
        "EPLAN_EXE": "装完平台后指向 ...\\Bin\\Eplan.exe（必需）",
        "EPLAN_BIN": "编译 Add-in 时用；一般等于 EPLAN_EXE 的目录",
        "EPLAN_MCP_PROFILE": "不设就是 review（只读）；写操作才要 trial",
        "EPLAN_MCP_WORKSPACE": "不设就用 MCP/EPLAN/private",
        "EPLAN_MCP_TRIAL_INSTANCE": "由 launch-trial.ps1 临时设置，不用手动给",
    }
    for key, hint in env_hints.items():
        value = os.environ.get(key)
        add("环境变量", key, "ok" if value else "info",
            value or "未设置", "" if value else hint)

    # 2. 平台本体
    exe, how = find_platform_exe()
    if exe:
        add("平台", "Eplan.exe", "ok", "%s（%s）" % (exe, how))
    else:
        add("平台", "Eplan.exe", "fail", how,
            "装 EPLAN Platform 2.9 / Electric P8；本机目前只有 License Client")

    # 3. API 程序集
    bin_dir = Path(os.environ.get("EPLAN_BIN", "")) if os.environ.get("EPLAN_BIN") else (
        exe.parent if exe else None)
    if bin_dir and bin_dir.is_dir():
        missing = [n for n in API_ASSEMBLIES if not (bin_dir / n).is_file()]
        if missing:
            add("API", "Eplan.EplApi.*.dll", "fail",
                "缺 %d 个：%s" % (len(missing), ", ".join(missing)), "确认 EPLAN_BIN 指向 Bin 目录")
        else:
            add("API", "Eplan.EplApi.*.dll", "ok", "5 个都在 %s" % bin_dir)
    else:
        add("API", "Eplan.EplApi.*.dll", "fail", "没有 API 目录（EPLAN_BIN 未设且没找到平台）",
            "装完平台后设 EPLAN_BIN 到 ...\\Bin")

    # 4. 编译器
    csc = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / \
        "v4.0.30319" / "csc.exe"
    add("工具链", "csc.exe (x64 .NET Framework)", "ok" if csc.is_file() else "fail",
        str(csc) if csc.is_file() else "缺失",
        "" if csc.is_file() else "装 .NET Framework 4.x 运行时/开发包")

    # 5. pywin32（kit 用的 venv）
    venv_py = HUB / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        probe = subprocess.run([str(venv_py), "-c", "import win32file, win32event, pywintypes"],
                               capture_output=True, text=True, timeout=120)
        add("工具链", "pywin32（命名管道）", "ok" if probe.returncode == 0 else "fail",
            "venv 可用" if probe.returncode == 0 else (probe.stderr or "").strip()[:160],
            "" if probe.returncode == 0 else "在 CAD_SERVERS_HOME/.venv 里 pip install pywin32")
    else:
        add("工具链", "pywin32（命名管道）", "fail", "没找到 %s" % venv_py, "先建 CAD_SERVERS_HOME/.venv")

    # 6. Add-in 源码与脚本
    cs = sorted(ADDIN_DIR.glob("*.cs")) if ADDIN_DIR.is_dir() else []
    scripts_ok = all((ADDIN_DIR / n).is_file() for n in
                     ("build.ps1", "register.ps1", "launch-trial.ps1"))
    add("Add-in", "源码与脚本", "ok" if cs and scripts_ok else "fail",
        "%d 个 .cs，脚本%s齐" % (len(cs), "已" if scripts_ok else "不"),
        "" if (cs and scripts_ok) else "检查 CAD_SERVERS_HOME/MCP/EPLAN/addin")

    # 7. 产物
    add("Add-in", "Codex.EplAddin.Bridge.dll", "ok" if BUILT_DLL.is_file() else "info",
        str(BUILT_DLL) if BUILT_DLL.is_file() else "还没编译",
        "" if BUILT_DLL.is_file() else "有平台后跑 addin\\build.ps1")

    # 8. 发现目录 + 运行中的 EPLAN
    inst = instances_dir()
    files = sorted(inst.glob("*.json")) if inst.is_dir() else []
    procs = eplan_processes()
    add("桥接", "运行中的 EPLAN 进程", "ok" if procs else "info",
        ", ".join("pid=%s" % p.get("Id") for p in procs) if procs else "没有 EPLAN 在跑")
    if files:
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                add("桥接", path.name, "fail", "发现文件解析失败", "删掉它重启 EPLAN")
                continue
            add("桥接", path.name, "ok" if procs else "info",
                "pid=%s build=%s trial=%s pipe=%s"
                % (data.get("pid"), data.get("build"),
                   data.get("trial_writes_enabled"), data.get("pipe")))
    else:
        add("桥接", "发现文件", "info",
            "%s（没有 *.json）" % inst,
            "Add-in 注册并随 EPLAN 启动后才会写；本机缺平台，正常为空")

    # 9. 工作目录
    artifacts = PRIVATE / "artifacts"
    add("工作目录", "private/artifacts", "ok" if artifacts.is_dir() else "info",
        str(artifacts) if artifacts.is_dir() else "不存在（snapshot 无处落盘）",
        "" if artifacts.is_dir() else "mkdir 一下，或让首次抓证据时自动建")

    # 汇总：算出「现在能走到第几步」
    failures = [r for r in rows if r["state"] == "fail"]
    api_ready = bool(bin_dir) and all((bin_dir / n).is_file() for n in API_ASSEMBLIES)
    if not exe:
        stage = "0. 前置（还没装平台本体）"
    elif not api_ready:
        stage = "1. 编译 Add-in（缺 API 程序集）"
    elif not BUILT_DLL.is_file():
        stage = "1. 编译 Add-in"
    elif not files:
        stage = "2. 注册 Add-in 并启动 EPLAN"
    elif not procs:
        stage = "3. 启动 EPLAN"
    else:
        stage = "4. 只读验证（projects → pages → functions）"

    if want_json:
        print(json.dumps({"stage": stage, "blocking": len(failures), "rows": rows},
                         ensure_ascii=False, indent=1))
    else:
        print("EPLAN 桥接前置自检（只读）")
        print("=" * 72)
        group = None
        for row in rows:
            if row["group"] != group:
                group = row["group"]
                print("\n[%s]" % group)
            mark = {"ok": "OK  ", "fail": "BLOCK", "info": "  - "}[row["state"]]
            print("  %-5s %-32s %s" % (mark, row["name"], row["detail"]))
            if row["hint"]:
                print("        %s %s" % ("→" if row["state"] == "fail" else " ", row["hint"]))
        print("\n" + "=" * 72)
        print("当前可到：%s" % stage)
        if failures:
            print("阻塞 %d 项，最先要解决的：" % len(failures))
            for row in failures[:3]:
                print("  - %s：%s" % (row["name"], row["hint"] or row["detail"]))
        else:
            print("没有阻塞项。下一步：%s" % stage)
        print("\n手册：docs/eplan-bridge-handoff.md")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

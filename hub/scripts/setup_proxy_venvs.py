#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""为被代理的 CAD MCP server 建立**各自独立**的 venv。

为什么要独立：三个 server 对 mcp SDK 的版本要求互斥——

* UG    : ``mcp==1.26.0``（镜像上的 1.27.1 会拉不兼容的 mcp-types 2.0.0）
* EPLAN : ``mcp>=1.27.1,<2`` + jsonschema + pywin32
* CATIA : ``mcp>=1.7,<3`` + pywin32

共享 ``CAD-Agent-Hub/.venv`` 时只能满足其中一个。hub 侧的解析顺序是
``venv_python(<server_dir>, <hub_root>)``：先找 ``MCP/<SERVER>/.venv``，
找不到才退回仓库根的共享 venv，所以**建不建都能跑**，建了就隔离。

用法::

    python scripts/setup_proxy_venvs.py              # 缺哪个建哪个（幂等）
    python scripts/setup_proxy_venvs.py --force      # 全部删掉重建
    python scripts/setup_proxy_venvs.py --only UG    # 只处理一台
    python scripts/setup_proxy_venvs.py --check      # 只体检，不动文件
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

HUB = os.environ.get("CAD_AGENT_HUB", r"D:\bililive\CAD-Agent-Hub")
BASE_PYTHON = os.path.join(HUB, ".venv", "Scripts", "python.exe")


@dataclass
class Server:
    name: str
    directory: str
    #: 没有 requirements.txt 时用这几个包
    packages: list[str] = field(default_factory=list)

    @property
    def python(self) -> str:
        return os.path.join(self.directory, ".venv", "Scripts", "python.exe")

    @property
    def requirements(self) -> str:
        return os.path.join(self.directory, "requirements.txt")


def servers() -> list[Server]:
    mcp = os.path.join(HUB, "MCP")
    return [
        Server("UG", os.path.join(mcp, "UG")),
        Server("CATIA", os.path.join(mcp, "CATIA")),
        Server(
            "EPLAN",
            os.path.join(mcp, "EPLAN"),
            ["mcp>=1.27.1,<2", "jsonschema>=4.25,<5", "pywin32>=306"],
        ),
    ]


def _run(cmd: list[str], cwd: str | None = None, label: str | None = None) -> int:
    """跑一条命令；label 用于把长命令压成一行显示。"""
    printable = label or " ".join(
        os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)
    )
    print("   $", printable, flush=True)
    return subprocess.call(cmd, cwd=cwd)


def _base_python() -> str:
    if os.path.isfile(BASE_PYTHON):
        return BASE_PYTHON
    return sys.executable


def ensure_venv(server: Server, *, force: bool, dry: bool) -> None:
    venv_dir = os.path.join(server.directory, ".venv")
    if force and os.path.isdir(venv_dir):
        print("   - 删除旧 venv:", venv_dir)
        if not dry:
            shutil.rmtree(venv_dir, ignore_errors=True)
    if os.path.isfile(server.python):
        print("   = venv 已存在，跳过创建")
        return
    print("   + 创建 venv:", venv_dir)
    if dry:
        return
    rc = _run([_base_python(), "-m", "venv", venv_dir])
    if rc != 0:
        raise SystemExit("venv 创建失败，退出码 %d" % rc)


def install(server: Server, *, force: bool, dry: bool) -> None:
    if not force and not os.path.isfile(server.python):
        return
    print("   + 安装依赖")
    if dry:
        return
    has_req = os.path.isfile(server.requirements) and os.path.getsize(server.requirements) > 0
    if has_req:
        rc = _run([server.python, "-m", "pip", "install", "-q", "-r", server.requirements],
                  cwd=server.directory)
    else:
        if not server.packages:
            print("   ! 既没有 requirements.txt 也没给 packages，跳过")
            return
        rc = _run([server.python, "-m", "pip", "install", "-q", *server.packages],
                  cwd=server.directory)
    if rc != 0:
        raise SystemExit("pip install 失败，退出码 %d" % rc)


def verify(server: Server) -> bool:
    if not os.path.isfile(server.python):
        print("   x 没有 venv:", server.python)
        return False
    code = (
        "import sys; print('   python', sys.version.split()[0], '|', sys.prefix)\n"
        "import mcp; print('   mcp OK')\n"
    )
    if server.name == "EPLAN":
        code += "import jsonschema; print('   jsonschema OK')\n"
    if server.name in ("EPLAN", "CATIA"):
        code += "import win32com; print('   pywin32 OK')\n"
    return _run([server.python, "-c", code], label="校验导入（mcp%s）" %
                ("+jsonschema+pywin32" if server.name == "EPLAN"
                 else "+pywin32" if server.name == "CATIA" else "")) == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="建立 proxy server 各自的 venv")
    ap.add_argument("--force", action="store_true", help="删除并重建")
    ap.add_argument("--only", action="append", help="只处理指定 server（可多次）")
    ap.add_argument("--check", action="store_true", help="只体检，不改动")
    args = ap.parse_args(argv)

    print("hub:", HUB)
    print("base python:", _base_python())
    failed: list[str] = []
    for server in servers():
        if args.only and server.name not in args.only:
            continue
        print("\n[%s] %s" % (server.name, server.directory))
        if args.check:
            ok = verify(server)
        else:
            ensure_venv(server, force=args.force, dry=False)
            install(server, force=args.force, dry=False)
            ok = verify(server)
        if not ok:
            failed.append(server.name)

    print("\n结果:", "全部就绪" if not failed else "失败: %s" % ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

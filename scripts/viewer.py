#!/usr/bin/env python3
"""cad-viewer 封装：起服务 / 复用 / 生成 review 链接 / 复核。

cad-viewer 是**本机已装**的自包含 viewer（`~/.agents/skills/cad-viewer`，
`scripts/viewer/backend/server.mjs` 1.1 MB，无 npm 依赖），支持
STEP / STL / GLB / DXF / G-code / URDF / SDF 的交互查看。

它自己的后端接口（实测）：
    GET  /__cad/server?dir=<dir>              → JSON：app/backend/viewerVersion/pid
    GET  /__cad/catalog?dir=<dir>             → JSON：entries[{file,kind,url}]
    GET  /__cad/step-source-status?dir=&file= → JSON：ok / sourceKind
    GET  /__cad/asset?file=<fileRef>&dir=<dir>→ 文件字节

判据（verify）：
1. server JSON 里 app == "cad-viewer" 且 backend == "local-fs"；
2. catalog 里能找到我们给的每个文件的 basename；
3. 给的是 STEP 时，step-source-status 返回 ok=true 且 sourceKind=step。

**边界**：浏览器里 WebGL 的真实渲染无法在无头环境验证（需要浏览器）；glb 产物的
生成接口是 POST（当前载荷未打通，实测 400），所以这里只保证"后端认了这些文件"。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Sequence, Tuple

VIEWER_ENV = "NSA_CAD_VIEWER"
DEFAULT_PORT = 4178


def viewer_root() -> str:
    """定位 cad-viewer 的 scripts/viewer 目录（可用 NSA_CAD_VIEWER 覆盖）。"""
    cands = []
    env = os.environ.get(VIEWER_ENV, "").strip()
    if env:
        cands.append(env)
        cands.append(os.path.join(env, "scripts", "viewer"))
    home = os.path.expanduser("~")
    for base in (os.path.join(home, ".agents", "skills", "cad-viewer"),
                 os.path.join(home, ".dsh", "skills", "cad-viewer"),
                 os.path.join(home, ".claude", "skills", "cad-viewer")):
        cands.append(os.path.join(base, "scripts", "viewer"))
    for c in cands:
        if os.path.isfile(os.path.join(c, "backend", "server.mjs")):
            return os.path.abspath(c)
    raise FileNotFoundError(
        "找不到 cad-viewer（server.mjs）；装好后设 NSA_CAD_VIEWER 指向 skill 目录")


def base_url(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> str:
    return "http://%s:%d" % (host, int(port))


def _get_json(url: str, timeout: float = 5.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            raw = r.read()
        return json.loads(raw.decode("utf-8"))
    except Exception:                                 # noqa: BLE001
        return None


def server_info(base: str, timeout: float = 3.0) -> Optional[dict]:
    info = _get_json(base.rstrip("/") + "/__cad/server", timeout=timeout)
    if not info or info.get("app") != "cad-viewer":
        return None
    return info


def catalog(base: str, directory: str, timeout: float = 15.0) -> List[dict]:
    url = (base.rstrip("/") + "/__cad/catalog?dir="
           + urllib.parse.quote(directory, safe=""))
    data = _get_json(url, timeout=timeout)
    if not data:
        return []
    return list(data.get("entries") or [])


def step_source_status(base: str, directory: str, file_name: str,
                       timeout: float = 20.0) -> Optional[dict]:
    url = (base.rstrip("/") + "/__cad/step-source-status?dir="
           + urllib.parse.quote(directory, safe="") + "&file="
           + urllib.parse.quote(file_name, safe=""))
    return _get_json(url, timeout=timeout)


def review_url(base: str, directory: str, file_name: Optional[str] = None) -> str:
    url = base.rstrip("/") + "/?dir=" + urllib.parse.quote(os.path.abspath(directory), safe="")
    if file_name:
        url += "&file=" + urllib.parse.quote(file_name, safe="")
    return url


def _pidfile(port: int) -> str:
    return os.path.join(tempfile.gettempdir(), "nsa-viewer-%d.pid" % int(port))


def start(directory: str, *, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
          wait: float = 25.0, log_path: Optional[str] = None) -> Dict[str, object]:
    """起服务或复用已在跑的服务。返回 {base, reused, log, pid}。"""
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        raise FileNotFoundError("目录不存在：%s" % directory)
    base = base_url(host, port)

    info = server_info(base, timeout=1.5)
    if info is not None:
        return {"base": base, "reused": True, "log": None,
                "pid": info.get("pid"), "info": info}

    root = viewer_root()
    node = "node"
    log_path = log_path or os.path.join(tempfile.gettempdir(),
                                        "nsa-viewer-%d.log" % int(port))
    log = open(log_path, "wb")
    proc = subprocess.Popen(
        [node, os.path.join("backend", "server.mjs"), "--port", str(port),
         "--host", host, "--dir", directory],
        cwd=root, stdout=log, stderr=subprocess.STDOUT)
    try:
        with open(_pidfile(port), "w", encoding="utf-8") as fh:
            fh.write(str(proc.pid))
    except OSError:
        pass

    deadline = time.time() + float(wait)
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = ""
            try:
                tail = open(log_path, encoding="utf-8", errors="replace").read()[-500:]
            except OSError:
                pass
            raise RuntimeError("viewer 启动即退出（code=%s）：%s" % (proc.returncode, tail))
        info = server_info(base, timeout=1.5)
        if info is not None:
            return {"base": base, "reused": False, "log": log_path,
                    "pid": info.get("pid"), "info": info}
        time.sleep(0.3)
    raise TimeoutError("等了 %.0f s 服务还没就绪；日志：%s" % (wait, log_path))


def stop(port: int = DEFAULT_PORT) -> Dict[str, object]:
    """按 pidfile 停掉我们起的服务（不动别人的进程）。"""
    pf = _pidfile(port)
    if not os.path.isfile(pf):
        return {"stopped": False, "reason": "没有 pidfile（不是本工具起的）"}
    try:
        pid = int(open(pf, encoding="utf-8").read().strip())
    except (OSError, ValueError):
        return {"stopped": False, "reason": "pidfile 损坏"}
    try:
        if os.name == "nt":
            res = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                 capture_output=True, text=True, timeout=15)
            ok = res.returncode == 0
        else:
            os.kill(pid, 15)
            ok = True
    except Exception as exc:                          # noqa: BLE001
        return {"stopped": False, "reason": "终止失败：%s" % exc, "pid": pid}
    try:
        os.remove(pf)
    except OSError:
        pass
    return {"stopped": bool(ok), "pid": pid}


def verify(base: str, directory: str, files: Sequence[str] = ()) -> Dict[str, object]:
    """复核：服务活着 + 目录被列出来 + 每个文件出现在 catalog（STEP 再看 step 源状态）。"""
    out: Dict[str, object] = {"base": base, "directory": os.path.abspath(directory)}
    info = server_info(base, timeout=4.0)
    out["server_ok"] = info is not None
    if info:
        out["viewer_version"] = info.get("viewerVersion")
        out["backend"] = info.get("backend")
        out["pid"] = info.get("pid")
    if not info:
        out["ok"] = False
        out["note"] = "服务没响应（未启动或端口不对）"
        return out

    entries = catalog(base, directory)
    names = {os.path.basename(str(e.get("file") or "").replace("\\", "/"))
             for e in entries}
    found, missing = [], []
    for f in files:
        (found if os.path.basename(f) in names else missing).append(os.path.basename(f))
    out["catalog_entries"] = len(entries)
    out["files_found"] = found
    out["files_missing"] = missing

    steps = [f for f in files if f.lower().endswith((".step", ".stp"))]
    step_ok: Dict[str, object] = {}
    for f in steps:
        st = step_source_status(base, directory, os.path.basename(f))
        step_ok[os.path.basename(f)] = bool(st and st.get("ok")
                                            and st.get("sourceKind") == "step")
    out["step_source_ok"] = step_ok
    out["ok"] = bool(info) and not missing and all(step_ok.values())
    out["note"] = ("后端已认出这些文件；浏览器内 WebGL 渲染需人工打开链接确认"
                   if out["ok"] else "有文件没被列出或 STEP 未被接受")
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="起/复用 cad-viewer 并给出 review 链接")
    ap.add_argument("--dir", default="", help="要看的产物目录（默认当前目录）")
    ap.add_argument("--file", default="", help="要直接打开的文件（相对 --dir）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--stop", action="store_true", help="停掉本工具起的服务")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.stop:
        res = stop(args.port)
        print(json.dumps(res, ensure_ascii=False) if args.json
              else ("已停止 pid=%s" % res.get("pid") if res.get("stopped")
                    else "未停止：%s" % res.get("reason")))
        return 0 if res.get("stopped") else 1

    directory = os.path.abspath(args.dir or os.getcwd())
    try:
        out = start(directory, host=args.host, port=args.port)
    except Exception as exc:                          # noqa: BLE001
        print("启动失败：%s" % exc, file=sys.stderr)
        return 2

    files = [args.file] if args.file else sorted(
        f for f in os.listdir(directory)
        if f.lower().endswith((".step", ".stp", ".stl", ".glb", ".dxf", ".gcode",
                               ".urdf", ".srdf", ".sdf", ".3mf")))
    url = review_url(out["base"], directory, args.file or None)

    ver = {} if args.no_verify else verify(out["base"], directory, files)
    payload = {"base": out["base"], "reused": out["reused"], "pid": out.get("pid"),
               "log": out.get("log"), "url": url, "files": files, "verify": ver}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print("viewer ：%s（%s，pid=%s）"
              % (out["base"], "复用已在跑的" if out["reused"] else "新启动", out.get("pid")))
        print("目录   ：%s（%d 个可看文件）" % (directory, len(files)))
        print("链接   ：%s" % url)
        if ver:
            print("复核   ：%s  catalog=%s 个  STEP=%s"
                  % ("过" if ver.get("ok") else "未过", ver.get("catalog_entries"),
                     ver.get("step_source_ok") or "无"))
            if ver.get("files_missing"):
                print("         缺：%s" % ", ".join(ver["files_missing"]))
            if ver.get("note"):
                print("         %s" % ver["note"])
        if out.get("log"):
            print("日志   ：%s" % out["log"])
    return 0 if (args.no_verify or ver.get("ok")) else 1


if __name__ == "__main__":
    sys.exit(main())

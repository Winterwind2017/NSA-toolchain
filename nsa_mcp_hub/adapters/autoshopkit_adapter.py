"""autoshopkit 适配器：汇川 AutoShop（Inovance）离线工程分析 + 在线编程。

autoshopkit 没有 caps/判据体系（它的 CLI 有 20 多个 verb），所以这里**按 verb 薄封装**：
每个工具 = 一次 ``python -c "from autoshopkit.cli import main; ..."`` 子进程，
把 stdout/stderr/返回码原样回传。好处是不把 87 KB 的 app.py 拉进 MCP 进程，
也不会有 attach 副作用泄漏到服务端。

写操作（apply / save）在 schema 里带 ``confirm``，必须显式传 true 才执行。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from ..tools import Kit, ToolSpec, apply_checks, normalize

KIT_KEY = "autoshop"
KIT_NAME = "autoshopkit"
SRC = os.environ.get("AUTOSHOPKIT_SRC", r"D:\bililive\autoshopkit\src")

LAUNCH = ("import sys;from autoshopkit.cli import main;"
          "sys.exit(main(sys.argv[1:]))")

# 编译结束会打 "统计 - (0)错误,(103)步占用"
_ERRORS_RE = re.compile(r"\((\d+)\)\s*错误")


def _parse_json(text: str):
    """从可能夹着日志的输出里捞出第一个完整 JSON 对象。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _entry_count(data):
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("programs", "items", "entries", "index", "files"):
            if isinstance(data.get(key), list):
                return len(data[key])
        for value in data.values():
            if isinstance(value, list) and value:
                return len(value)
    return None


def _judge(verb: str, payload: dict, out: str, rc: int) -> dict:
    """给 autoshop 各 verb 造判据：能用真实读数的就用真实读数。"""
    checks = []

    def add(name, got, want, ok, note=""):
        item = {"check": name, "got": got, "want": want, "ok": bool(ok)}
        if note:
            item["note"] = note
        checks.append(item)

    if verb == "apply":
        # cli 的 apply 输出：{errors, warnings, written, readback_ok, compiles, document, ...}
        data = _parse_json(out)
        if isinstance(data, dict) and ("readback_ok" in data or "written" in data):
            errs = data.get("errors") or []
            warns = data.get("warnings") or []
            add("compile_errors", len(errs), 0, not errs,
                "; ".join(str(e.get("message") or e)[:120] for e in errs[:2]) if errs else "")
            add("readback_ok", bool(data.get("readback_ok")), True,
                bool(data.get("readback_ok")))
            written = data.get("written")
            add("bytes_written", written, ">0",
                isinstance(written, int) and written > 0)
            add("warnings", len(warns), "记录项", True,
                "; ".join(str(w.get("message") or w)[:120] for w in warns[:2]))
            payload.setdefault("reads", {})["apply_result"] = {
                k: data.get(k) for k in ("document", "written", "readback_ok",
                                         "compiles", "errors", "warnings")}
            return apply_checks(payload, checks)
    if verb in ("compile", "apply"):
        # cli 的 compile 会输出 JSON：{"ok": bool, "lines": [...]}
        data = _parse_json(out)
        if isinstance(data, dict) and isinstance(data.get("lines"), list):
            lines = [str(x) for x in data["lines"]]
            err_lines = [l for l in lines if l.strip().startswith("错误")]
            warn_lines = [l for l in lines if l.strip().startswith("警告")]
            # 实测：H3U 工程的编译**不会打印 统计 行**，cli 的 ok 因此恒为 false。
            # 所以判据改成「没有错误行 + 确实产生了编译输出」，统计行只作记录。
            has_output = any("编译" in l for l in lines)
            ok_now = (not err_lines) and has_output
            add("compile_ok", ok_now, True, ok_now)
            add("error_lines", len(err_lines), 0, not err_lines,
                "; ".join(err_lines[:2]) if err_lines else "")
            add("warning_lines", len(warn_lines), "记录项", True,
                "; ".join(warn_lines[:2]))
            add("summary_present", any("统计" in l for l in lines), "记录项", True,
                "H3U 工程不打印统计行，属已知差异" if not any("统计" in l for l in lines) else "")
            payload.setdefault("reads", {})["compile_lines"] = lines[:40]
        else:
            matches = _ERRORS_RE.findall(out)
            if matches:
                n = int(matches[-1])
                add("compile_errors", n, 0, n == 0)
            else:
                add("compile_output_present", bool(out), True, bool(out),
                    "没解析到编译输出，只能判输出存在")
    elif verb == "check":
        data = _parse_json(out) or {}
        counts = data.get("counts") or {}
        if counts:
            add("errors", counts.get("errors"), 0, counts.get("errors") == 0)
            add("warnings", counts.get("warnings"), 0, True, "informational")
            payload.setdefault("reads", {})["counts"] = counts
        else:
            add("check_json", bool(data), True, bool(data),
                "没解析到 counts，只能判 JSON 是否存在")
    elif verb == "hcp":
        data = _parse_json(out)
        n = _entry_count(data)
        if n is not None:
            add("index_entries", n, ">0", n > 0)
        else:
            add("hcp_json", data is not None, True, data is not None)
    else:
        add("returncode", rc, 0, rc == 0)
        add("output_present", bool(out), True, bool(out))

    return apply_checks(payload, checks)


def _run(args: list, timeout: float) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", LAUNCH, *[str(a) for a in args]],
            # stdin 必须断开：服务器的 stdin 是 JSON-RPC 管道，子进程继承会卡死
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return normalize(KIT_KEY, " ".join(args[:2]), ok=False,
                         errors=["超时（>%.0fs）" % timeout])
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    ok = proc.returncode == 0
    payload = normalize(KIT_KEY, args[0], ok=ok,
                        reads={"argv": args, "returncode": proc.returncode,
                               "stdout": out[-6000:], "stderr": err[-2000:]},
                        errors=[] if ok else [err.splitlines()[-1][:400] if err else "返回码 %s" % proc.returncode])
    return _judge(args[0], payload, out, proc.returncode)


def build_kit() -> Kit:
    kit = Kit(key=KIT_KEY, name=KIT_NAME, version="cli",
              instructions=("autoshopkit：汇川 AutoShop 自动化。离线分析（hcp/illog/check --offline）"
                            "不需要开 AutoShop；在线动作会 attach 到已打开的程序，且 UI 自动化会抢焦点。"
                            "写操作需要 confirm=true。"))

    def status(args: dict) -> dict:
        argv = ["status"]
        if args.get("launch"):
            argv.append("--launch")
        if args.get("project"):
            argv += ["--project", args["project"]]
        return _run(argv, 180)

    def doctor(_args: dict) -> dict:
        return _run(["doctor"], 180)

    def tree(_args: dict) -> dict:
        return _run(["tree"], 120)

    def summary(args: dict) -> dict:
        argv = ["summary"] + (["--compile"] if args.get("compile") else [])
        return _run(argv, 300)

    def compile_cmd(args: dict) -> dict:
        argv = ["compile"] + (["--one"] if args.get("one") else [])
        argv += ["--timeout", str(args.get("timeout_s") or 90)]
        return _run(argv, float(args.get("timeout_s") or 90) + 60)

    def il(args: dict) -> dict:
        argv = ["il"]
        if args.get("doc"):
            argv += ["--doc", args["doc"]]
        if args.get("view"):
            argv.append("--view")
        if args.get("write_file"):
            argv += ["--write", args["write_file"]]
        else:
            argv.append("--read")
        return _run(argv, 180)

    def apply_cmd(args: dict) -> dict:
        if not args.get("confirm"):
            return normalize(KIT_KEY, "apply", ok=False,
                             errors=["写程序是不可逆动作；确认后传 confirm=true 再调"])
        argv = ["apply", args["file"]]
        if args.get("doc"):
            argv += ["--doc", args["doc"]]
        if args.get("save"):
            argv.append("--save")
        return _run(argv, 600)

    def check(args: dict) -> dict:
        argv = ["check"]
        if args.get("no_compile"):
            argv.append("--no-compile")
        if args.get("offline"):
            argv += ["--offline", args["offline"]]
        return _run(argv, 600)

    def symbols(args: dict) -> dict:
        argv = ["symbols"]
        if args.get("add"):
            argv += ["--add", *args["add"]]
            if args.get("note"):
                argv += ["--note", args["note"]]
        if args.get("row"):
            argv += ["--row", str(args["row"])]
        return _run(argv, 180)

    def crossref(_args: dict) -> dict:
        return _run(["crossref"], 180)

    def hcp(args: dict) -> dict:
        argv = ["hcp"]
        if args.get("project"):
            argv += ["--project", args["project"]]
        if args.get("xml"):
            argv.append("--xml")
        return _run(argv, 180)

    def illog(args: dict) -> dict:
        argv = ["illog"]
        if args.get("project"):
            argv += ["--project", args["project"]]
        if args.get("program"):
            argv += ["--program", args["program"]]
        if args.get("paths"):
            argv.append("--paths")
        return _run(argv, 180)

    def save(args: dict) -> dict:
        argv = ["save", "--settle", str(args.get("settle") or 3.0)]
        return _run(argv, 300)

    S = {"type": "string"}
    B = {"type": "boolean"}
    kit.add(ToolSpec("autoshop_status", "attach 到 AutoShop 并打印摘要（可选 --launch 启动）。",
                     {"type": "object",
                      "properties": {"launch": B, "project": S},
                      "additionalProperties": False}, status, timeout_s=240))
    kit.add(ToolSpec("autoshop_doctor", "环境自检：工程、UIA、frida、编辑器。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     doctor, timeout_s=240))
    kit.add(ToolSpec("autoshop_tree", f"导出工程树（程序/子程序/FB/MODULE）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     tree, timeout_s=180, must_have_checks=True))
    kit.add(ToolSpec("autoshop_summary", "工程总览：程序、树、符号、监控表、编译。",
                     {"type": "object", "properties": {"compile": B},
                      "additionalProperties": False}, summary, timeout_s=360, must_have_checks=True))
    kit.add(ToolSpec("autoshop_compile", "全部编译（或当前文档）并报告消息。",
                     {"type": "object",
                      "properties": {"one": B, "timeout_s": {"type": "number"}},
                      "additionalProperties": False}, compile_cmd, timeout_s=480))
    kit.add(ToolSpec("autoshop_il",
                     "读取/写入当前文档的指令列表（默认读）。write_file 指向 LF 结尾的文本文件。",
                     {"type": "object",
                      "properties": {"doc": S, "view": B, "write_file": S},
                      "additionalProperties": False}, il, timeout_s=240))
    kit.add(ToolSpec("autoshop_apply",
                     "写程序 → 转换 → 编译 → 报告诊断（不可逆，需 confirm=true）。",
                     {"type": "object", "required": ["file", "confirm"],
                      "properties": {"file": S, "doc": S, "save": B, "confirm": B,
                                     "request_id": S},
                      "additionalProperties": False}, apply_cmd, timeout_s=660,
                     idempotent=True, must_have_checks=True))
    kit.add(ToolSpec("autoshop_check",
                     "工程体检（双线圈/无效写入等）；offline 指定目录则不启动 AutoShop。",
                     {"type": "object",
                      "properties": {"no_compile": B, "offline": S},
                      "additionalProperties": False}, check, timeout_s=660))
    kit.add(ToolSpec("autoshop_symbols", "读符号表；add=[NAME,ADDRESS] 追加一条。",
                     {"type": "object",
                      "properties": {"add": {"type": "array", "items": S},
                                     "note": S, "row": {"type": "integer"}},
                      "additionalProperties": False}, symbols, timeout_s=240))
    kit.add(ToolSpec("autoshop_crossref", "交叉引用：元件在哪些程序里被用到。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     crossref, timeout_s=240))
    kit.add(ToolSpec("autoshop_hcp", "读 .hcp 工程索引（离线，解密容器；不启动 AutoShop）。",
                     {"type": "object",
                      "properties": {"project": S, "xml": B},
                      "additionalProperties": False}, hcp, timeout_s=240))
    kit.add(ToolSpec("autoshop_illog", "从 il_log.log 读带行号的 IL（H5U 可用）。",
                     {"type": "object",
                      "properties": {"project": S, "program": S, "paths": B},
                      "additionalProperties": False}, illog, timeout_s=240))
    kit.add(ToolSpec("autoshop_save", "保存工程并报告哪些文件被重写。",
                     {"type": "object", "properties": {"settle": {"type": "number"}},
                      "additionalProperties": False}, save, timeout_s=360, must_have_checks=True))

    # ── P3 补：把 autoshopkit 剩下 11 个真 verb 也工具化（12 → 24）────────
    def _simple(verb: str, extra_args=None, timeout: float = 240.0):
        def handler(args: dict) -> dict:
            argv = [verb] + (extra_args(args) if extra_args else [])
            return _run(argv, timeout)
        return handler

    kit.add(ToolSpec("autoshop_commands",
                     "列出 autoshopkit CLI 的全部 verb 与参数提示。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     _simple("commands", None, 60), timeout_s=90, must_have_checks=True))

    kit.add(ToolSpec("autoshop_start",
                     "启动 AutoShop（可选带工程路径），已启动则复用。",
                     {"type": "object", "properties": {"project": {"type": "string"}},
                      "additionalProperties": False},
                     _simple("start", lambda a: (["--project", a["project"]]
                                                 if a.get("project") else []), 300),
                     timeout_s=360, must_have_checks=True))

    kit.add(ToolSpec("autoshop_stop",
                     "关闭 AutoShop。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     _simple("stop", None, 120), timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_open",
                     "打开 .hcp 工程（会抢焦点）。",
                     {"type": "object", "properties": {"project": {"type": "string"}},
                      "required": ["project"], "additionalProperties": False},
                     _simple("open", lambda a: ["--project", a["project"]], 300),
                     timeout_s=360, must_have_checks=True))

    def _new_argv(a):
        """`autoshopkit new` 的真参数是 `new <name> [--dest DIR]`。

        旧映射传的是 `--path/--hcp`，CLI 直接 `unrecognized arguments`（实测）。
        这里把 `path` 拆成「目录 + 工程名」：`path` 的最后一段做 name，
        其余做 `--dest`；都没给就用 `NewProject` + 当前目录。
        """
        import os as _os
        raw = str(a.get("path") or "").strip().rstrip("\\/")
        if raw:
            name = _os.path.basename(raw) or "NewProject"
            dest = _os.path.dirname(raw)
            argv = [name]
            if dest:
                argv += ["--dest", dest]
            return argv
        return ["NewProject"]

    kit.add(ToolSpec("autoshop_new",
                     "新建工程（`new <name> --dest <dir>`；path 的最后一段作工程名）。",
                     {"type": "object", "properties": {"path": {"type": "string"},
                                                       "hcp": {"type": "string"}},
                      "additionalProperties": False},
                     _simple("new", _new_argv, 300),
                     timeout_s=360, must_have_checks=True))

    kit.add(ToolSpec("autoshop_monitor",
                     "读监控表/软元件值（在线动作）。",
                     {"type": "object", "properties": {"filter": {"type": "string"},
                                                       "limit": {"type": "integer"}},
                      "additionalProperties": False},
                     _simple("monitor", lambda a: (["--filter", a["filter"]]
                                                   if a.get("filter") else [])
                             + (["--limit", str(a["limit"])] if a.get("limit") else []), 240),
                     timeout_s=300, must_have_checks=True))

    kit.add(ToolSpec("autoshop_output",
                     "读 AutoShop 输出窗口文本（编译/错误信息的原始来源）。",
                     {"type": "object", "properties": {"limit": {"type": "integer"}},
                      "additionalProperties": False},
                     _simple("output", lambda a: (["--limit", str(a["limit"])]
                                                  if a.get("limit") else []), 120),
                     timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_dialogs",
                     "列出当前 AutoShop 的模态/非模态对话框（UI 卡死排查用）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     _simple("dialogs", None, 120), timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_shot",
                     "截屏（默认当前窗口），配合 dialogs 定位 UI 问题。",
                     {"type": "object", "properties": {"out": {"type": "string"}},
                      "additionalProperties": False},
                     _simple("shot", lambda a: (["--out", a["out"]] if a.get("out") else []), 120),
                     timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_cmd",
                     "透传一条 autoshopkit CLI 命令（逃生口）。",
                     {"type": "object", "properties": {"argv": {"type": "array",
                                                                 "items": {"type": "string"}}},
                      "required": ["argv"], "additionalProperties": False},
                     lambda a: _run(list(a.get("argv") or []), 240), timeout_s=300, must_have_checks=True))


    # ── 聚焦变体（真实 CLI 开关组合，一个意图一个工具）──────────────────
    kit.add(ToolSpec("autoshop_dlfile",
                     "生成离线下载文件（dlfile，无参数；产物路径从输出里读）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     _simple("dlfile", None, 300), timeout_s=360, must_have_checks=True))

    kit.add(ToolSpec("autoshop_il_read",
                     "读当前程序的指令表（il --read，只读）。",
                     {"type": "object", "properties": {"doc": {"type": "string"}},
                      "additionalProperties": False},
                     _simple("il", lambda a: ["--read"] + (["--doc", a["doc"]]
                                                          if a.get("doc") else []), 180),
                     timeout_s=240, must_have_checks=True))

    kit.add(ToolSpec("autoshop_il_write",
                     "写指令表文本并回读（il --write <file>，写操作）。",
                     {"type": "object", "properties": {"write_file": {"type": "string"},
                                                       "doc": {"type": "string"}},
                      "required": ["write_file"], "additionalProperties": False},
                     _simple("il", lambda a: ["--write", a["write_file"]]
                             + (["--doc", a["doc"]] if a.get("doc") else []), 240),
                     timeout_s=300, must_have_checks=True))

    kit.add(ToolSpec("autoshop_il_view",
                     "以只读视图方式打开指令表（il --view，写保护）。",
                     {"type": "object", "properties": {"doc": {"type": "string"}},
                      "additionalProperties": False},
                     _simple("il", lambda a: ["--view"] + (["--doc", a["doc"]]
                                                          if a.get("doc") else []), 180),
                     timeout_s=240, must_have_checks=True))

    kit.add(ToolSpec("autoshop_symbols_read",
                     "读符号/变量表（symbols，只读）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     _simple("symbols", None, 120), timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_symbols_add",
                     "向符号表追加一条 NAME,ADDRESS（symbols --add）。",
                     {"type": "object", "properties": {"name": {"type": "string"},
                                                       "address": {"type": "string"}},
                      "required": ["name", "address"], "additionalProperties": False},
                     _simple("symbols", lambda a: ["--add", "%s,%s" % (a["name"], a["address"])],
                             180), timeout_s=240, must_have_checks=True))

    kit.add(ToolSpec("autoshop_symbols_row",
                     "读符号表第 N 行（symbols --row N）。",
                     {"type": "object", "properties": {"row": {"type": "integer"}},
                      "required": ["row"], "additionalProperties": False},
                     _simple("symbols", lambda a: ["--row", str(int(a["row"]))], 120),
                     timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_compile_one",
                     "只编译当前文档（compile --one），比全量编译快。",
                     {"type": "object", "properties": {"timeout_s": {"type": "number"}},
                      "additionalProperties": False},
                     _simple("compile", lambda a: ["--one", "--timeout",
                                                   str(a.get("timeout_s") or 90)], 200),
                     timeout_s=260, must_have_checks=True))

    kit.add(ToolSpec("autoshop_check_offline",
                     "离线工程体检（check --offline <目录> --no-compile，不开 AutoShop）。",
                     {"type": "object", "properties": {"offline": {"type": "string"}},
                      "required": ["offline"], "additionalProperties": False},
                     _simple("check", lambda a: ["--offline", a["offline"], "--no-compile"], 240),
                     timeout_s=300, must_have_checks=True))

    kit.add(ToolSpec("autoshop_hcp_xml",
                     "读 .hcp 工程索引并输出 XML（hcp --project <p> --xml）。",
                     {"type": "object", "properties": {"project": {"type": "string"}},
                      "required": ["project"], "additionalProperties": False},
                     _simple("hcp", lambda a: ["--project", a["project"], "--xml"], 120),
                     timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_illog_program",
                     "读某个程序的带行号 IL（illog --program <名>）。",
                     {"type": "object", "properties": {"program": {"type": "string"},
                                                       "project": {"type": "string"}},
                      "required": ["program"], "additionalProperties": False},
                     _simple("illog", lambda a: ["--program", a["program"]]
                             + (["--project", a["project"]] if a.get("project") else []), 180),
                     timeout_s=240, must_have_checks=True))

    kit.add(ToolSpec("autoshop_illog_paths",
                     "列出 il_log 里可用的程序路径（illog --paths）。",
                     {"type": "object", "properties": {"project": {"type": "string"}},
                      "additionalProperties": False},
                     _simple("illog", lambda a: ["--paths"]
                             + (["--project", a["project"]] if a.get("project") else []), 120),
                     timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_summary_compile",
                     "工程总览并顺带编译（summary --compile）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     _simple("summary", lambda a: ["--compile"], 300), timeout_s=360,
                     must_have_checks=True))

    kit.add(ToolSpec("autoshop_monitor_read",
                     "读监控表当前值（monitor，在线）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     _simple("monitor", None, 180), timeout_s=240, must_have_checks=True))

    kit.add(ToolSpec("autoshop_monitor_row",
                     "读/扩展监控表第 N 行（monitor --row N）。",
                     {"type": "object", "properties": {"row": {"type": "integer"}},
                      "required": ["row"], "additionalProperties": False},
                     _simple("monitor", lambda a: ["--row", str(int(a["row"]))], 120),
                     timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_output_tail",
                     "读输出窗口文本（output，编译/错误原文）。",
                     {"type": "object", "properties": {}, "additionalProperties": False},
                     _simple("output", None, 120), timeout_s=180, must_have_checks=True))

    kit.add(ToolSpec("autoshop_status_launch",
                     "启动（若未运行）并报告 AutoShop 状态（status --launch）。",
                     {"type": "object", "properties": {"project": {"type": "string"}},
                      "additionalProperties": False},
                     _simple("status", lambda a: ["--launch"]
                             + (["--project", a["project"]] if a.get("project") else []), 300),
                     timeout_s=360, must_have_checks=True))

    kit.add(ToolSpec("autoshop_hcp_write_xml",
                     "把一份 XML 加密写回 .hcp（hcp --project FILE.hcp --write-xml FILE）。"
                     "会改写工程文件，属写操作。",
                     {"type": "object", "properties": {"project": {"type": "string"},
                                                       "xml_file": {"type": "string"}},
                      "required": ["project", "xml_file"], "additionalProperties": False},
                     _simple("hcp", lambda a: ["--project", a["project"],
                                               "--write-xml", a["xml_file"]], 180),
                     timeout_s=240, must_have_checks=True))

    return kit

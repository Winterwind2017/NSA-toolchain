"""swkit 的"脚本类"工具：把 mcp-patches 里的能力直接并进 kit-sw。

为什么不再挂一个 sw-extra MCP：
  swkit 的 MCP 面（145 个工具）覆盖了建模/装配/出图/钣金/导出，
  但不含**分步 FEA**、Motion 列表、批量扫描和 DocumentMgr 索引查询——
  这些能力本来就在 `D:\\bililive\\mcp-patches\\*.py` 里，只是没被 MCP 化。
  并入 kit-sw 后：一个服务器、一套判据、不重名。

判据说明：这里都是**结构性判据**（退出码 + 关键读数），不是几何判据。
能解析到真实读数的（加载项自检、索引统计）就按读数判，解析不到就只判"跑通了"。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid

from ..tools import ToolSpec, apply_checks, normalize
from .. import paths

KIT_KEY = "sw"
PATCH_DIR = os.environ.get("SW_PATCH_DIR") or str(paths.repo_path("mcp-patches"))
PATCH_PY = os.environ.get("SW_PATCH_PYTHON") or paths.python_exe()
RUNS = paths.runs_dir()
MAX_OUT = 20000


def _python() -> str:
    return PATCH_PY if os.path.isfile(PATCH_PY) else sys.executable


def _run_script(script: str, argv: list, timeout: float) -> dict:
    """跑一个 mcp-patches 脚本。

    沿用 sw-extra 的实测约定：输出重定向到**文件**而不是管道（沙箱下管道会挂死），
    stdin=DEVNULL，CREATE_NO_WINDOW 避免弹黑框。
    """
    path = os.path.join(PATCH_DIR, script)
    if not os.path.isfile(path):
        return {"ok": False, "rc": None, "text": "", "seconds": 0.0,
                "errors": ["找不到脚本：%s" % path]}

    logdir = os.path.join(RUNS, "sw")
    os.makedirs(logdir, exist_ok=True)
    tag = "%s_%s" % (os.path.splitext(script)[0], uuid.uuid4().hex[:8])
    out_f = os.path.join(logdir, tag + ".out")
    err_f = os.path.join(logdir, tag + ".err")

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [_python(), "-u", path] + [str(a) for a in argv]
    started = time.time()
    # 用 Popen + 轮询代替 subprocess.run：这样**取消**才能真的杀掉子进程
    # （FEA 求解/大目录扫描动辄几分钟，不能让客户端只能等）。
    try:
        from ..tools import is_cancelled
    except Exception:                                  # noqa: BLE001
        def is_cancelled() -> bool:
            return False
    try:
        with open(out_f, "w", encoding="utf-8", errors="replace") as fo, \
                open(err_f, "w", encoding="utf-8", errors="replace") as fe:
            proc = subprocess.Popen(
                cmd, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            rc = None
            while True:
                try:
                    rc = proc.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    if is_cancelled():
                        proc.kill()
                        try:
                            proc.wait(timeout=5)
                        except Exception:              # noqa: BLE001
                            pass
                        return {"ok": False, "rc": None, "text": "",
                                "seconds": time.time() - started,
                                "errors": ["已取消（客户端取消请求）"],
                                "cancelled": True}
                    if time.time() - started > timeout:
                        proc.kill()
                        try:
                            proc.wait(timeout=5)
                        except Exception:              # noqa: BLE001
                            pass
                        return {"ok": False, "rc": None, "text": "",
                                "seconds": time.time() - started,
                                "errors": ["超时（>%.0fs）" % timeout]}
        errors = []
    except Exception as exc:                          # noqa: BLE001
        return {"ok": False, "rc": None, "text": "", "seconds": time.time() - started,
                "errors": ["启动失败：%s" % exc]}
    except Exception as exc:                          # noqa: BLE001
        return {"ok": False, "rc": None, "text": "", "seconds": time.time() - started,
                "errors": ["启动失败：%s" % exc]}

    parts = []
    for path_i, is_err in ((out_f, False), (err_f, True)):
        try:
            with open(path_i, encoding="utf-8", errors="replace") as fh:
                body = fh.read().strip()
        except OSError:
            body = ""
        if body:
            parts.append(("[stderr]\n" if is_err else "") + body)
    text = "\n".join(parts)
    if len(text) > MAX_OUT:
        text = text[:MAX_OUT] + "\n…（截断）"

    return {"ok": rc == 0, "rc": rc, "text": text,
            "seconds": time.time() - started,
            "errors": [] if rc == 0 else ["退出码 %s：%s" % (rc, text[-300:] or "-")]}


def _parse_json(text: str):
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


def _check(name, got, want, ok, note=""):
    item = {"check": name, "got": got, "want": want, "ok": bool(ok)}
    if note:
        item["note"] = note
    return item


def _judge(kind: str, run: dict, verb: str) -> dict:
    text = run.get("text") or ""
    rc = run.get("rc")
    checks = [_check("exit_code", rc, 0, rc == 0)]

    if kind == "addin":
        data = _parse_json(text) or {}
        if data:
            checks.append(_check("sim_dll_exists", data.get("exists"), True,
                                 bool(data.get("exists"))))
            load_addin = data.get("load_addin")
            got = bool(data.get("get_addin_object"))
            if isinstance(load_addin, int) and load_addin >= 0:
                # 加载项真被载入时才把 addin_object 当判据
                checks.append(_check("addin_object", got, True, got))
            else:
                # SolidWorks 没运行时 load_addin=-1、必然拿不到 AddIn 对象，
                # 这时只记录不判负，否则等于把"没开 SW"当成"Simulation 坏了"
                checks.append(_check("addin_object", got, True, True,
                                     "informational：load_addin=%s，需 SolidWorks "
                                     "正在运行才判负" % load_addin))
    elif kind == "swdm_stats":
        files = re.search(r"文件数\s*=\s*(\d+)", text)
        okfiles = re.search(r"成功\s*=\s*(\d+)", text)
        comps = re.search(r"组件行?\s*=\s*(\d+)", text)
        if files and okfiles:
            f, o = int(files.group(1)), int(okfiles.group(1))
            checks.append(_check("files_indexed", o, f, o == f))
        if comps:
            n = int(comps.group(1))
            checks.append(_check("components", n, ">0", n > 0))
    elif kind == "swdm_query":
        checks.append(_check("output_present", bool(text.strip()), True,
                             bool(text.strip())))
    elif kind == "sim_faces":
        m = re.search(r"(\d+)\s*个面", text)
        if m:
            n = int(m.group(1))
            checks.append(_check("face_count", n, ">0", n > 0))
        else:
            checks.append(_check("output_present", bool(text.strip()), True,
                                 bool(text.strip())))
    elif kind == "sim_mesh":
        elems = re.search(r"单元=(\d+)", text)
        nodes = re.search(r"节点=(\d+)", text) or re.search(r"节点\s*[:=]?\s*(\d+)", text)
        size = re.search(r"ElementSize=([\d.]+) mm", text)
        failed = re.search(r"失败=(\d+)", text)
        if elems:
            n = int(elems.group(1))
            checks.append(_check("elements", n, "10..2000000", 10 <= n <= 2_000_000))
        else:
            checks.append(_check("mesh_reported", bool(text.strip()), True,
                                 bool(text.strip())))
        if nodes:
            checks.append(_check("nodes", int(nodes.group(1)), ">0", int(nodes.group(1)) > 0))
        if size:
            mm = float(size.group(1))
            checks.append(_check("element_size_mm", mm, ">0", mm > 0))
        if failed:
            checks.append(_check("mesh_failed", int(failed.group(1)), 0,
                                 int(failed.group(1)) == 0))
    elif kind == "sim_run":
        done = ("完成" in text) or ("求解" in text and "失败" not in text)
        checks.append(_check("solve_reported", done, True, done))
        # 2026-11-03：求解返回 0 不等于有结果（网格 2134 万单元时返回 0 但 Results 为空）
        ready = "结果已就绪" in text
        checks.append(_check("results_ready", ready, True, ready,
                             "" if ready else "求解返回 0 但没有结果（多半网格过大，调大 size 重划）"))
    elif kind == "scan":
        data = _parse_json(text)
        if isinstance(data, dict):
            items = data.get("files") or data.get("items") or []
            if isinstance(items, list):
                checks.append(_check("files_scanned", len(items), ">=0", True))
    elif kind.startswith("hub_"):
        data = _parse_json(text) or {}
        spec = HUB_EXPECT.get(kind, {})
        if not data and spec:
            checks.append(_check("result_json", False, True, False,
                                 "脚本没有输出 RESULT 行"))
        for name, rule in spec.items():
            got = data.get(name)
            if rule == "skip_none":
                # 有值就记成 informational（不判负），没值直接不记
                if got is not None:
                    checks.append(_check(name, got, "参考读数", True))
                continue
            if isinstance(rule, str) and rule.startswith(">="):
                want = float(rule[2:])
                ok = got is not None and float(got) >= want
            elif isinstance(rule, str) and rule.startswith(">"):
                want = float(rule[1:])
                ok = got is not None and float(got) > want
            elif isinstance(rule, str) and rule.startswith("=="):
                want = float(rule[2:])
                ok = got is not None and abs(float(got) - want) < 1e-6
            else:
                want = rule
                ok = (got == rule)
            checks.append(_check(name, got, want, ok))
    else:
        checks.append(_check("output_present", bool(text.strip()), True,
                             bool(text.strip())))

    return {"checks": checks}


# 重活按 kind 自动幂等：重试代价高（求解 13 分钟 / 划网格吃 15GB / 扫大目录）
IDEMPOTENT_KINDS = {"sim_setup", "sim_mesh", "sim_run", "scan"}


def _tool(name: str, description: str, schema: dict, script: str, kind: str,
          build_argv, timeout: float, idempotent: bool | None = None,
          must_have_checks: bool = True) -> ToolSpec:
    if idempotent is None:
        idempotent = kind in IDEMPOTENT_KINDS
    if idempotent:
        props = dict(schema.get("properties") or {})
        props["request_id"] = {"type": "string",
                               "description": "幂等键：同 id 重试直接回放上次结果"}
        schema = {**schema, "properties": props}

    def handler(args: dict) -> dict:
        argv = build_argv(args or {})
        run = _run_script(script, argv, timeout)
        judged = _judge(kind, run, argv[0] if argv else "")
        payload = normalize(KIT_KEY, name, ok=run["ok"],
                            reads={"script": script, "argv": argv,
                                   "returncode": run["rc"],
                                   "output": run["text"][:6000]},
                            errors=run["errors"], seconds=run["seconds"])
        return apply_checks(payload, judged["checks"])
    return ToolSpec(name, description, schema, handler, timeout_s=timeout + 60,
                    idempotent=idempotent, must_have_checks=must_have_checks)




# ── P5：hub 语义增强的判据表（值：期望值 / ">0" / ">=1" / "==0" / "skip_none"）──
HUB_EXPECT = {
    "hub_docs": {"doc_count": ">=1", "dirty_count": "skip_none", "active_present": True},
    "hub_activate": {"activated": True},
    "hub_bbox": {"bodies": ">=1", "dx_mm": ">0", "dy_mm": ">0", "dz_mm": ">0"},
    "hub_rebuild": {"rebuild_ok": True, "feature_count": ">0", "failed_count": "skip_none"},
    "hub_inspect": {"type": ">=1", "feature_count": ">0"},
    # 零件没有组件/配合，只有装配体才有；这里只要求"类型有效 + 配合数可读"，
    # 组件数作为 informational（不然零件一律判负）。
    "hub_relations": {"type": ">=1", "component_count": "skip_none", "mate_count": ">=0"},
    "hub_setprops": {"written": ">=1", "readback_ok": True},
    "hub_config": {"created": True, "config_count": ">=1"},
    "hub_material": {"assigned": True, "material_chars": ">0"},
    # 运行时自检：只要脚本确实给出结构化结果就算过；"SW 有没有开"是信息项，
    # 不判负——状态工具在 SW 关着的时候也应该能回答。
    "hub_reload": {"reported": True, "attached": True, "doc_count": "skip_none",
                   "revision": "skip_none"},
    "hub_status": {"reported": True, "attached": "skip_none", "doc_count": "skip_none"},
}

S = {"type": "string"}
I = {"type": "integer"}
N = {"type": "number"}
B = {"type": "boolean"}


def script_tools() -> list:
    """返回并入 kit-sw 的脚本类工具（分步 FEA / Motion / 扫描 / 索引）。"""
    tools = []

    def open_args(a: dict) -> list:
        return ["--open", a["open_path"]] if a.get("open_path") else []

    tools.append(_tool(
        "sw_sim_faces",
        "列出零件面（索引/中心 mm/尺寸 mm），用于挑约束面与受力面。",
        {"type": "object",
         "properties": {"open_path": S, "limit": I},
         "additionalProperties": False},
        "sw_sim.py", "sim_faces",
        lambda a: ["faces", "--limit", int(a.get("limit") or 20)] + open_args(a),
        300))

    tools.append(_tool(
        "sw_sim_list",
        "列出所有仿真研究及其结果状态（有/无、步数）。",
        {"type": "object", "properties": {"open_path": S},
         "additionalProperties": False},
        "sw_sim.py", "list", lambda a: ["list"] + open_args(a), 300))

    tools.append(_tool(
        "sw_sim_setup",
        "建静力研究 + 固定约束 + 法向力（可同时划网格）。分步 FEA 第一步。",
        {"type": "object",
         "properties": {"restraint_face": I, "force_face": I, "force_n": N,
                        "material": S, "open_path": S, "mesh": B,
                        "size": N, "tol": N},
         "additionalProperties": False},
        "sw_sim.py", "sim_setup",
        lambda a: ["setup",
                   "--restraint-face", int(a.get("restraint_face") or 0),
                   "--force-face", int(a.get("force_face") or 1),
                   "--force", float(a.get("force_n") or 100.0),
                   "--size", float(a.get("size") or 0.02),
                   "--tol", float(a.get("tol") or 0.002)]
                  + (["--material", a["material"]] if a.get("material") else [])
                  + ([] if a.get("mesh", True) else ["--no-mesh"])
                  + open_args(a),
        1800))

    tools.append(_tool(
        "sw_sim_mesh",
        "只划网格。size/tol 以**米**为单位；内部按实测的 ×100 换算成 API 值，"
        "并按单元数（上限 200 万）拦截过大网格。",
        {"type": "object",
         "properties": {"open_path": S, "study": S, "size": N, "tol": N},
         "additionalProperties": False},
        "sw_sim.py", "sim_mesh",
        lambda a: ["mesh", "--size", float(a.get("size") or 0.02),
                   "--tol", float(a.get("tol") or 0.002)]
                  + (["--study", a["study"]] if a.get("study") else [])
                  + open_args(a),
        1800))

    tools.append(_tool(
        "sw_sim_run",
        "只求解（不建研究、不划网格）。40 mm 级零件约 11–13 分钟，star.exe 峰值约 15 GB。",
        {"type": "object",
         "properties": {"open_path": S, "study": S, "timeout_s": I},
         "additionalProperties": False},
        "sw_sim.py", "sim_run",
        lambda a: ["run"] + (["--study", a["study"]] if a.get("study") else [])
                  + open_args(a),
        3600))

    tools.append(_tool(
        "sw_sim_addin_check",
        "Simulation 加载项自检（不打开文档）：cosworks.dll 是否存在、能否拿到 AddIn 对象。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "sw_adv.py", "addin", lambda a: ["sim", "status"], 300))

    tools.append(_tool(
        "sw_motion_list",
        "列出 Motion 算例、马达与结果集可用性。",
        {"type": "object", "properties": {"open_path": S},
         "additionalProperties": False},
        "sw_motion.py", "motion_list", lambda a: ["list"] + open_args(a), 600))

    tools.append(_tool(
        "sw_scan",
        "一个会话批量只读扫描目录：逐个打开、读配置与自定义属性，输出 JSON。",
        {"type": "object", "required": ["dir_path"],
         "properties": {"dir_path": S, "pattern": S, "out": S,
                        "verbose": B, "timeout_s": I},
         "additionalProperties": False},
        "sw_adv.py", "scan",
        lambda a: ["scan", a["dir_path"]]
                  + (["--pattern", str(a["pattern"]).replace("*", "").replace("?", "")
                      .lstrip(".")] if a.get("pattern") else [])
                  + (["--out", a["out"]] if a.get("out") else [])
                  + (["--verbose"] if a.get("verbose") else []),
        3600))

    tools.append(_tool(
        "swdm_query",
        "按属性/目录/扩展名查私有 DocumentMgr 索引（275 文件 / 2684 组件）。"
        "prop 写成 `名=值`（子串匹配）；不带任何条件时等价于 stats。",
        {"type": "object",
         "properties": {"prop": S, "dir": S, "ext": S, "limit": I, "print_rows": I},
         "additionalProperties": False},
        "swdm_lite.py", "swdm_query",
        lambda a: (["query"]
                   + (["--prop", a["prop"]] if a.get("prop") else [])
                   + (["--dir", a["dir"]] if a.get("dir") else [])
                   + (["--ext", a["ext"]] if a.get("ext") else [])
                   + (["--limit", int(a["limit"])] if a.get("limit") else [])
                   + (["--print", int(a["print_rows"])] if a.get("print_rows") else [])
                   if any(a.get(k) for k in ("prop", "dir", "ext", "limit")) else ["stats"]),
        300))

    tools.append(_tool(
        "swdm_stats",
        "DocumentMgr 索引统计：文件数/成功数/扩展名分布/组件数。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "swdm_lite.py", "swdm_stats", lambda a: ["stats"], 300))


    # ── P5：hub 语义增强 9 个（脚本 mcp-patches/sw_hub_ext.py）────────────
    tools.append(_tool(
        "sw_reload_runtime",
        "重新建立与 SolidWorks 的 COM 连接（SW 重启/崩溃后旧引用失效时用），"
        "返回附着状态、文档数、版本号。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "sw_hub_ext.py", "hub_reload", lambda a: ["reload_runtime"], 120))

    tools.append(_tool(
        "sw_operation_status",
        "运行时状态：COM 是否连得上、打开文档数/脏文档数、版本号；"
        "连不上也返回结构化结果（不判负），用于排查\"服务器还挂着旧会话\"。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "sw_hub_ext.py", "hub_status", lambda a: ["status"], 120))

    tools.append(_tool(
        "sw_list_documents_dirty",
        "列出打开的文档 + 是否有未保存修改（dirty），并标出当前活动文档。"
        "比 sw_list_open_documents 多 dirty/active 两个判据源。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "sw_hub_ext.py", "hub_docs", lambda a: ["docs"], 120))

    tools.append(_tool(
        "sw_activate_document",
        "按标题激活已打开的文档（多文档切换）。",
        {"type": "object", "properties": {"title": S}, "required": ["title"],
         "additionalProperties": False},
        "sw_hub_ext.py", "hub_activate",
        lambda a: ["activate", "--title", a["title"]], 120))

    tools.append(_tool(
        "sw_bounding_box_with_hidden",
        "包围盒（mm），include_hidden=true 时把隐藏/抑制的也算进去（装配量外形用）。",
        {"type": "object", "properties": {"include_hidden": B},
         "additionalProperties": False},
        "sw_hub_ext.py", "hub_bbox",
        lambda a: ["bbox"] + (["--include-hidden"] if a.get("include_hidden") else []),
        180))

    tools.append(_tool(
        "sw_rebuild_diagnostics",
        "重建并给诊断：是否成功、特征总数、失败特征（需要早绑定才有逐条错误码，"
        "拿不到时 failed_count=null 而不是 0）。",
        {"type": "object", "properties": {"full": B}, "additionalProperties": False},
        "sw_hub_ext.py", "hub_rebuild",
        lambda a: ["rebuild"] + (["--full"] if a.get("full") else []), 300))

    tools.append(_tool(
        "sw_inspect_active",
        "当前文档自审查：类型/是否脏/特征数/错误与警告数/配置可用性。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "sw_hub_ext.py", "hub_inspect", lambda a: ["inspect_active"], 120))

    tools.append(_tool(
        "sw_inspect_relations",
        "装配关系自审查：组件数、配合数、路径为空的悬空组件。",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "sw_hub_ext.py", "hub_relations", lambda a: ["inspect_relations"], 180))

    tools.append(_tool(
        "sw_set_custom_properties",
        "批量写自定义属性并逐条读回（数字自动用数值类型）。props 形如 {\"料号\": \"A-01\", \"重量\": 2.5}。",
        {"type": "object", "properties": {"props": {"type": "object"},
                                          "config": S},
         "required": ["props"], "additionalProperties": False},
        "sw_hub_ext.py", "hub_setprops",
        lambda a: ["set_props", "--json", json.dumps(a.get("props") or {}, ensure_ascii=False)]
                  + (["--config", a["config"]] if a.get("config") else []),
        180))

    tools.append(_tool(
        "sw_create_configuration_full",
        "新增配置（可带备注/派生/直接激活），比 sw_add_configuration 参数更全。",
        {"type": "object", "properties": {"name": S, "comment": S,
                                          "alternate": S, "activate": B},
         "required": ["name"], "additionalProperties": False},
        "sw_hub_ext.py", "hub_config",
        lambda a: ["create_config", "--name", a["name"]]
                  + (["--comment", a["comment"]] if a.get("comment") else [])
                  + (["--alternate", a["alternate"]] if a.get("alternate") else [])
                  + (["--activate"] if a.get("activate") else []),
        180))

    tools.append(_tool(
        "sw_assign_material_full",
        "赋材料并可指定材料库/配置/是否重建，然后读回材料名（读回才是判据）。",
        {"type": "object", "properties": {"name": S, "db": S, "config": S,
                                          "rebuild": B},
         "required": ["name"], "additionalProperties": False},
        "sw_hub_ext.py", "hub_material",
        lambda a: ["assign_material", "--name", a["name"]]
                  + (["--db", a["db"]] if a.get("db") else [])
                  + (["--config", a["config"]] if a.get("config") else [])
                  + (["--rebuild"] if a.get("rebuild") else []),
        300))

    return tools

"""验收用例：SolidWorks / NX / AutoCAD 三家各一组。

SolidWorks 的用例跑在**临时副本**上（`NSA_MCP_HUB_SW_FIXTURE` 可覆盖默认夹具），
NX / AutoCAD 的用例走各自 kit 的 `*_run_capability`，本来就自带几何判据。
"""

from __future__ import annotations

import glob
import os
import shutil
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SW_FIXTURE = os.environ.get(
    "NSA_MCP_HUB_SW_FIXTURE", r"C:\Users\yuche\Desktop\450隔音罩1-B2.SLDPRT")


# ----------------------------------------------------------------- SolidWorks
def _sw_attach():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.Dispatch("SldWorks.Application")


def _sw_title(model) -> str:
    value = model.GetTitle
    return value if isinstance(value, str) else value()


def _solidworks_running() -> bool:
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/NH"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
        return "SLDWORKS.exe" in (out.stdout or "")
    except Exception:                              # noqa: BLE001
        return False


def sw_setup() -> dict:
    if not os.path.isfile(SW_FIXTURE):
        print("  [warn] 找不到 SolidWorks 夹具：%s" % SW_FIXTURE, flush=True)
        return {"available": False}
    # 绝不为跑验收去“启动”SolidWorks——没开就跳过，避免制造副作用
    if not _solidworks_running():
        print("  [warn] SolidWorks 没在运行，SolidWorks 组跳过（本套件不会替你启动它）",
              flush=True)
        return {"available": False}
    workdir = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_")
    copy_path = os.path.join(workdir, os.path.basename(SW_FIXTURE))
    shutil.copy2(SW_FIXTURE, copy_path)
    try:
        from win32com.client import VARIANT
        import pythoncom
        app = _sw_attach()
        err = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warn = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        model = app.OpenDoc6(copy_path, 1, 1, "", err, warn)   # 1 = Silent
        if model is None:
            raise RuntimeError("打开夹具失败（err=%s）" % err.value)
        return {"available": True, "workdir": workdir,
                "copy": copy_path, "title": _sw_title(model)}
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise


def sw_teardown(context: dict) -> None:
    if not context.get("available"):
        return
    try:
        app = _sw_attach()
        for _ in range(10):
            if int(app.GetDocumentCount) == 0:
                break
            docs = app.GetDocuments
            docs = docs() if callable(docs) else docs
            model = docs[0]
            app.CloseDoc(_sw_title(model))       # 不保存：都是副本
    except Exception as exc:                      # noqa: BLE001
        print("  [warn] 关闭文档失败：%s" % exc, flush=True)
    shutil.rmtree(context["workdir"], ignore_errors=True)


def _no_fixture(context: dict) -> bool:
    return not context.get("available")


def _select_args(client):
    """先 inspect 拿 2 个持久引用 token，再拿去选面。"""
    payload = client.call("sw_feature_inspect",
                          {"include_topology": True, "include_tokens": True, "limit": 6})
    topo = ((payload.get("reads") or {}).get("result") or {}).get("topology") or []
    tokens = [t["reference_token"] for t in topo if t.get("reference_token")][:2]
    return {"tokens": tokens}


_FEA_BLOCK = {"version": "1.0", "metadata": {"part_type": "block"}, "features": [
    {"name": "Part", "kind": "new_part", "title": "FEA accept block"},
    {"name": "S1", "kind": "sketch", "plane": "Front Plane",
     "entities": [{"kind": "polyline", "closed": True,
                   "points": [[-50, -25], [50, -25], [50, 25], [-50, 25]]}]},
    {"name": "B1", "kind": "boss_extrude", "sketch": "S1", "depth_mm": 10,
     "merge": False}]}


def _fea_prepare(client):
    """为 FEA 用例铺路：建 100×50×10 方块 → 设材质/约束/力 → 划 20 mm 网格。

    判据链：RunAnalysis=0 且 study.Results 非空（脚本自己校验），
    所以这里任何一步失败都直接抛错，不把"跑过了"当成"有结果"。
    """
    for step, tool, args in (
            ("建块", "sw_execute_feature_graph", {"feature_graph": _FEA_BLOCK}),
            ("setup", "sw_sim_setup", {"restraint_face": 4, "force_face": 5,
                                       "force_n": 100, "material": "AISI 304",
                                       "mesh": False}),
            ("mesh", "sw_sim_mesh", {"size": 0.02, "tol": 0.002})):
        r = client.call(tool, args)
        if not r.get("ok"):
            raise RuntimeError("%s 失败：%s" % (step, (r.get("errors") or ["-"])[0]))
    return {}


SW_CASES = [
    {"id": "sw.inspect.topology", "tool": "sw_feature_inspect",
     "title": "列出特征树 + 拓扑 + token",
     "args": {"include_topology": True, "include_tokens": True, "limit": 20},
     "expect_check_true": ["features_listed", "all_features_named"],
     "skip_if": _no_fixture},

    {"id": "sw.param.thickness", "tool": "sw_set_feature_parameter",
     "title": "板厚 5→8mm，体积应 ×1.6",
     "args": {"feature": "凸台-拉伸1", "parameter": "D1", "value": 8.0,
              "confirm": True},
     "expect_checks": {"value_readback_m": 0.008, "geometry_delta": True},
     "expect_ratio": {"reads.geometry_after.volume_mm3 / reads.geometry_before.volume_mm3": 1.6},
     "skip_if": _no_fixture},

    {"id": "sw.param.fillet", "tool": "sw_set_feature_parameter",
     "title": "圆角 5→3mm，体积微增",
     "args": {"feature": "圆角1", "parameter": "D1", "value": 3.0, "confirm": True},
     "expect_checks": {"value_readback_m": 0.003},
     "expect_check_true": ["applied"],
     "skip_if": _no_fixture},

    {"id": "sw.rollback.before", "tool": "sw_feature_rollback",
     "title": "回滚棒移到 凸台-拉伸1 之前",
     "args": {"location": "before", "feature": "凸台-拉伸1"},
     "expect_checks": {"moved": True}, "skip_if": _no_fixture},

    {"id": "sw.rollback.end", "tool": "sw_feature_rollback",
     "title": "回滚棒归位到 end",
     "args": {"location": "end"},
     "expect_checks": {"moved": True}, "skip_if": _no_fixture},

    {"id": "sw.select.faces", "tool": "sw_select_references",
     "title": "用 2 个 token 选面",
     "prepare": _select_args,
     "expect_check_true": ["tokens_resolved", "selected_count"],
     "skip_if": _no_fixture},

    {"id": "sw.sphere.plan", "tool": "sw_sphere_plan",
     "title": "球体图生成器（上游 create_sphere 的图）：3 个特征 + 体积 4/3·π·r³",
     "args": {"diameter_mm": 40.0},
     "expect_ok": True,
     "expect_reads": {"reads.feature_count": 3},
     "expect_check_true": ["feature_count", "volume_formula"],
     "expect_min_checks": 2,
     # 纯计算（不碰 COM）：SolidWorks 没开也要跑
     "no_setup": True,
     "timeout_s": 180},

    {"id": "sw.graph.block", "tool": "sw_execute_feature_graph",
     "title": "Feature Graph 建块 100×60×20 → 体积 120000",
     "args": {"feature_graph": {"version": "1.0", "metadata": {"part_type": "block"},
                                "features": [
                                    {"name": "Part", "kind": "new_part", "title": "acceptance block"},
                                    {"name": "BlockSketch", "kind": "sketch", "plane": "Front Plane",
                                     "entities": [{"kind": "polyline", "closed": True,
                                                   "points": [[-50, -30], [50, -30], [50, 30], [-50, 30]]}]},
                                    {"name": "BlockBoss", "kind": "boss_extrude",
                                     "sketch": "BlockSketch", "depth_mm": 20, "merge": False}]},
              "expected_volume_mm3": 120000},
     "expect_check_true": ["steps_ok", "volume_matches_expected"],
     "expect_reads": {"reads.body_volume_mm3": 120000},
     "skip_if": _no_fixture},

    {"id": "sw.index.stats", "tool": "swdm_stats",
     "title": "DocumentMgr 索引统计（环境项）",
     "args": {},
     "expect_check_true": ["files_indexed"]},

    {"id": "sw.index.query", "tool": "swdm_query",
     "title": "按扩展名查索引（取 3 条 .sldprt）",
     "args": {"ext": ".sldprt", "limit": 3},
     "expect_check_true": ["output_present"]},

    {"id": "sw.sim.addin", "tool": "sw_sim_addin_check",
     "title": "Simulation 加载项自检（cosworks.dll）",
     "args": {},
     "expect_check_true": ["sim_dll_exists"]},

    # 放在最后：它会新建一个方块文档并留下研究，避免影响前面的用例
    {"id": "sw.fea.solve", "tool": "sw_sim_run",
     "title": "小方块三段式 FEA：20 mm 网格 → 求解 → Results 非空",
     "prepare": _fea_prepare,
     "expect_check_true": ["solve_reported", "results_ready"],
     "timeout_s": 600},

    # ── P5 hub 语义增强的验收（真机，需 SolidWorks 有活动文档）──────────
    {"id": "sw.hub.docs", "tool": "sw_list_documents_dirty",
     "title": "列出文档 + dirty 状态（hub 增强）",
     "args": {}, "expect_check_true": ["doc_count", "active_present"],
     "skip_if": _no_fixture},

    {"id": "sw.hub.inspect", "tool": "sw_inspect_active",
     "title": "当前文档自审查（类型/特征数）",
     "args": {}, "expect_check_true": ["type", "feature_count"],
     "skip_if": _no_fixture},

    {"id": "sw.hub.bbox", "tool": "sw_bounding_box_with_hidden",
     "title": "包围盒（mm，三个方向都 >0）",
     "args": {"include_hidden": False},
     "expect_check_true": ["bodies", "dx_mm", "dy_mm", "dz_mm"],
     "skip_if": _no_fixture},

    {"id": "sw.export.step", "tool": "sw_export_step",
     "title": "导出 STEP（判据：文件头 ISO-10303-21）",
     "args": lambda ctx: {"path": os.path.join(tempfile.gettempdir(),
                                               "nsa_mcp_hub_accept_450.step")},
     "expect_ok": True,
     "skip_if": _no_fixture},
]


# ------------------------------------------------------------------------ NX
NX_CASES = [
    {"id": "nx.status", "tool": "nx_status",
     "title": "NX 环境（run_journal 路径 + 能力数）",
     "args": {},
     "expect_reads": {"reads.cap_count": 146}},

    {"id": "nx.block", "tool": "nx_run_capability",
     "title": "真机建块 100×50×20 → 体积 100000",
     "args": {"ids": ["block.create"]},
     "expect_check_true": ["volume_mm3", "faces", "edges"],
     "expect_min_checks": 3},
]


# ------------------------------------------------------------------------ GX
GX_CASES = [
    {"id": "gx.paste_st", "tool": "gx_run_capability",
     "title": "把 ST 粘进程序并转换（判据：步数 2-200）",
     "args": {"ids": ["program.paste_st"], "keep": True},
     "expect_check_true": ["steps"],
     "expect_min_checks": 1},

    {"id": "gx.convert_all", "tool": "gx_run_capability",
     "title": "全部转换（判据：errors=0 / warnings=0 / stages≥3）",
     "args": {"ids": ["build.convert_all"], "keep": True},
     "expect_checks": {"errors": 0, "warnings": 0},
     "expect_min_checks": 2},
]


# ------------------------------------------------------------------- AutoCAD
ACAD_CASE_TIMEOUT = 120.0


def _acad_com():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.GetActiveObject("AutoCAD.Application")


def acad_setup() -> dict:
    """验收前把 ATTDIA 关掉。

    实测：`block.insert_with_attributes` 在 ATTDIA=1 时会**卡住不返回**（属性输入对话框
    在等用户点确定）；ATTDIA=0 后 7.9 s 全绿。跑完恢复原值。
    """
    try:
        app = _acad_com()
        # AutoCAD 停在开始页时一个文档都没有，ActiveDocument 会抛
        # "无法获取 Document 对象"；那会把整组误判成环境不可用。
        if int(app.Documents.Count) == 0:
            app.Documents.Add()
        doc = app.ActiveDocument
        saved = {"ATTDIA": doc.GetVariable("ATTDIA"),
                 "FILEDIA": doc.GetVariable("FILEDIA")}
        doc.SetVariable("ATTDIA", 0)
        # FILEDIA=1 时，任何"需要文件名"的动作（Save/SaveAs/打开文件）都会弹模态框，
        # COM 随即一直等到用户点确定 —— 这正是 projection 被误判成"卡 120 s"的来源。
        doc.SetVariable("FILEDIA", 0)
        return {"available": True, "saved": saved}
    except Exception as exc:                       # noqa: BLE001
        print("  [warn] AutoCAD 未就绪（%s），acad 组跳过" % str(exc)[:80], flush=True)
        return {"available": False}


def acad_between(context: dict) -> None:
    """每条用例之间存一次盘，消掉 close 时的"是否保存"提示。"""
    if not context.get("available"):
        return
    try:
        doc = _acad_com().ActiveDocument
        if doc.Saved:
            return
        # 没有 FullName 的图纸（新建未存盘）调 Save() 会走"另存为"，FILEDIA=1 时弹框卡死。
        if not (getattr(doc, "FullName", "") or "").strip():
            return
        doc.Save()
    except Exception:                              # noqa: BLE001
        pass


def acad_teardown(context: dict) -> None:
    if not context.get("available"):
        return
    try:
        app = _acad_com()
        doc = app.ActiveDocument
        # 先恢复原值（含 FILEDIA），再兜底把我调试期改过的一项恢复默认
        for key, value in (context.get("saved") or {}).items():
            doc.SetVariable(key, value)
        doc.SetVariable("CMDECHO", 1)
    except Exception as exc:                       # noqa: BLE001
        print("  [warn] 恢复 AutoCAD 变量失败：%s" % exc, flush=True)


def _acad_missing(context: dict) -> bool:
    return not context.get("available")

ACAD_CASES = [
    {"id": "acad.caps", "timeout_s": ACAD_CASE_TIMEOUT, "tool": "acad_list_caps",
     "title": "几何族能力清单",
     "args": {"family": "geom"},
     "expect_reads": {"reads.total": 8}},

    # 放在最前面：这条要 insert + 读属性，图纸越"脏"越容易碰到保存/属性提示
    {"id": "acad.block.insert", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "块插入 + 属性值读回",
     "args": {"ids": ["block.insert_with_attributes"]},
     "expect_check_true": ["count", "attr_values", "reopen"]},

    {"id": "acad.block.define", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "块定义 + 属性定义",
     "args": {"ids": ["block.define"]},
     "expect_check_true": ["new_block", "attdef_count"]},

    {"id": "acad.line", "timeout_s": ACAD_CASE_TIMEOUT, "tool": "acad_run_capability",
     "title": "真机画 60mm 线 → 长度/重开判据",
     "args": {"ids": ["geom.line"]},
     "expect_check_true": ["length", "count"],
     "expect_min_checks": 5},

    {"id": "acad.circle", "timeout_s": ACAD_CASE_TIMEOUT, "tool": "acad_run_capability",
     "title": "画 R25 圆 → 半径/面积=πR²/重开",
     "args": {"ids": ["geom.circle"]},
     "expect_check_true": ["count", "type", "geometry", "area", "reopen"],
     "expect_reads": {"reads.details[\"geom.circle\"].radius_mm": 25.0}},

    {"id": "acad.rect", "timeout_s": ACAD_CASE_TIMEOUT, "tool": "acad_run_capability",
     "title": "画 40×30 矩形 → 闭合/顶点/面积",
     "args": {"ids": ["geom.rect"]},
     "expect_check_true": ["reopen"],
     "expect_min_checks": 4},

    {"id": "acad.dim.linear", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "线性标注 60mm → Measurement 读回",
     "args": {"ids": ["dim.linear"]},
     "expect_check_true": ["measurement", "text_side"],
     "expect_reads": {"reads.details[\"dim.linear\"].measurement_mm": 60.0}},

    {"id": "acad.text.single", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "单行文字 → 内容/位置/字高",
     "args": {"ids": ["text.single"]},
     "expect_min_checks": 3},

    {"id": "acad.layer.create", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "建图层 + Name/Color 读回",
     "args": {"ids": ["layer.create"]},
     "expect_min_checks": 2},

    {"id": "acad.solid.primitive", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "3D 基本体 → 体积判据",
     "args": {"ids": ["solid.primitive"]},
     "expect_min_checks": 3},

    {"id": "acad.solid.extrude", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "3D 拉伸 → 体积 = 面积 × 高",
     "args": {"ids": ["solid.extrude"]},
     "expect_min_checks": 3},

    {"id": "acad.projection", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "三视图投影（front/top/left）",
     "args": {"ids": ["projection.orthographic"]},
     "expect_min_checks": 3},

    {"id": "acad.table.bom", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "BOM 表逐格 + 合计",
     "args": {"ids": ["table.bom"]},
     "expect_min_checks": 3},

    {"id": "acad.export.dxf", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "导出 DXF → 文件/段/重新导入计数",
     "args": {"ids": ["export.dxf"]},
     "expect_check_true": ["file", "sections", "parsed"]},

    {"id": "acad.export.pdf_multipage", "timeout_s": ACAD_CASE_TIMEOUT,
     "tool": "acad_run_capability",
     "title": "多页 PDF：逐布局出图（每页 A3 且有墨）",
     "args": {"ids": ["export.pdf_multipage"]},
     "expect_min_checks": 3},
]


# ------------------------------------------------------------------- CODESYS
def _codesys_available(context: dict) -> bool:
    return not context.get("available")


def _codesys_service_alive(state: str) -> bool:
    """state 文件存在 ≠ 服务活着。

    实测（2026-11-03）：CODESYS 关掉后 `service.json` 还留着旧端口，
    setup 直接复用 → 4 条用例全报 `WinError 10061 目标计算机积极拒绝`。
    所以必须真去 connect 一下，连不上就当陈旧状态处理。
    """
    import json
    import socket
    try:
        with open(state, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:                              # noqa: BLE001
        return False
    port = int(data.get("port") or 0)
    if port <= 0:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0):
            return True
    except OSError:
        return False


def codesys_setup() -> dict:
    """起常驻服务（headless，约 8-10 s）；**确认服务真的应答**才复用。"""
    import json
    import subprocess
    import sys as _sys
    state = os.path.join(os.environ.get("LOCALAPPDATA", ""), "codesyskit", "service.json")
    if os.path.isfile(state) and _codesys_service_alive(state):
        return {"available": True, "started": False}
    if os.path.isfile(state):
        # 陈旧状态：挪到一边，让 start 重新写
        try:
            os.replace(state, state + ".stale")
            print("  [info] CODESYS 服务状态陈旧（端口连不上），已归档并重启服务", flush=True)
        except Exception:                          # noqa: BLE001
            pass
    src = os.environ.get("CODESYSKIT_SRC", r"D:\bililive\codesyskit\src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        subprocess.run([_sys.executable, "-c",
                        "import sys;from codesyskit.cli import main;sys.exit(main(sys.argv[1:]))",
                        "start", "--wait", "180"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, env=env)
    except Exception as exc:                       # noqa: BLE001
        print("  [warn] 起 CODESYS 服务失败：%s" % exc, flush=True)
        return {"available": False}
    ok = os.path.isfile(state) and _codesys_service_alive(state)
    if not ok:
        print("  [warn] CODESYS 服务起不来（state 存在=%s）" % os.path.isfile(state), flush=True)
    return {"available": ok, "started": True}


CODESYS_CASES = [
    {"id": "codesys.status", "tool": "codesys_status",
     "title": "常驻服务可达 + 版本",
     "args": {},
     "expect_check_true": ["service_reachable", "version_present"],
     "skip_if": _codesys_available},

    {"id": "codesys.create", "tool": "codesys_call",
     "title": "新建工程（写到临时目录）",
     "args": lambda ctx: {"cmd": "project.create",
                          "args": {"path": os.path.join(tempfile.gettempdir(),
                                                        "nsa_mcp_hub_accept_codesys.project")}},
     "expect_check_true": ["result_present"],
     "skip_if": _codesys_available},

    {"id": "codesys.info", "tool": "codesys_call",
     "title": "读工程信息",
     "args": {"cmd": "project.info"},
     "expect_check_true": ["result_present"],
     "skip_if": _codesys_available},

    {"id": "codesys.tree", "tool": "codesys_call",
     "title": "读对象树",
     "args": {"cmd": "tree", "args": {"path": "", "depth": 2}},
     "expect_check_true": ["result_present"],
     "skip_if": _codesys_available},
]


# ------------------------------------------------------------------- AutoShop
def _autoshop_missing(context: dict) -> bool:
    return not context.get("available")


def _autoshop_no_project(context: dict) -> bool:
    """没打开工程时没法编译——这是环境问题，不是工具坏了，跳过并说明。"""
    return not context.get("available") or not context.get("project")


def _as_run(*args, timeout=300):
    """跑一次 autoshopkit CLI，返回解析后的 JSON（失败返回 {}）。"""
    import json
    import subprocess
    import sys as _sys
    src = os.environ.get("AUTOSHOPKIT_SRC", r"D:\bililive\autoshopkit\src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    runner = os.path.join(tempfile.gettempdir(), "ash_run.py")
    with open(runner, "w", encoding="utf-8") as fh:
        fh.write("import sys\nfrom autoshopkit.cli import main\nsys.exit(main(sys.argv[1:]))\n")
    try:
        p = subprocess.run([_sys.executable, runner, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except Exception:                              # noqa: BLE001
        return {}
    text = p.stdout or ""
    dec = json.JSONDecoder()
    best = {}
    idx = 0
    while True:
        i = text.find("{", idx)
        if i < 0:
            break
        try:
            obj, end = dec.raw_decode(text[i:])
            if isinstance(obj, dict):
                best = obj
            idx = i + end
        except Exception:                          # noqa: BLE001
            idx = i + 1
    return best


def _il_program(path: str) -> bool:
    info = _as_run("hcp", "--project", path, timeout=90)
    fields = (info.get("fields") or {})
    return str(fields.get("FileName") or "").upper().endswith(".IL")


def autoshop_setup() -> dict:
    """确保 AutoShop 打开的是**带指令列表(H3U/MAIN.IL)的工程**。

    `apply` 需要 IL 编辑器：H5U 或 MAIN.LD 的工程只有梯形图，`apply` 会报
    `no instruction-list editor`。所以这里主动准备一份 IL 工程副本（不碰用户工程）。
    """
    status = _as_run("status", timeout=120)
    project = str(status.get("project") or "")
    if project:
        hcps = glob.glob(os.path.join(project, "*.hcp"))
        if not hcps or not _il_program(hcps[0]):
            project = ""                           # 不是 IL 工程，换掉
    if project:
        return {"available": True, "project": project, "provisioned": False}

    src = os.environ.get("AUTOSHOP_IL_PROJECT", r"D:\bililive\autoshopkit\sandbox\ilcorpus")
    if not os.path.isdir(src):
        print("  [warn] 找不到 IL 工程样本：%s" % src, flush=True)
        return {"available": False}
    # 先关掉 AutoShop（旧工程占着文件，删不掉也拷不进去），再用**唯一目录**复制
    _as_run("stop", timeout=120)
    time.sleep(3)
    workdir = os.path.join(tempfile.gettempdir(),
                           "nsa_mcp_hub_accept_autoshop_%s" % time.strftime("%H%M%S"))
    shutil.copytree(src, workdir)
    hcps = glob.glob(os.path.join(workdir, "*.hcp"))
    if not hcps:
        print("  [warn] 复制出来的工程里没有 .hcp", flush=True)
        return {"available": False}
    hcp = hcps[0]
    started = _as_run("start", hcp, timeout=300)
    if not started.get("pid"):
        print("  [warn] 启动 AutoShop 失败", flush=True)
        return {"available": False}
    time.sleep(3)
    return {"available": True, "project": workdir, "provisioned": True,
            "hcp": hcp}


def autoshop_between(context: dict) -> None:
    """用例之间如果 AutoShop 被前一条命令带走了（实测 compile/apply 超时或保存后会退出），
    就用同一份工程副本重新拉起来，保证后面的用例仍有环境。"""
    if not context.get("available"):
        return
    status = _as_run("status", timeout=60)
    if status.get("pid"):
        return
    hcp = context.get("hcp")
    if not hcp:
        hcps = glob.glob(os.path.join(context.get("project") or "", "*.hcp"))
        hcp = hcps[0] if hcps else ""
    if not hcp:
        return
    started = _as_run("start", hcp, timeout=300)
    if started.get("pid"):
        print("  [info] AutoShop 已重新拉起（pid=%s）" % started["pid"], flush=True)
        time.sleep(3)


def autoshop_teardown(context: dict) -> None:
    """只清理我们复制的工程；不动用户原来开的工程。"""
    if not context.get("provisioned"):
        return
    _as_run("stop", timeout=120)


def _apply_fixture() -> str:
    """写一份三网 IL 到临时文件，给 apply 用例用。"""
    path = os.path.join(tempfile.gettempdir(), "nsa_mcp_hub_accept_apply.il")
    text = ("//net one\nLD X0\nOUT Y0\n"
            "//net two\nLD X1\nOUT Y1\n"
            "//net three\nLD X2\nOUT Y2\n")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


AUTOSHOP_CASES = [
    {"id": "autoshop.status", "tool": "autoshop_status",
     "title": "attach 到 AutoShop",
     "args": {},
     "expect_ok": True,
     "skip_if": _autoshop_missing},

    {"id": "autoshop.tree", "tool": "autoshop_tree",
     "title": "导出工程树",
     "args": {},
     "expect_ok": True,
     "skip_if": _autoshop_missing},

    # 编译放在 apply 之前：实测 apply（写 IL + 保存）之后 AutoShop 会退出
    {"id": "autoshop.compile", "tool": "autoshop_compile",
     "title": "全部编译 → 错误数 0",
     "args": {"timeout_s": 45},
     "expect_checks": {"compile_ok": True, "error_lines": 0},
     "timeout_s": 420,
     "skip_if": _autoshop_no_project},

    {"id": "autoshop.apply", "tool": "autoshop_apply",
     "title": "写 IL → 转换 → 编译（readback_ok + 0 错误）",
     "args": lambda ctx: {"file": _apply_fixture(), "doc": "MAIN", "confirm": True},
     "expect_checks": {"compile_errors": 0, "readback_ok": True},
     "expect_check_true": ["bytes_written"],
     "timeout_s": 420,
     "skip_if": _autoshop_no_project},
]


# ── ug（CAD-Agent-Hub 的 NX MCP：CAM / 机床 / 钣金 / 装配约束）────────────
def _ug_no_live_nx(context: dict) -> bool:
    """NX 交互式会话不在时跳过：上游要 socket 桥（start_mcp.py 在 NX 里跑过）。"""
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ugraf.exe"],
                             capture_output=True, text=True, timeout=20).stdout
        return "ugraf.exe" not in out.lower()
    except Exception:                                  # noqa: BLE001
        return True


def _ug_cam_recipe(client, context: dict) -> dict:
    """端到端 CAM 配方：新零件 → 零件体/毛坯体 → CAM 设置 → 三条工序各自生成刀路。

    覆盖的是「模板 + 工具面」这条链：工序默认毛坯必须是「毛坯几何体」（改过的
    mill_planar.prt 模板），并且 set_cam_operation_geometry 要给工序自己的毛坯体、
    切削区里要有零件顶面 + 毛坯顶面；平面铣还要 floor_z + 边界曲线。
    任何一环退化（模板被还原、参数没生效），path_exists 会立刻变 false。
    """
    import time as _time

    stamp = _time.strftime("%H%M%S")
    part_name = "nsa_accept_cam_%s.prt" % stamp
    steps = []
    checks = []
    ops = {}

    def call(tool: str, args: dict, label: str, strict: bool = True):
        result = client.call(tool, args)
        steps.append({"step": label, "tool": tool, "ok": bool(result.get("ok"))})
        if not result.get("ok") and strict:
            error = (result.get("errors") or [{}])[0]
            raise RuntimeError("%s 失败：%s" % (label, str(error)[:220]))
        return result

    def top_face(body_index: int):
        data = call("ug_inspect_body_topology", {"body_index": body_index},
                    "topology_%d" % body_index).get("reads") or {}
        for face in data.get("faces") or []:
            normal = face.get("normal") or [0, 0, 0]
            if abs(float(normal[2]) - 1.0) < 1e-6:
                return face.get("stable_id")
        raise RuntimeError("body %d 没有 +Z 顶面" % body_index)

    try:
        # 1. 独立零件：零件体 100×60×20，毛坯体 104×64×24（顶面同为 z=20）
        call("ug_create_part", {"file_name": part_name}, "create_part")
        call("ug_create_block", {"length": 100.0, "width": 60.0, "height": 20.0,
                                 "origin": [0.0, 0.0, 0.0]}, "part_block")
        call("ug_create_block", {"length": 104.0, "width": 64.0, "height": 24.0,
                                 "origin": [-2.0, -2.0, -4.0]}, "blank_block")
        call("ug_initialize_cam_setup", {"template_name": "mill_planar"}, "cam_setup")
        call("ug_create_cam_mill_tool", {"name": "T1_D10", "diameter": 10.0,
                                         "flute_length": 30.0,
                                         "overall_length": 75.0}, "tool")
        call("ug_create_cam_milling_context", {
            "origin": [0.0, 0.0, 20.0],
            "part_body_indices": [0],
            "blank_body_indices": [1],
            "workpiece_name": "MCP_WORKPIECE",
        }, "workpiece")

        part_top = top_face(0)
        blank_top = top_face(1)
        selectors = [
            {"selector": {"stable_id": part_top}, "body_index": 0},
            {"selector": {"stable_id": blank_top}, "body_index": 1},
        ]

        # 2. 三条工序，覆盖腔铣族 / 无壁底面 / 平面铣
        for subtype in ("FLOOR_FACING", "POCKETING", "PLANAR_MILL"):
            name = "ACC_%s" % subtype
            call("ug_create_cam_operation", {
                "name": name,
                "template_subtype": subtype,
                "template_type": "mill_planar",
                "tool_name": "T1_D10",
                "geometry_name": "MCP_WORKPIECE",
            }, "create_%s" % subtype)
            call("ug_set_cam_operation_geometry", {
                "operation_name": name,
                "part_body_indices": [0],
                "blank_body_indices": [1],
                "cut_area_face_selectors": selectors,
                "auto_add_blank_faces": True,
                "floor_z": 0.0,
                "depth_per_cut": 2.0,
            }, "geometry_%s" % subtype)
            generated = call("ug_generate_cam_toolpath", {"operation_names": [name]},
                             "generate_%s" % subtype, strict=False)
            checks.append({"check": "%s.generate_ok" % subtype,
                           "ok": bool(generated.get("ok")),
                           "got": bool(generated.get("ok")), "want": True})

        # 3. 判据：三条都得有刀路
        inspected = call("ug_inspect_cam_operations", {}, "inspect").get("reads") or {}
        for record in inspected.get("operations") or []:
            ops[record.get("name")] = bool(record.get("path_exists"))
        for subtype in ("FLOOR_FACING", "POCKETING", "PLANAR_MILL"):
            name = "ACC_%s" % subtype
            found = ops.get(name, False)
            checks.append({"check": "%s.path_exists" % subtype, "ok": found,
                           "got": found, "want": True})
        return {
            "ok": all(item["ok"] for item in checks),
            "reads": {"part": part_name, "operations": ops,
                      "part_top": part_top, "blank_top": blank_top,
                      "steps": steps},
            "checks": checks,
            "errors": [],
        }
    finally:
        # 收紧现场：关掉验收零件（不存盘），把显示切回原零件
        try:
            client.call("ug_run_python", {"code": (
                "import NXOpen\n"
                "s = NXOpen.Session.GetSession()\n"
                "target = None\n"
                "for p in s.Parts:\n"
                "    if str(p.Leaf).startswith('nsa_accept_cam_'):\n"
                "        target = p\n"
                "        break\n"
                "if target is not None:\n"
                "    target.Close(NXOpen.BasePart.CloseWholeTree.TrueValue,\n"
                "                 NXOpen.BasePart.CloseModified.CloseModified, None)\n"
                "left = [p for p in s.Parts]\n"
                "if left:\n"
                "    try:\n"
                "        s.Parts.SetDisplay(left[0], False, True)\n"
                "    except Exception:\n"
                "        pass\n"
                "result = [str(p.Leaf) for p in s.Parts]\n"
            ), "timeout": 180.0})
        except Exception:                              # noqa: BLE001
            pass


UG_CASES = [
    {"id": "ug.ping", "tool": "ug_ping",
     "title": "NX 桥连通性（进程/零件/桥版本）",
     "args": {},
     "expect_ok": True,
     "timeout_s": 120,
     "skip_if": _ug_no_live_nx},

    {"id": "ug.cam.capabilities", "tool": "ug_get_cam_capabilities",
     "title": "CAM 能力自报（模块/许可/可用操作）",
     "args": {},
     "expect_ok": True,
     "timeout_s": 180,
     "skip_if": _ug_no_live_nx},

    {"id": "ug.cam.recipe", "call": _ug_cam_recipe,
     "title": "CAM 端到端配方：新零件 → 三种工序各自生成刀路（path_exists）",
     "expect_check_true": ["FLOOR_FACING.path_exists", "POCKETING.path_exists",
                           "PLANAR_MILL.path_exists", "FLOOR_FACING.generate_ok",
                           "POCKETING.generate_ok", "PLANAR_MILL.generate_ok"],
     "expect_min_checks": 6,
     "timeout_s": 900,
     "skip_if": _ug_no_live_nx},
]

# ── eplan（CAD-Agent-Hub 的 EPLAN 2.9 MCP：电气设计 / 审图）──────────────
def _eplan_missing(context: dict) -> bool:
    """没有 EPLAN **平台本体** 时跳过真机读取类用例。

    注意：光看 EPLAN 目录会误判——本机只装了 EPLAN License Client
    （Common\\EClientService.exe），没有 Platform，Eplan.exe 不存在。
    所以这里查注册表里的平台条目。
    """
    import winreg
    keys = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
    for path in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        name = winreg.EnumKey(root, index)
                        with winreg.OpenKey(root, name) as item:
                            display = winreg.QueryValueEx(item, "DisplayName")[0]
                    except OSError:
                        continue
                    if "EPLAN" not in str(display):
                        continue
                    lowered = str(display).lower()
                    if "license" in lowered or "identity" in lowered:
                        continue
                    return False
        except OSError:
            continue
    return not any(os.path.isfile(p) for p in
                   (r"C:\Program Files\EPLAN\Platform\2.9.4\Bin\Eplan.exe",
                    r"C:\Program Files\EPLAN\Electric P8\2.9.4\Bin\Eplan.exe"))


_EPLAN_INTENT_MODEL = {
    "schema_version": "eplan-design-intent-1",
    "devices": [
        {"tag": "PS1", "kind": "psu", "part_number": None,
         "ports": [{"id": "24V", "conductor": "DC24", "required": True, "physical_pin": None},
                   {"id": "0V", "conductor": "DC0", "required": True, "physical_pin": None}]},
        {"tag": "PLC1", "kind": "plc", "part_number": None,
         "ports": [{"id": "L+", "conductor": "DC24", "required": True, "physical_pin": None},
                   {"id": "M", "conductor": "DC0", "required": True, "physical_pin": None},
                   {"id": "Q0.0", "conductor": "SIGNAL", "required": True,
                    "physical_pin": None, "plc_address": "Q0.0"},
                   {"id": "Q0.1", "conductor": "SIGNAL", "required": True,
                    "physical_pin": None, "plc_address": "Q0.1"}],
         "io_groups": [{"id": "DO", "channels": ["Q0.0", "Q0.1"], "common_port": "M",
                        "supply_port": "L+", "common_conductor": "DC0", "type": "PNP"}]},
        {"tag": "KA1", "kind": "relay", "part_number": None,
         "ports": [{"id": "A1", "conductor": "SIGNAL", "required": True, "physical_pin": None},
                   {"id": "A2", "conductor": "DC0", "required": True, "physical_pin": None}]},
        {"tag": "KA2", "kind": "relay", "part_number": None,
         "ports": [{"id": "A1", "conductor": "SIGNAL", "required": True, "physical_pin": None},
                   {"id": "A2", "conductor": "DC0", "required": True, "physical_pin": None}]},
    ],
    "connections": [
        {"id": "W1", "from": "PS1:24V", "to": "PLC1:L+"},
        {"id": "W2", "from": "PS1:0V", "to": "PLC1:M"},
        {"id": "W3", "from": "PLC1:Q0.0", "to": "KA1:A1"},
        {"id": "W4", "from": "PLC1:Q0.1", "to": "KA2:A1"},
        {"id": "W5", "from": "PS1:0V", "to": "KA1:A2"},
        {"id": "W6", "from": "PS1:0V", "to": "KA2:A2"},
    ],
    "forbidden_pairs": [["PLC1:Q0.0", "PLC1:Q0.1"], ["PS1:24V", "PS1:0V"]],
    "forward_reverse": {"forward_output": "PLC1:Q0.0", "reverse_output": "PLC1:Q0.1",
                        "mutual_exclusion": True,
                        "restart_requires_new_start_edge": True,
                        "reversal_requires_standstill": True},
}


EPLAN_CASES = [
    {"id": "eplan.capabilities", "tool": "eplan_capabilities",
     "title": "EPLAN 能力自报（画像 / 版本约束 / 支持与不支持）",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.profile": "review",
                      "reads.server": "eplan29-lab"},
     "timeout_s": 180},

    {"id": "eplan.tool_catalog", "tool": "eplan_tool_catalog",
     "title": "工具目录（review 画像应给出 15 条）",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.profile": "review", "reads.count": 15},
     "timeout_s": 180},

    {"id": "eplan.bridge.discover", "tool": "eplan_bridge_discover",
     "title": "原生 bridge 发现（EPLAN 没开时应是空列表而不是报错）",
     "args": {},
     "expect_ok": True,
     "timeout_s": 180},

    {"id": "eplan.intent.validate", "tool": "eplan_design_intent_validate",
     "title": "离线设计意图校验：6 根线分成 4 组、给出 14 条告警",
     "args": {"model": _EPLAN_INTENT_MODEL},
     "expect_ok": True,
     "expect_reads": {"reads.wire_groups": 4,
                      "reads.scope": "offline_declared_wire_graph_and_constraints_only"},
     "timeout_s": 180},
]


# ── catia（CATIA V5：建模 / 曲面 / 原生 Analysis）────────────────────────
def _catia_missing(context: dict) -> bool:
    """本机没装 CATIA 就跳过（2026-11-04 实测未安装）。"""
    import os
    roots = [r"C:\Program Files\Dassault Systemes", r"D:\Program Files\Dassault Systemes",
             r"C:\Program Files (x86)\Dassault Systemes"]
    return not any(os.path.isdir(r) for r in roots)


CATIA_CASES = [
    {"id": "catia.health", "tool": "catia_health_check",
     "title": "CATIA 可用性自检",
     "args": {},
     "expect_ok": True,
     "timeout_s": 120,
     "skip_if": _catia_missing},
]


KITS = {
    "sw": {"module": "nsa_mcp_hub.servers.sw_mcp", "setup": sw_setup,
           "teardown": sw_teardown, "cases": SW_CASES},
    "nx": {"module": "nsa_mcp_hub.servers.nx_mcp", "cases": NX_CASES},
    "acad": {"module": "nsa_mcp_hub.servers.acad_mcp", "setup": acad_setup, "between": acad_between, "teardown": acad_teardown, "cases": ACAD_CASES},
    "gx": {"module": "nsa_mcp_hub.servers.gx_mcp", "cases": GX_CASES},
    "codesys": {"module": "nsa_mcp_hub.servers.codesys_mcp", "setup": codesys_setup,
                "cases": CODESYS_CASES},
    "ug": {"module": "nsa_mcp_hub.servers.ug_mcp", "cases": UG_CASES},
    "catia": {"module": "nsa_mcp_hub.servers.catia_mcp", "cases": CATIA_CASES},
    "eplan": {"module": "nsa_mcp_hub.servers.eplan_mcp", "cases": EPLAN_CASES},
    "autoshop": {"module": "nsa_mcp_hub.servers.autoshop_mcp", "setup": autoshop_setup, "between": autoshop_between, "teardown": autoshop_teardown, "cases": AUTOSHOP_CASES},
}

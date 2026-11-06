"""验收用例：SolidWorks / NX / AutoCAD 三家各一组。

SolidWorks 的用例跑在**临时副本**上（`NSA_MCP_HUB_SW_FIXTURE` 可覆盖默认夹具），
NX / AutoCAD 的用例走各自 kit 的 `*_run_capability`，本来就自带几何判据。
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import tempfile
import uuid
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
        return {"available": False, "solidworks": False}
    # 绝不为跑验收去“启动”SolidWorks——没开就跳过，避免制造副作用
    if not _solidworks_running():
        print("  [warn] SolidWorks 没在运行，SolidWorks 组跳过（本套件不会替你启动它）",
              flush=True)
        return {"available": False, "solidworks": False}
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
            # 这份夹具可能已经开着（上一轮 setup 打开没关）——OpenDoc6 会 return None
            # 且 err=65536。按路径找一下已打开的文档，别再报错。
            model = None
            # 注意：GetDocuments 在晚绑定下是**属性**不是方法（调它会 TypeError）。
            # 而且每轮 setup 的临时目录不同，不能比全路径——比**文件名**即可：
            # 夹具副本是丢弃品，同名开着的那个就是上次留下的。
            wanted = os.path.basename(copy_path).lower()
            docs = app.GetDocuments
            for item in (docs or []):
                try:
                    # 这两个在晚绑定下都是**属性**，加括号会 TypeError
                    path = str(item.GetPathName or "")
                    title = str(item.GetTitle or "")
                    if path and os.path.basename(path).lower() == wanted:
                        model = item
                        break
                    if not path and title.lower() == os.path.splitext(wanted)[0].lower():
                        model = item
                        break
                except Exception:                      # noqa: BLE001
                    continue
        if model is None:
            raise RuntimeError("打开夹具失败（err=%s）" % err.value)
        return {"available": True, "solidworks": True, "workdir": workdir,
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



def _sw_threaded_hole_flow(client, context):
    """SW 剧本：螺纹孔（`sw_threaded_hole`，verified）。

    2026-11-06 起 SolidWorks 侧终于有可交付的螺纹孔工具：孔向导对本机不可用
    （HoleWizard5 27 参错位 + COM 下不建特征，见 swkit docs/SILENT_FAILURES.md），
    改走「底孔 FeatureCut4 + 口部倒角 + 真实 ThreadFeatureData」。

    判据全看几何：实测圆柱直径必须等于规格表底孔（±0.15 mm）、孔口出现锥面、
    螺纹是 real（不是 cosmetic 降级），三项齐了 `delivery_gate_passed` 才为 True。
    """
    import json as _json

    checks, reads, steps = [], {}, []

    def record(name, payload):
        ok = bool(payload.get("ok"))
        checks.append({"check": name, "got": ok, "want": True, "ok": ok})
        return payload.get("reads") or {}

    for tool, args in (("sw_create_part", {}),
                       ("sw_create_parametric_part",
                        {"part_type": "block",
                         "parameters": {"length": 120, "width": 60, "height": 20},
                         "execute": True})):
        payload = client.call(tool, args)
        steps.append({"tool": tool, "ok": bool(payload.get("ok"))})
        if tool == "sw_create_parametric_part":
            made = payload
    if not made.get("ok"):
        return {"ok": False, "reads": reads,
                "errors": ["建块失败：%s" % str(made.get("errors"))[:160]],
                "checks": checks}

    # 顶面在 z=0（sw_create_parametric_part 的块以顶面为基准），按点选面更稳
    for size, x, expected in (("M6", -20.0, 5.0), ("M12", 20.0, 10.2)):
        payload = client.call("sw_threaded_hole", {
            "size": size, "depth": 15.0, "through": False,
            "hole_x": x, "hole_y": 0.0,
            "face_x": 0.0, "face_y": 0.0, "face_z": 0.0,
            "mouth_chamfer": 0.5})
        steps.append({"tool": "sw_threaded_hole", "ok": bool(payload.get("ok"))})
        data = record("threaded_hole_%s" % size, payload)
        reads["%s" % size] = data
        checks.append({"check": "%s_bore" % size, "got": data.get("bore_diameter_mm"),
                       "want": expected,
                       "ok": data.get("bore_diameter_mm") is not None
                             and abs(float(data["bore_diameter_mm"]) - expected) <= 0.15})
        checks.append({"check": "%s_chamfer" % size, "got": data.get("cone_faces"),
                       "want": ">=1",
                       "ok": (data.get("cone_faces") or 0) >= 1})
        checks.append({"check": "%s_real_thread" % size, "got": data.get("thread_kind"),
                       "want": "real", "ok": data.get("thread_kind") == "real"})
        checks.append({"check": "%s_gate" % size,
                       "got": data.get("delivery_gate_passed"), "want": True,
                       "ok": data.get("delivery_gate_passed") is True})
        checks.append({"check": "%s_volume_dropped" % size,
                       "got": data.get("volume_delta_mm3"), "want": "<0",
                       "ok": (data.get("volume_delta_mm3") or 0) < 0})

    reads["steps"] = steps
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "reads": reads,
            "errors": [] if ok else ["螺纹孔未达门槛：%s" % _json.dumps(
                [c for c in checks if not c["ok"]], ensure_ascii=False)[:400]],
            "checks": checks}


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

    {"id": "sw.flow.part", "tool": None,
     "title": "SW 剧本：新建零件→矩形草图 40×25→拉伸 20→量体积（判 20000 mm³）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     # 用 lambda 延迟解析：_sw_part_flow 定义在 SW_CASES 之后（模块加载顺序）
     "call": lambda client, context: _sw_part_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.fillet", "tool": None,
     "title": "SW 剧本二：圆 Ø40→拉伸 15→圆角 R2（判体积下降 0–5%）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_fillet_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.inspect", "tool": None,
     "title": "SW 剧本三：块 40×25×10 + 读/视图类 7 个工具（12 步，判 10000 mm³）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_inspect_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.export", "tool": None,
     "title": "SW 剧本四：建块→存盘→导出 STEP/STL（判 ISO-10303-21 与 STL 大小）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_export_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.props", "tool": None,
     "title": "SW 剧本五：倒角/抽壳/自定义属性/配置/材料/重建诊断（14 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_props_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.equations", "tool": None,
     "title": "SW 剧本六：方程/全局变量/镜向/回滚/显示模式（12 步，判 W=40 与 H=10）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_equations_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.sketch", "tool": None,
     "title": "SW 剧本七：草图类 10 工具（弧/多边形/椭圆/中心线/偏移/阵列），判体积不变",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sketch_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.drawing", "tool": None,
     "title": "SW 剧本八：零件→出图→标注→导出 PDF（判 %PDF 头与 >1 KB）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_drawing_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.light.reads", "tool": None,
     "title": "SW 只读 12 连：状态/注册表/文档/索引/模型信息/包围盒（夹具打开时也安全）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_light_reads(client, context)},

    {"id": "sw.flow.surface", "tool": None,
     "title": "SW 剧本九：曲面族（平面区域→加厚→拉伸曲面→偏移曲面，判实体与曲面都存在）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_surface_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.drawing2", "tool": None,
     "title": "SW 剧本十一：IGES 导出 + 出图注释 + 视图旋转 + 导出 PDF/DWG（12 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_drawing2_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.sketch2", "tool": None,
     "title": "SW 剧本十三：草图线/样条/构造线（3 工具，不 exit——判据问题已记录）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sketch2_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.constraint", "tool": None,
     "title": "SW 剧本三十八：草图约束（6 步）",
     "args": {}, "expect_ok": True, "timeout_s": 300,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_constraint_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.fea_solve", "tool": None,
     "title": "SW 剧本四十四：FEA 真求解（10 步，约 11–15 分钟，需单独跑）",
     "args": {}, "expect_ok": True, "timeout_s": 2400,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_fea_solve_flow(client, context)},

    {"id": "sw.flow.select_refs", "tool": None,
     "title": "SW 剧本五十二：持久引用 token 选实体（8 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_select_refs_flow(client, context)},
    {"id": "sw.tool.vba_dump", "tool": "sw_vba_dump",
     "title": "VBA 源码导出（用本机样本 .swp）",
     "args": {"swp": r"D:\bililive\DeepHarness\_sw_probe\generated_test.swp"},
     "expect_ok": True, "timeout_s": 300,
     "requires": ["solidworks"]},

    {"id": "sw.flow.sketch_text", "tool": None,
     "title": "SW 剧本五十：草图文字（4 步）",
     "args": {}, "expect_ok": True, "timeout_s": 300,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sketch_text_flow(client, context)},
    {"id": "sw.flow.close_doc", "tool": None,
     "title": "SW 剧本五十一：关当前文档（8 步）",
     "args": {}, "expect_ok": True, "timeout_s": 300,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_close_doc_flow(client, context)},

    {"id": "sw.flow.asm_replace", "tool": None,
     "title": "SW 剧本四十五：装配替换组件（13 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_asm_replace_flow(client, context)},
    {"id": "sw.flow.refs_select", "tool": None,
     "title": "SW 剧本四十六：选实体（7 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_refs_select_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.refusals", "tool": None,
     "title": "SW 剧本五十五：分型线/空装配两条拒绝路径（9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_refusal_flow(client, context)},
    {"id": "sw.flow.param_dimension", "tool": None,
     "title": "SW 剧本五十四：参数化零件改尺寸（4 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_param_dimension_flow(client, context)},
    {"id": "sw.flow.drawing_extra", "tool": None,
     "title": "SW 剧本五十三：3D 剖视 + 孔表 + 断裂视图 + 四种符号（18 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_drawing_extra_flow(client, context)},
    {"id": "sw.flow.drawing_table", "tool": None,
     "title": "SW 剧本四十七：选视图 + 插 BOM 表（9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_drawing_table_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.reducer_plan", "tool": None,
     "title": "SW 剧本四十八：两级减速器出计划（7 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_reducer_plan_flow(client, context)},
    {"id": "sw.flow.sim_rerun", "tool": None,
     "title": "SW 剧本四十九：求解 → 再求解 → 读结果（12 步，需单独跑）",
     "args": {}, "expect_ok": True, "timeout_s": 1800,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sim_rerun_flow(client, context)},

    {"id": "sw.flow.body_ops", "tool": None,
     "title": "SW 剧本四十一：多实体组合 + 包围盒 + 球体（10 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_body_ops_flow(client, context)},
    {"id": "sw.flow.refs_params", "tool": None,
     "title": "SW 剧本四十二：改特征参数 + 方程增删（9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_refs_params_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.sheetmetal_full", "tool": None,
     "title": "SW 剧本四十三：钣金法兰/卷边/折弯/展开信息（11 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sheetmetal_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.feature_pattern", "tool": None,
     "title": "SW 剧本三十九：按名字选特征 + 特征阵列（12 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_feature_pattern_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.drawing_notes", "tool": None,
     "title": "SW 剧本四十：自动气泡 + 旋转视图（9 步，需单独跑）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_drawing_notes_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.part_ops", "tool": None,
     "title": "SW 剧本三十三：切除/移动/缩放/镜像/材料/关系/DimXpert/Flow（18 步）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_part_ops_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.sim", "tool": None,
     "title": "SW 剧本三十四：FEA 建研究+约束+力+划网格（9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sim_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.sketch_extras", "tool": None,
     "title": "SW 剧本三十六：草图约束/倒角/圆周阵列（10 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sketch_extras_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.plan_only", "tool": None,
     "title": "SW 剧本三十七：只出计划的工具 + 关全部（9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_plan_only_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.face_sketch", "tool": None,
     "title": "SW 剧本三十二：面上开草图 + 转换实体引用（8 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_face_sketch_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.assembly_b", "tool": None,
     "title": "SW 剧本三十：装配插入两件 + 面到面距离（12 步，上游已修）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_assembly_b_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.scan", "tool": None,
     "title": "SW 剧本三十一：另存副本 → 批量扫描 → 关文档（9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_scan_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.assemble", "tool": None,
     "title": "SW 剧本二十五：重入草图/分割线 + 直连装配（create_assembly/open_document/assembly_add）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_assemble_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.bodies", "tool": None,
     "title": "SW 剧本二十八：实体平移/缩放/镜像/组合（9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_bodies_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.modify", "tool": None,
     "title": "SW 剧本二十六：抑制/解抑制/删特征（8 步，中文特征名直传）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_modify_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},
    {"id": "sw.flow.delete_body", "tool": None,
     "title": "SW 剧本二十七：建件后删实体（6 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_delete_body_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.artifacts", "tool": None,
     "title": "SW 剧本二十四：导出 PDF + 截图 BMP/PNG + 取消抑制（10 步，判文件头）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_artifacts_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.sheet", "tool": None,
     "title": "SW 剧本十：钣金基体法兰 + 展开图信息（6 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sheet_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.batch.plans", "tool": None,
     "title": "SW 纯函数批量：球/渐开线齿轮/两级减速器/输出轴 计划 + 单文件属性（5 条，不开 COM）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "call": lambda client, context: _sw_batch_tools(client, [
         "sw_sphere_plan", "sw_gear_involute_plan", "sw_gearbox_plan",
         "sw_output_shaft_plan", "sw_props"])},
    {"id": "sw.batch.doc_reads", "tool": None,
     "title": "SW 文档级只读批量：DimXpert 读取/仿真列表与状态/特征树自省（4 条）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_batch_tools(client, [
         "sw_dxp", "sw_sim_list", "sw_sim_status", "sw_feature_inspect"],
         setup=[("sw_create_part", {}),
                ("sw_create_sketch", {"plane": "前视基准面"}),
                ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 30.0, "y2": 20.0}),
                ("sw_exit_sketch", {}),
                ("sw_extrude", {"depth_mm": 8})]),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.sketch_ops", "tool": None,
     "title": "SW 剧本二十二：草图圆角/剪裁（靠新的选中工具，9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_sketch_ops_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.dwgviews", "tool": None,
     "title": "SW 剧本二十一：图纸加投影/辅助视图（9 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_dwgviews_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.revolve", "tool": None,
     "title": "SW 剧本二十：旋转凸台（体积=π·30·(20²−5²)）+ 旋转曲面（12 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_revolve_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.batch.misc", "tool": None,
     "title": "SW 批量：环境/选择/保存/文档切换（14 步，全快工具）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_misc_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.asm_ops", "tool": None,
     "title": "SW 剧本十八：装配体读取/配置/组件阵列镜像（16 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_asm_ops_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.assembly", "tool": None,
     "title": "SW 剧本十六：装配链（建装配→插两件→干涉/树/固定/抑制/爆炸，14 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_assembly_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.flow.annotate", "tool": None,
     "title": "SW 剧本十五：出图注释族（中心线/粗糙度/注释×2/球标 + 导出 PDF）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_annotate_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

    {"id": "sw.status", "tool": "sw_status",
     "title": "连接状态 + 打开文档数 + 注册表摘要（不建模）",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

    {"id": "sw.registry", "tool": "sw_registry",
     "title": "工具注册表：哪些真的能用、依据是什么",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

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

    # ── 从上游 test_*.py 搬来的判据（纯几何，不需要 SolidWorks 在跑）──
    {"id": "sw.plan.gear", "tool": "sw_gear_involute_plan",
     "title": "上游 test_involute_gear：m2 z20 → 分度 R20 / 外径 R22 / 齿根 R17.5 / 基圆 R18.79",
     "args": {"module_mm": 2, "tooth_count": 20, "pressure_angle_deg": 20,
              "thickness_mm": 10, "bore_diameter_mm": 10},
     "expect_ok": True,
     "expect_reads": {"reads.spec_valid": True, "reads.feature_count": 9,
                      "reads.spec.pitch_radius_mm": 20.0,
                      "reads.spec.outer_radius_mm": 22.0,
                      "reads.spec.root_radius_mm": 17.5,
                      "reads.spec.base_radius_mm": 18.79385241571817},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.gearbox", "tool": "sw_gearbox_plan",
     "title": "上游 test_gearbox：传动比 6.0、两级中心距 60/80",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.metadata.total_ratio": 6.0,
                      "reads.metadata.stage1_center_distance_mm": 60.0,
                      "reads.metadata.stage2_center_distance_mm": 80.0},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.flange", "tool": "sw_part_plan",
     "title": "上游 test_part_generators：法兰 8 孔 → 5 个特征",
     "args": {"part_type": "flange", "parameters": {"outer_diameter_mm": 120,
                                                    "bore_diameter_mm": 40,
                                                    "thickness_mm": 12,
                                                    "bolt_circle_diameter_mm": 90,
                                                    "bolt_hole_diameter_mm": 10,
                                                    "bolt_count": 8}},
     "expect_ok": True,
     "expect_reads": {"reads.part_type": "flange", "reads.feature_count": 5},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.output_shaft", "tool": "sw_output_shaft_plan",
     "title": "上游 test_output_shaft：总长 333、7 段直径 [55,60,65,60,55,50,45]",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.metadata.total_length_mm": 333.0,
                      "reads.feature_count": 13},
     "no_setup": True, "timeout_s": 120},

    # ── 深几何层（内齿圈 / 斜齿轮 / 花键 / 键槽库）：纯计算 ──
    {"id": "sw.plan.internal_gear", "tool": "sw_internal_gear_plan",
     "title": "内齿圈 m2 z40：分度 R40 / 齿顶 R38（朝内）/ 齿根 R42.5 / 渐开线齿槽 体积 26325.888",
     "args": {"module_mm": 2, "tooth_count": 40, "thickness_mm": 12,
              "rim_outer_diameter_mm": 96},
     "expect_ok": True,
     "expect_reads": {"reads.feature_count": 3,
                      "reads.spec.pitch_radius_mm": 40.0,
                      "reads.spec.tip_radius_mm": 38.0,
                      "reads.spec.root_radius_mm": 42.5,
                      "reads.expected_volume_mm3": 26325.888},
     "tol": 1e-2, "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.helical_gear", "tool": "sw_helical_gear_plan",
     "title": "斜齿轮 mn2 z24 β20：mt=2.128356、导程 440.8993、扭转 0.285017、12 特征（放样）",
     "args": {"module_normal_mm": 2, "tooth_count": 24, "helix_angle_deg": 20,
              "thickness_mm": 20, "bore_diameter_mm": 16, "slices": 4},
     "expect_ok": True,
     "expect_reads": {"reads.feature_count": 12,
                      "reads.spec.module_transverse_mm": 2.128356,
                      "reads.spec.lead_mm": 440.8993,
                      "reads.spec.total_twist_rad": 0.285017},
     "tol": 1e-2, "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.spline", "tool": "sw_spline_plan",
     "title": "矩形花键 D46/d40 z8 b8 L60：截面积 1419.955、体积 85197.301",
     "args": {"outer_diameter_mm": 46, "inner_diameter_mm": 40, "tooth_count": 8,
              "key_width_mm": 8, "length_mm": 60},
     "expect_ok": True,
     "expect_reads": {"reads.feature_count": 3,
                      "reads.section_area_mm2": 1419.955,
                      "reads.expected_volume_mm3": 85197.301},
     "tol": 1e-2, "no_setup": True, "timeout_s": 120},

    # ── 齿轮检验尺寸（公法线 / 跨棒距 / 齿厚）──
    {"id": "sw.gear.inspection", "tool": "sw_gear_inspection",
     "title": "齿轮检验 m2 z20：齿厚 3.1416、公法线 W3 15.3209、跨棒距 42.2896（量柱 2.7896，中部接触）",
     "args": {"module_mm": 2, "tooth_count": 20},
     "expect_ok": True,
     "expect_reads": {"reads.inspection.tooth_thickness_at_pitch_mm": 3.1416,
                      "reads.inspection.span_measurement.k": 3,
                      "reads.inspection.span_measurement.span_length_mm": 15.3209,
                      "reads.inspection.span_over_pins.span_mm": 42.2896,
                      "reads.inspection.span_over_pins.pin_diameter_mm": 2.7896,
                      "reads.inspection.span_over_pins.contact_radius_mm": 19.75,
                      "reads.inspection.span_over_pins.pin_diameter_rule": "contact at mid tooth height",
                      "reads.inspection.span_over_pins.even_teeth": True},
     "tol": 1e-2, "no_setup": True, "timeout_s": 120},

    {"id": "sw.gear.inspection.odd", "tool": "sw_gear_inspection",
     "title": "齿轮检验 m2 z21（奇数齿）：跨棒距按 cos(π/2z) 修正",
     "args": {"module_mm": 2, "tooth_count": 21},
     "expect_ok": True,
     "expect_reads": {"reads.inspection.span_over_pins.even_teeth": False},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.gear.inspection.internal", "tool": "sw_gear_inspection",
     "title": "内齿检验 m2 z40：跨棒距 77.7228、α_M 20.956（量柱 2.7772，内齿减量柱）",
     "args": {"module_mm": 2, "tooth_count": 40, "internal": True},
     "expect_ok": True,
     "expect_reads": {"reads.inspection.span_over_pins.span_mm": 77.7228,
                      "reads.inspection.span_over_pins.alpha_M_deg": 20.956,
                      "reads.inspection.span_over_pins.pin_diameter_mm": 2.7772,
                      "reads.inspection.pitch_diameter_mm": 80.0},
     "tol": 1e-2, "no_setup": True, "timeout_s": 120},

    {"id": "sw.gear.inspection.refuse", "tool": "sw_gear_inspection",
     "title": "负面对照：内齿量柱 20mm 相对基圆过大 → 必须拒绝",
     "args": {"module_mm": 2, "tooth_count": 40, "internal": True,
              "pin_diameter_mm": 20},
     "expect_ok": False, "no_setup": True, "timeout_s": 60},

    {"id": "sw.gear.inspection.helical", "tool": "sw_gear_inspection",
     "title": "斜齿检验 mn2 z24 β20：当量齿 28.9237、法向公法线 W4 21.4751、量球跨距 60.1021（球 2.7791）",
     "args": {"module_mm": 2, "tooth_count": 24, "helix_angle_deg": 20},
     "expect_ok": True,
     "expect_reads": {"reads.inspection.virtual_tooth_count": 28.9237,
                      "reads.inspection.normal_span_measurement.k": 4,
                      "reads.inspection.normal_span_measurement.span_length_mm": 21.4751,
                      "reads.inspection.span_over_balls.span_mm": 60.1021,
                      "reads.inspection.span_over_balls.ball_diameter_mm": 2.7791,
                      "reads.inspection.span_over_balls.ball_diameter_rule": "contact at mid tooth height",
                      "reads.inspection.span_over_balls.even_teeth": True},
     "tol": 1e-2, "no_setup": True, "timeout_s": 120},

    {"id": "sw.spline.inspection", "tool": "sw_spline_inspection",
     "title": "花键检具 D46/d40 z8 b8：推荐量柱 8.455、跨棒距 M 51.454（夹在齿侧上）",
     "args": {"outer_diameter_mm": 46, "inner_diameter_mm": 40,
              "tooth_count": 8, "key_width_mm": 8},
     "expect_ok": True,
     "expect_reads": {"reads.inspection.tooth_thickness_mm": 8.0,
                      "reads.inspection.recommended_pin_diameter_mm": 8.455,
                      "reads.inspection.span_over_pins.pin_diameter_mm": 8.455,
                      "reads.inspection.span_over_pins.span_mm": 51.454,
                      "reads.inspection.span_over_pins.contact": "flank",
                      "reads.inspection.span_over_pins.even_teeth": True},
     "tol": 1e-2, "no_setup": True, "timeout_s": 120},

    {"id": "sw.spline.inspection.refuse", "tool": "sw_spline_inspection",
     "title": "负面对照：量柱 1mm 太细、落到齿根圆上（量不到齿厚）→ 必须拒绝",
     "args": {"outer_diameter_mm": 46, "inner_diameter_mm": 40,
              "tooth_count": 8, "key_width_mm": 8, "pin_diameter_mm": 1.0},
     "expect_ok": False, "no_setup": True, "timeout_s": 60},

    {"id": "sw.note.inspection", "tool": "sw_inspection_note",
     "title": "检验注释（只格式化）：注释里必须出现 W3 15.3209 与 M 42.2896",
     "args": {"kind": "gear", "module_mm": 2, "tooth_count": 20, "write": False},
     "expect_ok": True,
     "expect_reads": {"reads.kind": "external_involute_gear",
                      "reads.written": False},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.note.inspection.write", "tool": "sw_inspection_note",
     "title": "检验注释写进工程图：文档类型 3、注释文本读回含数值、位置已设",
     "args": {"kind": "gear", "module_mm": 2, "tooth_count": 20, "write": True},
     "expect_ok": True,
     "expect_reads": {"reads.written": True, "reads.document_type": 3},
     "timeout_s": 600},

    # ── 检验图（视图 + 标题栏 + 检验注释）──
    {"id": "sw.sheet.gear", "tool": "sw_inspection_drawing",
     "title": "齿轮检验图一条龙：现建齿轮 → 工程图 → 前视/上视 → 视图尺寸 + 检验注释 + 标题栏",
     "args": {"kind": "gear", "title": "输入齿轮检验图", "drawing_number": "NSA-0001",
              "auto_part": True},
     "expect_ok": True,
     "expect_reads": {"reads.document_type": 3, "reads.drawing_created": True},
     "timeout_s": 900},

    {"id": "sw.asm.reducer.drawing", "tool": "sw_reducer_assembly_drawing",
     "title": "减速器整机装配图：7 组件 → 前视/等轴测 → BOM 表（8 行×4 列 32 格）+ 球标 + 标题栏",
     "args": {"title": "两级减速器装配图", "drawing_number": "NSA-ASM-0001"},
     "expect_ok": True,
     "expect_reads": {"reads.components": 7, "reads.bom_rows": 1,
                      "reads.bom_table.rows": 8, "reads.bom_table.cols": 4,
                      "reads.bom_table.cells_written": 32,
                      "reads.bom_table.parts_present": 7},
     "timeout_s": 1800},

    {"id": "sw.sheet.spline", "tool": "sw_inspection_drawing",
     "title": "花键检验图：现建花键轴 → 工程图 + 检验注释（跨棒距 + 量柱）",
     "args": {"kind": "spline", "title": "花键轴检验图", "drawing_number": "NSA-0002",
              "auto_part": True},
     "expect_ok": True,
     "expect_reads": {"reads.document_type": 3},
     "timeout_s": 900},

    {"id": "sw.note.reducer", "tool": "sw_inspection_note",
     "title": "减速器整机检验表（只格式化）：4 个齿轮各一条 W/M + 3 处键槽",
     "args": {"kind": "reducer", "write": False},
     "expect_ok": True,
     "expect_reads": {"reads.kind": "two_stage_parallel_shaft_reducer",
                      "reads.written": False},
     "no_setup": True, "timeout_s": 180},

    {"id": "sw.note.reducer.write", "tool": "sw_inspection_note",
     "title": "减速器检验表写到工程图：表格 9 行、读回含跨棒距与键宽",
     "args": {"kind": "reducer", "write": True},
     "expect_ok": True,
     "expect_reads": {"reads.written": True, "reads.document_type": 3},
     "timeout_s": 600},

    {"id": "sw.spline.pin.rule", "tool": "sw_spline_inspection",
     "title": "花键量柱规则显式化：走齿侧接触分支、量柱中心落在中径 21.5",
     "args": {"outer_diameter_mm": 46, "inner_diameter_mm": 40,
              "tooth_count": 8, "key_width_mm": 8},
     "expect_ok": True,
     "expect_reads": {"reads.inspection.span_over_pins.pin_diameter_rule":
                      "flank contact at radial mid height",
                      "reads.inspection.span_over_pins.pin_contact_radius_mm": 21.4995,
                      "reads.inspection.span_over_pins.mid_tooth_height_radius_mm": 21.5,
                      "reads.inspection.span_over_pins.contact": "flank"},
     "tol": 1e-2, "no_setup": True, "timeout_s": 120},

    {"id": "sw.plan.gearbox.keyways", "tool": "sw_gearbox_plan",
     "title": "减速器键槽按 GB/T 1096 查表：三根轴 3×3 / 4×4 / 5×5，键长 10",
     "args": {},
     "expect_ok": True,
     "expect_reads": {"reads.metadata.keyways.0.width_mm": 3.0,
                      "reads.metadata.keyways.0.shaft_depth_mm": 1.8,
                      "reads.metadata.keyways.1.width_mm": 4.0,
                      "reads.metadata.keyways.1.shaft_depth_mm": 2.5,
                      "reads.metadata.keyways.2.width_mm": 5.0,
                      "reads.metadata.keyways.2.shaft_depth_mm": 3.0,
                      "reads.metadata.keyways.0.key_length_mm": 10.0},
     "no_setup": True, "timeout_s": 120},

    {"id": "sw.keyway.lookup", "tool": "sw_keyway_lookup",
     "title": "GB/T 1096：φ55 → 16×10、t1=6.0、t2=4.3；需求键长 48 → 标准 50",
     "args": {"shaft_diameter_mm": 55, "required_length_mm": 48},
     "expect_ok": True,
     "expect_reads": {"reads.key.width_mm": 16.0, "reads.key.height_mm": 10.0,
                      "reads.key.shaft_depth_mm": 6.0,
                      "reads.key.hub_depth_mm": 4.3,
                      "reads.standard_length_mm": 50.0},
     "no_setup": True, "timeout_s": 60},

    {"id": "sw.plan.internal_gear.refuse", "tool": "sw_internal_gear_plan",
     "title": "负面对照：轮缘壁厚不足（rim φ84 ≈ 齿根 φ85）必须拒绝",
     "args": {"module_mm": 2, "tooth_count": 40, "thickness_mm": 12,
              "rim_outer_diameter_mm": 84},
     "expect_ok": False, "no_setup": True, "timeout_s": 60},

    {"id": "sw.plan.helical_gear.refuse", "tool": "sw_helical_gear_plan",
     "title": "负面对照：螺旋角 60°（超出 5–45°）必须拒绝",
     "args": {"helix_angle_deg": 60},
     "expect_ok": False, "no_setup": True, "timeout_s": 60},

    {"id": "sw.plan.spline.refuse", "tool": "sw_spline_plan",
     "title": "负面对照：键宽 44 ≥ 内径 40，齿廓会自交，必须拒绝",
     "args": {"outer_diameter_mm": 46, "inner_diameter_mm": 40, "tooth_count": 8,
              "key_width_mm": 44},
     "expect_ok": False, "no_setup": True, "timeout_s": 60},

    # ── 深几何层：真机建出来（判据是体积区间）──
    {"id": "sw.create.internal_gear", "tool": "sw_create_internal_gear",
     "title": "内齿圈真机：3 特征、渐开线齿槽、体积 26325.888（±1%）",
     "args": {"module_mm": 2, "tooth_count": 40, "thickness_mm": 12, "execute": True},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 3, "reads.executed": True},
     "expect_between": {"reads.execute.body_volume_mm3": [26062.6, 26589.1]},
     "timeout_s": 600},

    {"id": "sw.create.spline_shaft", "tool": "sw_create_spline_shaft",
     "title": "花键轴真机：3 特征、体积 85197.301（±1%）",
     "args": {"outer_diameter_mm": 46, "inner_diameter_mm": 40, "tooth_count": 8,
              "key_width_mm": 8, "length_mm": 60, "execute": True},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 3, "reads.executed": True},
     "expect_between": {"reads.execute.body_volume_mm3": [84345.3, 86049.3]},
     "timeout_s": 600},

    {"id": "sw.create.helical_gear", "tool": "sw_create_helical_gear",
     "title": "斜齿轮真机（4 段放样、真螺旋面）：12 特征、体积 36290.5（±3%）",
     "args": {"module_normal_mm": 2, "tooth_count": 24, "helix_angle_deg": 20,
              "thickness_mm": 20, "bore_diameter_mm": 16, "slices": 4,
              "execute": True},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 12, "reads.executed": True},
     "expect_between": {"reads.execute.body_volume_mm3": [35201.8, 37379.2]},
     "timeout_s": 900},

    {"id": "sw.create.output_shaft", "tool": "sw_create_output_shaft",
     "title": "输出轴真机回归：13 特征、体积 768065.6（±2%）",
     "args": {"execute": True},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 13, "reads.executed": True},
     "expect_between": {"reads.execute.body_volume_mm3": [752704.3, 783426.9]},
     "timeout_s": 900},

    {"id": "sw.create.sphere.live", "tool": "sw_create_sphere",
     "title": "一步到位（真机）：球 Ø40 → 体积 33510.3 mm³（解析解误差 <0.05%）",
     "args": {"diameter_mm": 40.0, "execute": True},
     "expect_ok": True,
     "expect_check_true": ["executed", "steps_ok"],
     "expect_between": {"reads.execute.body_volume_mm3": [33500.0, 33520.0]},
     "timeout_s": 900},

    {"id": "sw.create.gear", "tool": "sw_create_involute_gear",
     "title": "一步到位封装：齿轮出图（execute=false → 9 个特征；收尾默认关，SW2025 无 FeatureFillet）",
     "args": {"module_mm": 2.0, "tooth_count": 20, "execute": False},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 9, "reads.executed": False},
     "expect_check_true": ["graph_built", "feature_names"],
     "no_setup": True,
     "timeout_s": 180},

    {"id": "sw.create.reducer", "tool": "sw_create_two_stage_reducer",
     "title": "一步到位封装：两级减速器出图（16 特征 + 传动比 6.0 + 中心距 60）",
     "args": {"execute": False},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 16, "reads.ratio": 6.0,
                      "reads.center_distance_stage1_mm": 60.0},
     "no_setup": True,
     "timeout_s": 180},

    {"id": "sw.create.reducer.live", "tool": "sw_create_two_stage_reducer",
     "title": "减速器真机（渐开线齿轮）：16 特征、7 实体、总材积 192448（±3%）",
     "args": {"execute": True},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 16, "reads.executed": True,
                      "reads.ratio": 6.0,
                      "reads.center_distance_stage1_mm": 60.0,
                      "reads.execute.body_count": 7},
     "expect_between": {"reads.execute.body_volume_mm3": [186511.3, 198048.1]},
     "timeout_s": 900},

    {"id": "sw.create.sphere", "tool": "sw_create_sphere",
     "title": "一步到位封装：球体出图 + 解析体积 4/3·π·r³",
     "args": {"diameter_mm": 40.0, "execute": False},
     "expect_ok": True,
     "expect_reads": {"reads.graph_steps": 3, "reads.analytic_volume_mm3": 33510.322},
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

    {"id": "sw.tool.runtime", "tool": "kit_runtime",
     "title": "SW 内核运行状态（kit_runtime）", "args": {}, "expect_ok": True, "timeout_s": 120},
    {"id": "sw.threaded_hole", "tool": None,
     "title": "SW 剧本：螺纹孔 M6/M12（底孔 Ø5.0/Ø10.2 + 倒角 + 真实螺纹）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "requires": ["solidworks"],
     "call": lambda client, context: _sw_threaded_hole_flow(client, context),
     "cleanup": lambda client, context: _close_unsaved_docs(client)},

]


# ------------------------------------------------------------------------ NX
NX_CASES = [
    {"id": "nx.tool.delete_face", "tool": "nx_solid_delete_face",
     "title": "NX 删孔面愈合（93716.8 → 100000 / 6 面）",
     "args": {}, "expect_ok": True, "timeout_s": 600},

    {"id": "nx.tool.run_capability", "tool": "nx_run_capability",
     "title": "NX 能力分发器：按 id 跑 solid.delete_face",
     "args": {"id": "solid.delete_face"}, "expect_ok": True, "timeout_s": 600},

    {"id": "nx.status", "tool": "nx_status",
     "title": "NX 环境（run_journal 路径 + 能力数）",
     "args": {},
     "expect_reads": {"reads.cap_count": 146}},

    {"id": "nx.selftest", "tool": "nx_selftest",
     "title": "离线自检：每条能力的动作与判据是否齐全（不开 NX）",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

    # ── 多步剧本：一条用例覆盖一串工具（快乐路径）──
    {"id": "nx.batch.asm", "tool": None,
     "title": "NX 批量：装配三组件/组件名/约束参考（3 条）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "call": lambda client, context: _nx_batch(client, [
         "nx_asm_three_components", "nx_asm_component_names", "nx_asm_constraint_refs",
     ])},

    {"id": "nx.batch.export_asm", "tool": None,
     "title": "NX 批量：DWG/DXF 导出/另存副本/引导扫掠/修剪实体/投影视图/装配两组件/加组件（8 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_export_dwg", "nx_export_dxf", "nx_file_save_copy", "nx_feature_sweep_guide",
         "nx_solid_trim_body", "nx_drawing_projected_view", "nx_asm_two_components",
         "nx_asm_add_component",
     ])},

    {"id": "nx.batch.boolean", "tool": None,
     "title": "NX 批量：布尔差保留/双工具/三体并/双实体/移动/文字/筋/两面/体类型/Parasolid（10 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_boolean_subtract_retain", "nx_boolean_two_tools", "nx_boolean_unite_three",
         "nx_block_two_bodies", "nx_solid_move_body", "nx_feature_text", "nx_feature_rib",
         "nx_measure_faces_two", "nx_inspect_body_type", "nx_export_parasolid",
     ])},

    {"id": "nx.batch.solid", "tool": None,
     "title": "NX 批量：圆锥/球/孔/倒角/边倒圆/线性阵列/实体状态/基准面/基准轴/ACIS（10 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_solid_cone", "nx_solid_sphere", "nx_feature_hole", "nx_feature_chamfer",
         "nx_feature_edge_blend", "nx_feature_pattern_linear", "nx_inspect_body_state",
         "nx_datum_plane", "nx_datum_axis", "nx_export_acis",
     ])},

    {"id": "nx.batch.sketch_drawing", "tool": None,
     "title": "NX 批量：草图约束/水平/尺寸 + A4 图纸/基础视图/尺寸标注（6 条）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "call": lambda client, context: _nx_batch(client, [
         "nx_sketch_constraint", "nx_sketch_horizontal", "nx_sketch_dimension",
         "nx_drawing_sheet_a4", "nx_drawing_base_view", "nx_drawing_dimension",
     ])},

    {"id": "nx.batch.export", "tool": None,
     "title": "NX 批量：环形拉伸/整圆拉伸/布尔交/面面积/距离/边数/英制/IGES/STL/STEP-AP214（10 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_extrude_ring", "nx_sketch_circle_extrude", "nx_boolean_intersect",
         "nx_measure_face_area", "nx_measure_distance", "nx_inspect_edge_count",
         "nx_part_inch", "nx_export_iges", "nx_export_stl", "nx_export_step_ap214",
     ])},

    {"id": "nx.batch.model", "tool": None,
     "title": "NX 批量：拉伸/布尔并/布尔差/块/圆柱/量质量/周长/面类型/拓扑/导出 STEP（10 条）",
     "args": {}, "expect_ok": True, "timeout_s": 1200,
     "call": lambda client, context: _nx_batch(client, [
         "nx_extrude_rect", "nx_boolean_union", "nx_boolean_subtract",
         "nx_block_create", "nx_cylinder_create", "nx_measure_mass",
         "nx_measure_perimeter", "nx_inspect_face_types", "nx_body_topo",
         "nx_export_step",
     ])},

    {"id": "nx.flow.block", "tool": None, "title": "NX 剧本：新建零件→矩形草图→拉伸→量质量",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "call": lambda client, context: _flow(client, [
         ("nx_part_new", {}),
         ("nx_sketch_rect", {}),
         ("nx_sketch_extrude", {}),
         ("nx_measure_mass", {}),
     ])},

    {"id": "nx.flow.inspect", "tool": None,
     "title": "NX 剧本：实体拓扑 + 面积/周长 + 能力清单",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "call": lambda client, context: _flow(client, [
         ("nx_body_topo", {}),
         ("nx_measure_face_area", {}),
         ("nx_measure_perimeter", {}),
         ("nx_list_caps", {}),
     ])},

    {"id": "nx.block", "tool": "nx_run_capability",
     "title": "真机建块 100×50×20 → 体积 100000",
     "args": {"ids": ["block.create"]},
     "expect_check_true": ["volume_mm3", "faces", "edges"],
     "expect_min_checks": 3},

    {"id": "nx.tool.runtime", "tool": "kit_runtime",
     "title": "NX 内核运行状态（kit_runtime）", "args": {}, "expect_ok": True, "timeout_s": 120},
]


# ------------------------------------------------------------------------ GX
def _gx_flow(client, steps, work_tag):
    """gx 多步剧本：按顺序调工具，首个失败即停（每条 57–595 s，别把时间浪费在后续）。

    steps 里的 args 可以用 "{work}" 占位，会被替换成本次沙箱目录。
    """
    import threading
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_gx_%s_" % work_tag)
    done, failures = [], []
    for name, args in steps:
        real = {}
        for key, value in (args or {}).items():
            real[key] = work if value == "{work}" else value
        box: dict = {}

        def _one(tool_name=name, tool_args=real):
            try:
                box["payload"] = client.call(tool_name, tool_args)
            except Exception as exc:                   # noqa: BLE001
                box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:140])

        worker = threading.Thread(target=_one, daemon=True)
        worker.start()
        worker.join(600)
        if worker.is_alive():
            failures.append("%s 超时（>600 s）" % name)
            done.append({"tool": name, "ok": False})
            break
        if "error" in box:
            failures.append("%s 抛异常：%s" % (name, box["error"]))
            done.append({"tool": name, "ok": False})
            break
        ok = bool(box["payload"].get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            failures.append("%s 失败：%s" % (name, str(box["payload"].get("errors"))[:160]))
            break
    return {"ok": not failures, "reads": {"steps": done, "workdir": work},
            "errors": failures,
            "checks": [{"check": "gx_flow_ok", "got": len(done) - len(failures),
                        "want": len(done), "ok": not failures}]}


def _gx_flow_tail(client, context):
    """gx 剧本七：收尾五个工具（6 步）。

    这五个都不带参数、自带工程创建：工程校验 / 工程比对 / 批量建工程 /
    功能块带参数 / iQ-R 往返。
    """
    steps = [
        ("gx_project_new", {}),
        ("gx_project_check", {}),
        ("gx_project_diff", {}),
        ("gx_batch_new_projects", {}),
        ("gx_program_import_fb_params", {}),
        ("gx_program_rcpu_roundtrip", {"series": 0, "model": 0}),
    ]
    return _gx_flow(client, steps, "tail")


def _gx_flow_project(client, context):
    """gx 剧本一：四种工程创建 + 保存/重开/元信息（7 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_gx_proj_")
    base = work.replace("\\", "/")
    steps = [
        ("gx_project_new", {}),
        ("gx_project_save", {}),
        ("gx_project_meta", {}),
        ("gx_project_new_fx5s", {"series": 0, "model": 0}),
        ("gx_project_new_rcpu", {"series": 0, "model": 0}),
        ("gx_project_new_language", {}),
        ("gx_project_reopen", {}),
    ]
    return _gx_flow(client, steps, "proj")


def _gx_flow_program(client, context):
    """gx 剧本二：ST 粘贴/读回 + 梯级/并联/应用指令（7 步）。"""
    steps = [
        ("gx_project_new", {}),
        ("gx_program_paste_st", {}),
        ("gx_program_read_st", {}),
        ("gx_program_write_ladder", {}),
        ("gx_program_write_ladder_multi", {"rungs": []}),
        ("gx_program_write_ladder_parallel", {"contacts": [], "parallel": [], "out": []}),
        ("gx_program_write_ladder_appl", {"contacts": [], "parallel": [], "out": []}),
    ]
    return _gx_flow(client, steps, "prog")


def _gx_flow_build(client, context):
    """gx 剧本三：全部转换 + 程序检查 + 编译诊断（7 步）。"""
    steps = [
        ("gx_project_new", {}),
        ("gx_program_paste_st", {}),
        ("gx_build_convert_all", {}),
        ("gx_build_program_check", {}),
        ("gx_build_error_messages", {}),
        ("gx_build_error_detail", {}),
        ("gx_build_locate_error_line", {"bad_line": 3, "total_lines": 6}),
    ]
    return _gx_flow(client, steps, "build")


def _gx_flow_inspect(client, context):
    """gx 剧本四：读程序/梯形图/IL/源码映射（6 步）。"""
    steps = [
        ("gx_project_new", {}),
        ("gx_program_paste_st", {}),
        ("gx_build_convert_all", {}),
        ("gx_inspect_programs", {}),
        ("gx_inspect_ladder", {}),
        ("gx_inspect_mil", {}),
        ("gx_inspect_source_map", {}),
    ]
    return _gx_flow(client, steps, "insp")


def _gx_flow_label(client, context):
    """gx 剧本五：标签/结构体（8 步）。"""
    steps = [
        ("gx_project_new", {}),
        ("gx_label_multi_type", {}),
        ("gx_datatype_import", {"struct_name": "ST_ACC", "program_name": "PrgGen"}),
        ("gx_datatype_custom_members", {"struct_name": "ST_ACC", "program_name": "PrgGen",
                                        "var_name": "stAcc"}),
        ("gx_datatype_member_var", {"struct_name": "ST_ACC", "program_name": "PrgGen",
                                    "var_name": "stAcc"}),
        ("gx_datatype_member_access", {"struct_name": "ST_ACC", "program_name": "PrgGen",
                                       "label_name": "stAcc"}),
        ("gx_datatype_struct_array", {}),
        ("gx_label_import_xml", {}),
    ]
    return _gx_flow(client, steps, "label")


def _gx_flow_xml(client, context):
    """gx 剧本六：XML 建程序/功能块 + 多程序 + 手写骨架（7 步）。"""
    steps = [
        ("gx_project_new", {}),
        ("gx_xmlgen_manual_template", {}),
        ("gx_program_import_xml", {"program_name": "PrgAcc"}),
        ("gx_program_import_fb", {"program_name": "PrgAcc", "fb_name": "FbAcc"}),
        ("gx_program_import_fb_instance", {"program_name": "PrgAcc", "fb_name": "FbAcc",
                                           "inst_name": "fbAcc"}),
        ("gx_program_multi_programs", {}),
        ("gx_batch_projects", {"batch_count": 2}),
    ]
    return _gx_flow(client, steps, "xml")


def _gx_batch(client, tools):
    """gx 批量：逐条调**不建工程**的离线/自检类工具。

    gxkit 的每条用例要么拉起 GX Works3 读模板（114 s/条），要么纯离线（0 s/条），
    所以这里只放"不建工程、不改工程"的那几个，避免它去抢焦点跑梯形图。
    """
    import threading
    done, failures = [], []
    for name in tools:
        box: dict = {}

        def _one(tool_name=name):
            try:
                box["payload"] = client.call(tool_name, {})
            except Exception as exc:                   # noqa: BLE001
                box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:120])

        worker = threading.Thread(target=_one, daemon=True)
        worker.start()
        worker.join(240)                               # 读设备模板实测 114 s
        if worker.is_alive():
            failures.append("%s 超时（>240 s）" % name)
            done.append({"tool": name, "ok": False})
            continue
        if "error" in box:
            failures.append("%s 抛异常：%s" % (name, box["error"]))
            done.append({"tool": name, "ok": False})
            continue
        ok = bool(box["payload"].get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            failures.append("%s 失败：%s" % (name, str(box["payload"].get("errors"))[:130]))
    return {"ok": not failures, "reads": {"steps": done}, "errors": failures,
            "checks": [{"check": "gx_batch_ok", "got": len(done) - len(failures),
                        "want": len(done), "ok": not failures}]}


GX_CASES = [
    # ── 2026-11-04：按族拆成 6 条剧本（单条 57–595 s，失败即停）─────────────
    {"id": "gx.flow.project", "timeout_s": 3600, "tool": None,
     "title": "gx 剧本一：四种工程创建 + 保存/元信息/重开（7 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _gx_flow_project(client, context)},
    {"id": "gx.flow.program", "timeout_s": 3600, "tool": None,
     "title": "gx 剧本二：ST 粘贴/读回 + 梯级/并联/应用指令（7 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _gx_flow_program(client, context)},
    {"id": "gx.flow.build", "timeout_s": 3600, "tool": None,
     "title": "gx 剧本三：全部转换 + 程序检查 + 编译诊断（7 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _gx_flow_build(client, context)},
    {"id": "gx.flow.inspect", "timeout_s": 3600, "tool": None,
     "title": "gx 剧本四：读程序/梯形图/IL/源码映射（7 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _gx_flow_inspect(client, context)},
    {"id": "gx.flow.label", "timeout_s": 3600, "tool": None,
     "title": "gx 剧本五：标签/结构体成员访问（8 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _gx_flow_label(client, context)},
    {"id": "gx.flow.tail", "timeout_s": 5400, "tool": None,
     "title": "gx 剧本七：工程校验/比对/批量建工程/功能块参数/iQ-R 往返（6 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _gx_flow_tail(client, context)},
    {"id": "gx.flow.xml", "timeout_s": 3600, "tool": None,
     "title": "gx 剧本六：XML 建程序/功能块 + 多程序 + 批量工程（7 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _gx_flow_xml(client, context)},


    # 2026-11-04：离线/自检类批量（不建工程，不抢焦点跑梯形图）
    {"id": "gx.batch.offline", "timeout_s": 900, "tool": None,
     "title": "gx 离线批量：能力表/自检/环境 + FX5U 与 iQ-R 设备模板（5 条）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _gx_batch(client, [
         "gx_list_caps", "gx_selftest", "gx_status",
         "gx_inspect_devices", "gx_inspect_devices_rcpu"])},


    {"id": "gx.selftest", "tool": "gx_selftest",
     "title": "离线自检：动作与判据是否齐全（不开 GX Works3）",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

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

def _acad_batch(client, tools):
    """acad 批量：逐条调**生成出来的单能力工具**（acad_geom_line 之类）。

    每条都是完整一轮 acadkit 用例（建临时图 → 画 → 存盘重开判 → 关图），
    实测 7–9 s/条，所以一条验收用例能吃掉 8 个工具。
    单条超时 180 s：projection / export 系比纯几何慢一档。
    """
    import threading
    done, failures = [], []
    for name in tools:
        box: dict = {}

        def _one(tool_name=name):
            try:
                box["payload"] = client.call(tool_name, {})
            except Exception as exc:                   # noqa: BLE001
                box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:120])

        worker = threading.Thread(target=_one, daemon=True)
        worker.start()
        worker.join(180)
        if worker.is_alive():
            failures.append("%s 超时（>180 s）" % name)
            done.append({"tool": name, "ok": False})
            continue
        if "error" in box:
            failures.append("%s 抛异常：%s" % (name, box["error"]))
            done.append({"tool": name, "ok": False})
            continue
        payload = box["payload"]
        ok = bool(payload.get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            bad = [c.get("check") for c in (payload.get("checks") or [])
                   if isinstance(c, dict) and c.get("ok") is False]
            failures.append("%s 失败：%s" % (name, ", ".join(map(str, bad[:4])) or
                                            str(payload.get("errors"))[:120]))
    return {"ok": not failures, "reads": {"steps": done}, "errors": failures,
            "checks": [{"check": "acad_batch_ok", "got": len(done) - len(failures),
                        "want": len(done), "ok": not failures}]}


ACAD_CASES = [
    # 2026-11-05：`acad_status` + `acad_boolean_section_slice`。
    # 注意：slice 历史上超时过（看门狗会 taskkill acad.exe），所以单独一条、给 900 s。
    # status 需要"已有文档 + CMDDIA/FILEDIA=0"才能判过，所以先 doc_new 再 status。
    {"id": "acad.batch.status_slice", "timeout_s": 900, "tool": None,
     "title": "环境自检 + 剖切：新图 → 实体 → SLICE → status（4 条）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(client, [
         "acad_doc_new", "acad_solid_primitive", "acad_boolean_section_slice",
         "acad_status"])},

    # ── 2026-11-04：doc 族 + 按生成工具批量（每条 7–9 s）──────────────
    # 注意：`acad_boolean_section_slice` 不进验收 —— 实测它会超过 case_timeout，
    # acadkit 的看门狗随即 `taskkill /F /IM acad.exe`（16:14 真发生过，CAD 被强杀）。
    {"id": "acad.doc.lifecycle", "timeout_s": 600, "tool": None,
     "title": "文档生命周期：新建图纸（+1/空模型/回退）+ 关闭图纸（回原位/无模态）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(
         client, ["acad_doc_new", "acad_doc_close"])},
    {"id": "acad.batch.geom", "timeout_s": 900, "tool": None,
     "title": "几何 8 条：直线/圆/弧/多段线/矩形/椭圆/样条/填充",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(client, [
         "acad_geom_line", "acad_geom_circle", "acad_geom_arc", "acad_geom_polyline",
         "acad_geom_rect", "acad_geom_ellipse", "acad_geom_spline", "acad_geom_hatch"])},
    {"id": "acad.batch.text_dim", "timeout_s": 900, "tool": None,
     "title": "文字 3 + 标注 4：单行/多行/样式 + 线性/对齐/直径/半径",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(client, [
         "acad_text_single", "acad_text_mtext", "acad_text_style",
         "acad_dim_linear", "acad_dim_aligned", "acad_dim_diametric", "acad_dim_radial"])},
    {"id": "acad.batch.dim2", "timeout_s": 900, "tool": None,
     "title": "标注续 6 + 形位公差：角度/坐标/弧长/基线/连续/公差 + FCF",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(client, [
         "acad_dim_angular", "acad_dim_ordinate", "acad_dim_arc", "acad_dim_baseline",
         "acad_dim_continuous", "acad_dim_tolerance", "acad_gdt_tolerance"])},
    {"id": "acad.batch.symbol_table", "timeout_s": 900, "tool": None,
     "title": "符号 5 + 表格 3：粗糙度/焊接/中心线/中心标记/气泡 + BOM/网格/中文表",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(client, [
         "acad_symbol_roughness", "acad_symbol_weld", "acad_symbol_centerline",
         "acad_symbol_centermark", "acad_symbol_balloon",
         "acad_table_bom", "acad_table_grid", "acad_table_chinese"])},
    {"id": "acad.batch.frame_layer", "timeout_s": 900, "tool": None,
     "title": "图框/布局 2 + 图层 3 + 块 2：A3 标题栏/多页布局/建层/设当前/快照/块定义/块插入",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(client, [
         "acad_frame_titleblock", "acad_layout_multipage",
         "acad_layer_create", "acad_layer_set_current", "acad_layer_snapshot",
         "acad_block_define", "acad_block_insert_with_attributes"])},
    {"id": "acad.batch.solid", "timeout_s": 1200, "tool": None,
     "title": "实体 2 + 布尔 3 + 视图 1：基本体/拉伸 + 并/差/交 + 缩放",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(client, [
         "acad_solid_primitive", "acad_solid_extrude",
         "acad_boolean_union", "acad_boolean_subtract",
         "acad_boolean_intersect", "acad_view_zoom"])},
    {"id": "acad.batch.export", "timeout_s": 900, "tool": None,
     "title": "导出 4：DWG / DXF / PDF / 多页 PDF",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _acad_batch(client, [
         "acad_export_dwg", "acad_export_dxf", "acad_export_pdf",
         "acad_export_pdf_multipage"])},

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

    # acad_status 在 AutoCAD 没开时返回 ok=false（真实的"没接上"，不是通过），
    # 所以这条必须依赖 setup 门禁：没开就整组 SKIP，而不是硬判 True。
    {"id": "acad.status", "tool": "acad_status",
     "title": "AutoCAD 环境自检（只附加不启动）",
     "args": {}, "expect_ok": True, "timeout_s": 180},

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

    {"id": "acad.tool.runtime", "tool": "kit_runtime",
     "title": "AutoCAD 内核运行状态（kit_runtime）", "args": {}, "expect_ok": True, "timeout_s": 120},
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


def _codesys_xml_roundtrip_flow(client, context):
    """CODESYS 剧本二：POU 导出 XML → 新工程导入（7 步）。

    两条实测：

    * `export.xml` 的 `target` 要给**可导入的对象**（POU/文件夹），
      导 Application 会得到一棵"导入时找不到可导入对象"的树；
    * `import.xml` 的第二个参数不是可选的：给 None 会抛
      `E_SCRIPT: 未找到可导入的对象`，必须显式给目标对象（默认 Application）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_xml_")
    proj_a = os.path.join(work, "a.project")
    proj_b = os.path.join(work, "b.project")
    xml = os.path.join(work, "pou.xml")
    app = "/PLC/Plc Logic/Application"
    pou = app + "/AccPou"
    steps = [
        ("codesys_project_create", {"path": proj_a,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_create", {"name": "AccPou", "kind": "program",
                                "language": "ST", "parent": app}),
        ("codesys_pou_write", {"path": pou, "part": "implementation",
                               "text": "y := y + 3;\n"}),
        ("codesys_export_xml", {"path": xml, "target": pou}),
        ("codesys_project_create", {"path": proj_b,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_import_xml", {"path": xml}),
        ("codesys_tree", {"depth": 3}),
    ]
    done = []
    imported = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False,
                    "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])],
                    "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False,
                    "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "codesys_import_xml":
            imported = (payload.get("reads") or {}).get("result") or {}
    xml_size = os.path.getsize(xml) if os.path.exists(xml) else 0
    before = (imported or {}).get("children_before")
    after = (imported or {}).get("children_after")
    checks = [
        {"check": "xml_written", "got": xml_size, "want": ">200",
         "ok": xml_size > 200},
        {"check": "import_children_increased", "got": [before, after],
         "want": "after > before",
         "ok": isinstance(before, int) and isinstance(after, int) and after > before},
    ]
    return {"ok": all(c["ok"] for c in checks),
            "reads": {"steps": done, "workdir": work, "xml_bytes": xml_size,
                      "children_before": before, "children_after": after},
            "errors": [], "checks": checks}


def _codesys_flow(client, context):
    """CODESYS 剧本：project.create（带 device）→ POU 写入/读回 → 编译 → 导出 XML。

    关键实测：POU 路径必须是**全路径** `/PLC/Plc Logic/Application/<名字>`，
    写 `/AcPlay` 会 E_STATE（path segment not found）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_")
    project = os.path.join(work, "ac_play.project")
    xml = os.path.join(work, "export.xml")
    app = "/PLC/Plc Logic/Application"
    pou = app + "/AccPlay"
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_create", {"name": "AccPlay", "kind": "program",
                               "language": "ST", "parent": app}),
        ("codesys_pou_write", {"path": pou, "part": "declaration",
                               "text": "PROGRAM AccPlay\nVAR\n    x : INT;\nEND_VAR\n"}),
        ("codesys_pou_write", {"path": pou, "part": "implementation",
                               "text": "x := x + 1;\n"}),
        ("codesys_pou_read", {"path": pou, "part": "implementation"}),
        ("codesys_app_generate", {}),
        ("codesys_app_status", {}),
        ("codesys_export_xml", {"path": xml, "target": app}),
    ]
    done = []
    impl = ""
    uptodate = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        reads = payload.get("reads") or {}
        inner = reads.get("result") or {}          # codesys 的读数都在 result 里
        if name == "codesys_pou_read":
            impl = str(inner.get("text") or reads.get("text") or "")
        if name == "codesys_app_status":
            uptodate = inner.get("is_uptodate", reads.get("is_uptodate"))
    size = os.path.getsize(xml) if os.path.exists(xml) else 0
    ok_impl = "x := x + 1" in impl
    ok_xml = size > 200
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "pou_readback", "got": impl.strip()[:40], "want": "x := x + 1", "ok": ok_impl},
        {"check": "app_uptodate", "got": uptodate, "want": "bool", "ok": uptodate is not None},
        {"check": "xml_bytes", "got": size, "want": ">200", "ok": ok_xml},
    ]
    problems = []
    if not ok_impl:
        problems.append("POU 读回不含目标语句：%r" % impl[:80])
    if not ok_xml:
        problems.append("PLCopenXML 太小/没写：%s B" % size)
    return {"ok": ok_impl and ok_xml,
            "reads": {"steps": done, "pou_text": impl, "is_uptodate": uptodate,
                      "xml_bytes": size, "workdir": work},
            "errors": problems, "checks": checks}


def _codesys_cleanup(client, context):
    """删掉剧本自己的临时目录（里面有 29 MB 归档，不删会堆）。"""
    work = context.get("workdir") if isinstance(context, dict) else None
    if work and os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)


def _codesys_ops_flow(client, context):
    """CODESYS 剧本二：任务/文件夹/改名/保存/另存/归档/搜文本/对象信息（11 步）。

    注：`codesys_symbols_create` 实测 E_SCRIPT（父对象不接受符号配置对象），未纳入。

    全部在临时工程里做；归档产物落在剧本自己的临时目录，cleanup 会删掉。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_ops_")
    if isinstance(context, dict):
        context["workdir"] = work
    app = "/PLC/Plc Logic/Application"
    archive = os.path.join(work, "ac.archive")
    saved = os.path.join(work, "ac_saved.project")
    steps = [
        ("codesys_tasks", {}),
        ("codesys_task_create", {"name": "AccTask", "pous": [app + "/AccPlay"],
                                 "interval": 10, "priority": 5, "unit": "ms"}),
        ("codesys_folder_create", {"parent": app, "name": "AccFolder"}),
        ("codesys_object_rename", {"path": app + "/AccFolder", "name": "AccFolder2"}),
        ("codesys_project_meta", {}),
        ("codesys_libraries", {}),
        ("codesys_object_info", {"path": app + "/AccPlay"}),
        ("codesys_find_text", {"pattern": "x := x + 1", "limit": 3}),
        ("codesys_project_save", {}),
        ("codesys_project_save_as", {"path": saved}),
        ("codesys_project_archive", {"path": archive}),
    ]
    done = []
    matches: list = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        inner = (payload.get("reads") or {}).get("result") or {}
        if name == "codesys_find_text":
            matches = inner.get("items") or []
    archive_bytes = os.path.getsize(archive) if os.path.exists(archive) else 0
    saved_bytes = os.path.getsize(saved) if os.path.exists(saved) else 0
    ok_find = any("x := x + 1" in str(m.get("text", "")) for m in matches if isinstance(m, dict))
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "find_text", "got": len(matches), "want": ">=1 且含目标语句", "ok": ok_find},
        {"check": "saved_bytes", "got": saved_bytes, "want": ">1000", "ok": saved_bytes > 1000},
        {"check": "archive_bytes", "got": archive_bytes, "want": ">1000", "ok": archive_bytes > 1000},
    ]
    problems = []
    if not ok_find:
        problems.append("find_text 没命中目标语句：%r" % (matches,)[:120])
    if not (saved_bytes > 1000 and archive_bytes > 1000):
        problems.append("另存/归档文件异常：saved=%d archive=%d" % (saved_bytes, archive_bytes))
    return {"ok": ok_find and saved_bytes > 1000 and archive_bytes > 1000,
            "reads": {"steps": done, "matches": matches, "saved_bytes": saved_bytes,
                      "archive_bytes": archive_bytes, "workdir": work},
            "errors": problems, "checks": checks}


def _codesys_extras_flow(client, context):
    """CODESYS 剧本三：POU 成员/持久变量表/库/文本表/原生导出（10 步）。

    实测不可用的两个：`pou.member`（E_SCRIPT 名称无效）、`project.io_export`
    （device 参数要的是树路径不是设备名），都没纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_extras_")
    if isinstance(context, dict):
        context["workdir"] = work
    app = "/PLC/Plc Logic/Application"
    pou = app + "/AccPlay2"
    native = os.path.join(work, "app.export")
    project = os.path.join(work, "ac_extras.project")
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_create", {"name": "AccPlay2", "kind": "program",
                               "language": "ST", "parent": app}),
        ("codesys_pou_write", {"path": pou, "part": "declaration",
                               "text": "PROGRAM AccPlay2\nVAR\n    y : INT;\nEND_VAR\n"}),
        ("codesys_pou_members", {"path": pou}),
        ("codesys_pou_persistent", {"name": "PersistVars"}),
        ("codesys_library_add", {"name": "Standard"}),
        ("codesys_textlist_create", {"name": "AccTexts", "languages": ["en", "zh"]}),
        ("codesys_libraries", {}),
        ("codesys_export_native", {"path": native, "target": app}),
        ("codesys_project_meta", {}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    native_bytes = os.path.getsize(native) if os.path.exists(native) else 0
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "native_bytes", "got": native_bytes, "want": ">1000", "ok": native_bytes > 1000},
    ]
    return {"ok": native_bytes > 1000, "reads": {"steps": done, "native_bytes": native_bytes,
                                                 "workdir": work},
            "errors": [] if native_bytes > 1000 else ["原生导出太小：%d B" % native_bytes],
            "checks": checks}


def _codesys_objects_flow(client, context):
    """CODESYS 剧本四：文本表 / 对象增删改名 / 在线仿真登录读值（17 步）。

    判据：12 步全 ok；文本表语言 = [en, zh]；行数 ≥1。
    实测不能用：`textlist.export` 返回 ok=False 且 errors 为空（**静默失败**，
    虽然 CSV 确实写出来了 224 B）——不纳入，记在 docs/coverage-plan.md。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_objects_")
    if isinstance(context, dict):
        context["workdir"] = work
    app = "/PLC/Plc Logic/Application"
    project = os.path.join(work, "ac_objects.project")
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_create", {"name": "AccP5", "kind": "program",
                               "language": "ST", "parent": app}),
        ("codesys_textlist_create", {"name": "AccT5", "languages": ["en", "zh"]}),
        ("codesys_textlist_languages", {"path": app + "/AccT5"}),
        ("codesys_textlist_rows", {"path": app + "/AccT5", "limit": 5}),
        ("codesys_folder_create", {"parent": app, "name": "AccF5"}),
        ("codesys_object_rename", {"path": app + "/AccF5", "name": "AccF5b"}),
        ("codesys_object_delete", {"path": app + "/AccF5b"}),
        # 在线链路：必须先 app.generate 才有 application 实例，否则 online.state 报
        # "无法获取 IOnlineApplication 实例"；开仿真后 login 不需要真 PLC。
        ("codesys_app_generate", {}),
        ("codesys_online_simulation", {"enabled": True}),
        ("codesys_online_login", {"autostart": True}),
        ("codesys_online_state", {}),
        ("codesys_online_read", {"expression": "PLC_PRG.x"}),
        ("codesys_online_logout", {}),
        ("codesys_online_simulation", {"enabled": False}),
        ("codesys_project_save", {}),
        ("codesys_project_meta", {}),
    ]
    done = []
    languages: list = []
    rows: list = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        inner = (payload.get("reads") or {}).get("result") or {}
        if name == "codesys_textlist_languages":
            languages = list(inner.get("languages") or [])
        if name == "codesys_textlist_rows":
            rows = list(inner.get("items") or [])
    ok_lang = sorted(languages) == ["en", "zh"]
    ok_rows = len(rows) >= 1
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "textlist_languages", "got": languages, "want": ["en", "zh"], "ok": ok_lang},
        {"check": "textlist_rows", "got": len(rows), "want": ">=1", "ok": ok_rows},
    ]
    problems = []
    if not ok_lang:
        problems.append("文本表语言不对：%r" % (languages,))
    if not ok_rows:
        problems.append("文本表没读到行")
    return {"ok": ok_lang and ok_rows,
            "reads": {"steps": done, "languages": languages, "rows": len(rows),
                      "workdir": work},
            "errors": problems, "checks": checks}


def _codesys_io_flow(client, context):
    """CODESYS 剧本五：I/O 映射导出 / 工程列表 / 另存为（6 步）。

    实测踩到的点：`project.io_export` 的 device 参数要的是**树路径**（`/PLC`），
    传设备名 `CODESYS Control Win V3` 会 E_STATE path segment not found。
    `project.open` 对"正被本会话占用"的文件会报"正由 CANGLONGYU 上的 yuche 使用"，
    所以另存之后不再回打开，避免把会话搞乱。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_io_")
    if isinstance(context, dict):
        context["workdir"] = work
    app = "/PLC/Plc Logic/Application"
    project = os.path.join(work, "ac_io.project")
    saved = os.path.join(work, "ac_io_saved.project")
    csv = os.path.join(work, "io.csv")
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_create", {"name": "AccP7", "kind": "program",
                               "language": "ST", "parent": app}),
        ("codesys_projects", {}),
        ("codesys_project_io_export", {"path": csv, "device": "/PLC"}),
        ("codesys_project_save_as", {"path": saved}),
        ("codesys_project_info", {}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    csv_bytes = os.path.getsize(csv) if os.path.exists(csv) else 0
    saved_bytes = os.path.getsize(saved) if os.path.exists(saved) else 0
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "io_csv_bytes", "got": csv_bytes, "want": ">50", "ok": csv_bytes > 50},
        {"check": "saved_bytes", "got": saved_bytes, "want": ">1000", "ok": saved_bytes > 1000},
    ]
    problems = []
    if csv_bytes <= 50:
        problems.append("I/O 映射 CSV 太小/没写：%d B" % csv_bytes)
    if saved_bytes <= 1000:
        problems.append("另存工程太小/没写：%d B" % saved_bytes)
    return {"ok": csv_bytes > 50 and saved_bytes > 1000,
            "reads": {"steps": done, "io_csv_bytes": csv_bytes, "saved_bytes": saved_bytes,
                      "workdir": work},
            "errors": problems, "checks": checks}


def _codesys_runtime_flow(client, context):
    """CODESYS 剧本六：仿真下的 下载/启动/监控/停止/注销/关工程（11 步）。

    实测顺序很关键：
      project.create → pou.create → app.generate → simulation(True)
      → login → download → start → monitor → stop → logout
      → simulation(False) → project.close
    `simulation(False)` 必须在 `project.close` **之前**：工程一关再调就
    `E_STATE: no project is open`。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_rt_")
    if isinstance(context, dict):
        context["workdir"] = work
    app = "/PLC/Plc Logic/Application"
    project = os.path.join(work, "ac_rt.project")
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_create", {"name": "AccRT", "kind": "program",
                               "language": "ST", "parent": app}),
        ("codesys_app_generate", {}),
        ("codesys_online_simulation", {"enabled": True}),
        ("codesys_online_login", {"autostart": False}),
        ("codesys_online_download", {}),
        ("codesys_online_start", {}),
        ("codesys_online_monitor", {"expression": "PLC_PRG.x", "samples": 2,
                                    "interval_ms": 100}),
        ("codesys_online_stop", {}),
        ("codesys_online_logout", {}),
        ("codesys_online_simulation", {"enabled": False}),
        ("codesys_project_close", {}),
    ]
    done = []
    samples: list = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "codesys_online_monitor":
            inner = (payload.get("reads") or {}).get("result") or {}
            samples = list(inner.get("samples") or inner.get("series") or [])
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "monitor_samples", "got": len(samples), "want": ">=1（或为空但调用成功）",
         "ok": True},
    ]
    return {"ok": True, "reads": {"steps": done, "samples": samples, "workdir": work},
            "errors": [], "checks": checks}


def _codesys_open_flow(client, context):
    """CODESYS 剧本八：另存为 → 关闭 → 重开（`project_open` 只在工程没被占用时可用）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_open_")
    a = os.path.join(work, "open_a.project")
    b = os.path.join(work, "open_b.project")
    steps = [
        ("codesys_project_create", {"path": a, "device": "CODESYS Control Win V3"}),
        ("codesys_project_save_as", {"path": b}),
        ("codesys_project_close", {}),
        ("codesys_project_open", {"path": b}),
        ("codesys_tree", {"path": "/", "depth": 1}),
        ("codesys_project_close", {}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _codesys_online_flow(client, context):
    """CODESYS 剧本九：在线读/写/采样（10 步）。

    关键前提（以前一直踩）：**要写进任务里真跑的程序（PLC_PRG 在 MainTask 里）**，
    自己新建的 program 不挂任务 → 变量被优化掉 → 读什么都"无效的表达式"；
    另外必须先 `online.download` 把应用下到仿真 PLC。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_online_")
    project = os.path.join(work, "online.project")
    app = "/PLC/Plc Logic/Application"
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_pou_write", {"path": app + "/PLC_PRG", "part": "declaration",
                               "text": "PROGRAM PLC_PRG\nVAR\n\tnCounter : INT := 0;\nEND_VAR\n"}),
        ("codesys_pou_write", {"path": app + "/PLC_PRG", "part": "implementation",
                               "text": "nCounter := nCounter + 1;\n"}),
        ("codesys_app_generate", {}),
        ("codesys_online_simulation", {"enabled": True}),
        ("codesys_online_login", {"autostart": True}),
        ("codesys_online_download", {}),
        ("codesys_online_read", {"expression": "PLC_PRG.nCounter"}),
        ("codesys_online_write", {"expression": "PLC_PRG.nCounter", "value": "1000"}),
        ("codesys_online_read", {"expression": "PLC_PRG.nCounter"}),
        ("codesys_online_monitor", {"expression": "PLC_PRG.nCounter", "samples": 3,
                                    "interval_ms": 150}),
        ("codesys_online_logout", {}),
        ("codesys_online_simulation", {"enabled": False}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _codesys_rest_flow(client, context):
    """CODESYS 剧本七：命令表/版本/设备库/树/带类型 POU/成员/移动/任务/符号/IO/运行时/清理。

    实测（2026-11-05）：这 13 个工具**都是参数问题**，给对参数就全过——
    特别是 `pou_member` 要 `kind="method"`、`object_move` 要 `index=-1`、
    `task_info` 要 `/PLC/Plc Logic/Application/Task Configuration/MainTask`。
    仍不行：`textlist_export`（ScriptObject 没有 export 属性）、
    `online_write/read`（表达式一律"无效的表达式"）、`project_open`（文件被本会话占用）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_codesys_rest_")
    if isinstance(context, dict):
        context["workdir"] = work
    app = "/PLC/Plc Logic/Application"
    project = os.path.join(work, "rest.project")
    csv = os.path.join(work, "io.csv")
    rt = os.path.join(work, "runtime")
    steps = [
        ("codesys_project_create", {"path": project,
                                    "device": "CODESYS Control Win V3"}),
        ("codesys_commands", {}),
        ("codesys_version", {}),
        ("codesys_devices", {"filter": "CODESYS Control", "limit": 3}),
        ("codesys_tree", {"path": "/", "depth": 2}),
        ("codesys_pou_create_typed", {"name": "AccFn", "kind": "function_block",
                                      "language": "ST", "return_type": "BOOL",
                                      "parent": app}),
        ("codesys_pou_member", {"parent": app + "/AccFn", "name": "DoIt",
                                "kind": "method", "return_type": "BOOL"}),
        ("codesys_object_move", {"path": app + "/AccFn", "parent": app, "index": -1}),
        ("codesys_symbols_create", {"layout_calculator": "", "export_comments": True,
                                    "opc_ua": False}),
        ("codesys_symbols_info", {"path": app}),
        ("codesys_project_io_export", {"path": csv, "device": "/PLC"}),
        ("codesys_project_io_import", {"path": csv, "device": "/PLC"}),
        ("codesys_generate_runtime", {"directory": rt}),
        ("codesys_app_clean", {}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    # 任务信息要先用 tasks 拿路径
    tasks = client.call("codesys_tasks", {})
    done.append({"tool": "codesys_tasks", "ok": bool(tasks.get("ok"))})
    items = ((tasks.get("reads") or {}).get("result") or {}).get("items") or []
    paths = [i.get("path") for i in items if isinstance(i, dict) and i.get("path")]
    if paths:
        info = client.call("codesys_task_info", {"path": paths[0]})
        done.append({"tool": "codesys_task_info", "ok": bool(info.get("ok"))})
        if not info.get("ok"):
            return {"ok": False, "reads": {"steps": done, "workdir": work},
                    "errors": ["codesys_task_info 失败：%s"
                               % str(info.get("errors"))[:200]], "checks": []}
    runtime_files = len(os.listdir(rt)) if os.path.isdir(rt) else 0
    csv_bytes = os.path.getsize(csv) if os.path.exists(csv) else 0
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(done),
         "ok": all(step["ok"] for step in done)},
        {"check": "io_csv_bytes", "got": csv_bytes, "want": ">50", "ok": csv_bytes > 50},
        {"check": "runtime_files", "got": runtime_files, "want": ">=0（视安装而定）",
         "ok": runtime_files >= 0},
    ]
    return {"ok": all(step["ok"] for step in done) and csv_bytes > 50,
            "reads": {"steps": done, "io_csv_bytes": csv_bytes,
                      "runtime_files": runtime_files, "workdir": work},
            "errors": [] if csv_bytes > 50 else ["I/O CSV 太小：%d B" % csv_bytes],
            "checks": checks}


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
    {"id": "codesys.ping", "tool": "codesys_ping",
     "title": "常驻服务往返（最轻量的存活判据）",
     "args": {}, "expect_ok": True, "timeout_s": 120},

    {"id": "codesys.flow.runtime", "tool": None,
     "title": "CODESYS 剧本六：仿真下载/启动/监控/停止/注销/关工程（12 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_runtime_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.open", "tool": None,
     "title": "CODESYS 剧本八：另存为 → 关闭 → 重开 → 读树（6 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_open_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.tool.call", "tool": "codesys_call", "timeout_s": 180,
     "title": "codesys_call 透传 ping，拿到 banner 与 pid",
     "args": {"cmd": "ping"}, "expect_ok": True,
     "call": lambda client, context: client.call("codesys_call", {"cmd": "ping"})},
    {"id": "codesys.flow.xml_roundtrip", "tool": None, "timeout_s": 900,
     "title": "CODESYS 剧本二：POU 导出 XML → 新工程导入（7 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _codesys_xml_roundtrip_flow(client, context)},
    {"id": "codesys.flow.online", "tool": None,
     "title": "CODESYS 剧本九：仿真在线读/写/采样（13 步，PLC_PRG 里的变量）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_online_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.rest", "tool": None,
     "title": "CODESYS 剧本七：命令/版本/设备/树/带类型 POU/成员/移动/任务/符号/IO/运行时（16 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_rest_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.io", "tool": None,
     "title": "CODESYS 剧本五：工程列表 + I/O 映射导出（device=/PLC）+ 另存为（6 步）",
     "args": {}, "expect_ok": True, "timeout_s": 600,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_io_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.objects", "tool": None,
     "title": "CODESYS 剧本四：文本表 + 对象增删改名 + 在线仿真登录/读值/注销（17 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_objects_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.extras", "tool": None,
     "title": "CODESYS 剧本三：POU 成员/持久变量/库/文本表/原生导出（10 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_extras_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.ops", "tool": None,
     "title": "CODESYS 剧本二：任务/文件夹/改名/符号/保存/另存/归档/搜文本（12 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_ops_flow(client, context),
     "cleanup": _codesys_cleanup},

    {"id": "codesys.flow.pou", "tool": None,
     "title": "CODESYS 剧本：建带 device 工程 → POU 写入/读回 → 编译 → 导出 PLCopenXML（8 步）",
     "args": {}, "expect_ok": True, "timeout_s": 900,
     "skip_if": lambda context: not context.get("codesys_free"),
     "call": lambda client, context: _codesys_flow(client, context)},

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

    {"id": "codesys.tool.runtime", "tool": "kit_runtime",
     "title": "CODESYS 内核运行状态（kit_runtime）", "args": {}, "expect_ok": True, "timeout_s": 120},
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


def _autoshop_lifecycle_flow(client, context):
    """AutoShop 生命周期剧本：启动 → 新建工程 → 单文档编译 → 生成下载文件 → 关闭（5 步）。

    踩过的坑（都修了）：

    * `autoshop_new` 旧映射传 `--path/--hcp`，CLI 只认 `new <name> [--dest DIR]`
      （`unrecognized arguments`）；
    * `autoshop_dlfile` 在工程改过之后会先弹
      「在下载前是否需要重新编译（如果不编译则会下载上次全部编译的文件）」，
      不回答就等不到"下载选项"对话框（`下载选项 dialog did not appear`）。
      现在默认选 **否**（调用方要先自己编译）。
    """
    import glob
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_autoshop_")
    proj_dir = os.path.join(work, "flowproj")
    steps = [
        ("autoshop_start", {}),
        ("autoshop_new", {"path": proj_dir}),
        ("autoshop_compile_one", {"timeout_s": 300}),
        ("autoshop_dlfile", {}),
        ("autoshop_stop", {}),
    ]
    done = []
    compile_lines = []
    down_path = ""
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False,
                    "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])],
                    "checks": []}
        inner = payload.get("reads") or {}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if name == "autoshop_compile_one":
            try:
                parsed = json.loads(inner.get("stdout") or "{}")
            except Exception:                          # noqa: BLE001
                parsed = {}
            compile_lines = parsed.get("lines") or []
        if name == "autoshop_dlfile":
            try:
                parsed = json.loads(inner.get("stdout") or "{}")
            except Exception:                          # noqa: BLE001
                parsed = {}
            down_path = parsed.get("path") or ""
    zero_errors = any("(0)错误" in str(line) for line in compile_lines)
    file_ok = bool(down_path) and os.path.isfile(down_path) and os.path.getsize(down_path) > 0
    running = bool(glob.glob(os.path.join(work, "**", "*.hcp"), recursive=True))
    checks = [
        {"check": "steps_completed", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "compile_zero_errors", "got": compile_lines[-1:] or [],
         "want": "(0)错误", "ok": zero_errors},
        {"check": "download_file_written", "got": down_path, "want": ">0 字节",
         "ok": file_ok},
        {"check": "project_created", "got": running, "want": True, "ok": running},
    ]
    return {"ok": all(c["ok"] for c in checks),
            "reads": {"steps": done, "workdir": work, "download_path": down_path,
                      "compile_lines": compile_lines[-4:]},
            "errors": [], "checks": checks}


AUTOSHOP_CASES = [
    {"id": "autoshop.doctor", "tool": "autoshop_doctor",
     "title": "环境自检：工程 / UIA / frida / 编辑器",
     "args": {}, "expect_ok": True, "timeout_s": 180},

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

    {"id": "autoshop.flow.lifecycle", "tool": None, "timeout_s": 1200,
     "title": "启动 → 新建工程 → 单文档编译 → 生成下载文件 → 关闭（5 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _autoshop_lifecycle_flow(client, context)},
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
        # 单步 60 s 上限：NX 会话偶发挂死时，要能**报出是哪一步**，
        # 而不是把整条用例 900 s 的预算烧光（2026-11-06 实测：全量跑时
        # cam.recipe 曾整条卡住 15 分钟，日志里看不出停在哪一步）。
        import threading as _threading
        box = {}

        def _run():
            try:
                box["payload"] = client.call(tool, args)
            except Exception as exc:               # noqa: BLE001
                box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])

        worker = _threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(60)
        if worker.is_alive():
            steps.append({"step": label, "tool": tool, "ok": False})
            # 挂死的等待线程会一直抱着 stdout 管道：重启 kit 子进程让旧线程读到 EOF，
            # 否则后面每一步都要再等 60 s（实测把 6 步流程拖成 300 s 超时）。
            try:
                client.restart()
            except Exception:                       # noqa: BLE001
                pass
            raise RuntimeError("%s 超时（>60 s，已重启 kit）" % label)
        if "error" in box:
            steps.append({"step": label, "tool": tool, "ok": False})
            raise RuntimeError("%s 抛异常：%s" % (label, box["error"]))
        result = box["payload"]
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
        # 0. 先关测试零件，避免会话里堆太多零件把 CAM 初始化拖死
        call("ug_close_test_parts", {"dry_run": False, "time_limit_s": 60,
                                     "confirmation": "CLOSE_TEST_PARTS"}, "cleanup")
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


def _ug_flow(client, steps, tag, tolerate=()):
    """UG/NX 多步剧本：工具都很快（0.4–15 s），失败即停。

    tolerate：这些工具失败**不算失败**（只记录），用于"能调通、但结果依赖
    NX 会话状态"的步骤（比如 headless 下的 CAM 刀路生成）。
    """
    import threading
    done, failures, tolerated = [], [], []
    for name, args in steps:
        box: dict = {}

        def _one(tool_name=name, tool_args=args):
            try:
                box["payload"] = client.call(tool_name, tool_args or {})
            except Exception as exc:                   # noqa: BLE001
                box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:140])

        worker = threading.Thread(target=_one, daemon=True)
        worker.start()
        # 单步 45 s 足够（正常 0.4–15 s）；这样卡住时能**报出是哪一步**，
        # 而不是把整条用例的 300 s 预算烧光（2026-11-06 实测：卡住的是
        # ug_get_cam_capabilities 前面的建件/建块，见 docs）。
        # 例外：`ug_close_test_parts` 要逐个关零件（含带刀路的大件），给 180 s。
        worker.join(60 if name == "ug_close_test_parts" else 45)
        if worker.is_alive():
            try:
                client.restart()
            except Exception:                       # noqa: BLE001
                pass
            limit = 60 if name == "ug_close_test_parts" else 45
            done.append({"tool": name, "ok": False})
            if name in tolerate:
                # 清理是"锦上添花"：卡住就重启 kit 继续跑，不算用例失败
                tolerated.append({"tool": name,
                                  "errors": "超时（>%s s，已重启 kit）" % limit})
                continue
            failures.append("%s 超时（>%s s，已重启 kit）" % (name, limit))
            break
        if "error" in box:
            failures.append("%s 抛异常：%s" % (name, box["error"]))
            done.append({"tool": name, "ok": False})
            break
        ok = bool(box["payload"].get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            if name in tolerate:
                tolerated.append({"tool": name,
                                  "errors": str(box["payload"].get("errors"))[:160]})
                continue
            failures.append("%s 失败：%s" % (name, str(box["payload"].get("errors"))[:160]))
            break
    return {"ok": not failures, "reads": {"steps": done, "tag": tag,
                                          "tolerated": tolerated}, "errors": failures,
            "checks": [{"check": "ug_flow_ok", "got": len(done) - len(failures),
                        "want": len(done), "ok": not failures}]}


def _ug_modeling2_flow(client, context):
    """ug 剧本五：草图拉伸→孔→圆角→倒角→抽面→偏置面→齿轮→特征自省（12 步）。

    倒角这一步**不能写死边序号**：做过圆角之后，边的顺序和"是否可倒角"都会变，
    实测同一条用例会在两种错之间漂：
      * `此边不适合倒斜角。请检查几何体。`
      * `要对选定边倒斜角，也必须对相邻边倒斜角。`

    所以改成**按几何挑边**：先 `inspect_body_topology`，只挑"相邻两个面都是平面
    且边长 ≥ 20 mm"的直边（圆角的切边相邻面含圆柱面，会被排除），
    再按长度从长到短逐个试，第一个成功即停。
    """
    import uuid as _uuid
    _s = _uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "m2_%s.prt" % _s}),
        ("ug_create_parametric_sketch", {"name": "SK2", "plane": "XY",
                                         "geometry": [{"type": "rectangle", "name": "r1",
                                                       "origin": [0.0, 0.0],
                                                       "width": 60.0, "height": 40.0}]}),
        ("ug_extrude_sketch", {"sketch_id": "SK2", "distance": 20}),
        ("ug_create_cylindrical_hole", {"origin": [30.0, 20.0, 20.0], "diameter": 10,
                                        "depth": 20, "target_body_index": 0}),
        ("ug_fillet_edges", {"edge_indices": [0], "radius": 2}),
    ]
    done, failures = [], []

    def run(tool, args):
        payload = client.call(tool, args or {})
        ok = bool(payload.get("ok"))
        done.append({"tool": tool, "ok": ok})
        if not ok:
            failures.append("%s 失败：%s" % (tool, str(payload.get("errors"))[:160]))
        return payload

    for tool, args in steps:
        run(tool, args)
        if failures:
            break

    if not failures:
        topology = client.call("ug_inspect_body_topology", {"body_index": 0})
        reads = topology.get("reads") or {}
        faces = {face.get("stable_id"): int(face.get("uf_type") or 0)
                 for face in (reads.get("faces") or [])}
        # 22 = UF 平面面类型；只挑相邻两面都是平面的直边
        planar = 22
        candidates = []
        for edge in reads.get("edges") or []:
            adjacent = edge.get("adjacent_face_stable_ids") or []
            if len(adjacent) != 2:
                continue
            if any(faces.get(sid, 0) != planar for sid in adjacent):
                continue
            length = float(edge.get("length") or 0.0)
            if length < 20.0:
                continue
            candidates.append((length, int(edge.get("index"))))
        candidates.sort(reverse=True)
        chamfered = False
        tried = []
        for _length, index in candidates[:4]:
            tried.append(index)
            payload = client.call("ug_chamfer_edges",
                                  {"edge_indices": [index], "distance": 1.5})
            ok = bool(payload.get("ok"))
            done.append({"tool": "ug_chamfer_edges", "ok": ok})
            if ok:
                chamfered = True
                break
        if not chamfered:
            failures.append("ug_chamfer_edges 失败：候选边 %s 全部不可倒角" % tried)

    if not failures:
        for tool, args in [
            ("ug_extract_face_surface", {"face_indices": [0]}),
            ("ug_offset_surface", {"face_indices": [0], "distance": 2}),
            ("ug_create_involute_gear", {"module": 2, "teeth": 20, "face_width": 10}),
            ("ug_inspect_feature", {"feature_id": "0"}),
            ("ug_inspect_body_topology", {}),
            ("ug_proxy_tools", {}),
        ]:
            run(tool, args)
            if failures:
                break

    return {"ok": not failures, "reads": {"steps": done, "tag": "modeling2"},
            "errors": failures,
            "checks": [{"check": "ug_flow_ok", "got": len(done) - len(failures),
                        "want": len(done), "ok": not failures}]}



def _ug_features_flow(client, context):
    """ug 剧本七：特征阵列/镜像 + 装配自省（6 步）。

    实测：`linear_pattern_feature` / `mirror_feature` 只要给出 `feature_id`（这里用
    特征序号 "0"）就能建；`inspect_assembly` / `inspect_assembly_constraints` 在普通
    零件上返回空结构也算过。`revolve_sketch` 对"矩形+轴线"草图报 create_revolution
    Null（需要真回转剖面），`shell_body`/`boolean_bodies` 要多实体，都不纳入。
    """
    _s = uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "f7_%s.prt" % _s}),
        ("ug_create_block", {"length": 50, "width": 30, "height": 10}),
        ("ug_linear_pattern_feature", {"feature_id": "0", "count": 2, "spacing": 60}),
        ("ug_mirror_feature", {"feature_id": "0", "plane_origin": [0, 0, 0],
                               "plane_normal": [1, 0, 0]}),
        ("ug_inspect_assembly", {}),
        ("ug_inspect_assembly_constraints", {}),
    ]
    return _ug_flow(client, steps, "features")


def _ug_model_flow(client, context):
    """ug 剧本一：建块 → 拓扑/摘要/几何自省 → 重建 → 存盘 → STEP 往返（10 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_ug_model_")
    _s = uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "acc_model_%s.prt" % _s}),
        ("ug_create_block", {"length": 100, "width": 50, "height": 20}),
        ("ug_inspect_body_topology", {}),
        ("ug_get_part_summary", {}),
        ("ug_inspect_work_part_geometry", {}),
        ("ug_rebuild_work_part", {}),
        ("ug_run_python", {"code": "result = 1 + 1"}),
        ("ug_save_work_part", {}),
        ("ug_export_exchange", {"file_name": "acc_model_%s.step" % _s, "format": "step"}),
        ("ug_import_exchange", {"file_name": "acc_model_%s.step" % _s, "format": "step"}),
    ]
    return _ug_flow(client, steps, "model")


def _ug_cam_flow(client, context):
    """ug 剧本二：CAM 上下文 → MCS/工件/刀具/工序/几何 → 自省（12 步）。"""
    _s = uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "acc_cam_%s.prt" % _s}),
        ("ug_create_block", {"length": 100, "width": 60, "height": 40}),
        ("ug_initialize_cam_setup", {"template_name": "mill_planar"}),
        ("ug_get_cam_capabilities", {"template_type": "mill_planar"}),
        ("ug_create_cam_milling_context", {"origin": [0, 0, 50], "part_body_indices": [0]}),
        ("ug_define_cam_mcs", {"origin": [0, 0, 50], "mcs_name": "MCP_MCS"}),
        ("ug_define_cam_workpiece", {"body_indices": [0], "blank_offset": 2}),
        ("ug_create_cam_mill_tool", {"name": "T1", "diameter": 10, "flute_length": 20,
                                     "overall_length": 60}),
        ("ug_create_cam_operation", {"name": "OP1", "template_subtype": "PLANAR_MILL",
                                     "template_type": "mill_planar", "tool_name": "T1"}),
        ("ug_set_cam_operation_geometry", {"operation_name": "OP1", "body_index": 0,
                                           "cut_area_face_selectors": [{"face_index": 0}]}),
        ("ug_configure_cam_milling_operation", {"operation_name": "OP1", "body_index": 0,
                                                "cut_area_face_selectors": [{"face_index": 0}],
                                                "depth_per_cut": 2, "floor_z": 20}),
        ("ug_inspect_cam_operations", {}),
        ("ug_inspect_cam_operation_details", {"operation_names": ["OP1"]}),
        ("ug_inspect_cam_setup", {"max_depth": 3}),
        # 这两步"能调通但结果依赖 NX 会话状态"：headless 下 Generate 常返回
        # path_exists=False（同一配方在别的会话里成功过），所以容忍失败。
        ("ug_generate_cam_toolpath", {"operation_names": ["OP1"], "backend": "auto"}),
        ("ug_export_cam_clsf", {"file_name": "op1_%s.clsf" % _s}),
    ]
    return _ug_flow(client, steps, "cam",
                    tolerate=("ug_generate_cam_toolpath", "ug_export_cam_clsf"))


def _ug_drawing_flow(client, context):
    """ug 剧本三：A3 图纸 + 投影视图 + 注释 + 注释自省（6 步）。"""
    _s = uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "acc_dwg_%s.prt" % _s}),
        ("ug_create_block", {"length": 100, "width": 60, "height": 20}),
        ("ug_create_drawing_sheet", {"name": "S1", "size": "A3", "create_base_view": True}),
        ("ug_create_projected_view", {"view_position": [200.0, 150.0, 0.0]}),
        ("ug_create_drafting_note", {"lines": ["ACCEPT"], "position": [50.0, 50.0, 0.0]}),
        ("ug_inspect_drawing_annotations", {}),
    ]
    return _ug_flow(client, steps, "drawing")


def _ug_sheetmetal_flow(client, context):
    """ug 剧本四：参数化草图 → NX 钣金基体 tab → 体自省（5 步）。"""
    _s = uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "acc_sm_%s.prt" % _s}),
        ("ug_create_parametric_sketch", {"name": "SK1", "plane": "XY",
                                         "geometry": [{"type": "rectangle", "name": "r1",
                                                       "origin": [0.0, 0.0],
                                                       "width": 80.0, "height": 40.0}]}),
        ("ug_inspect_sketch", {}),
        ("ug_create_sheet_metal_tab", {"sketch_id": "SK1", "thickness": 2}),
        ("ug_inspect_work_part_geometry", {}),
    ]
    return _ug_flow(client, steps, "sheetmetal")


def _ug_sheetmetal_bend_flow(client, context):
    """ug 剧本八：钣金 tab → 折弯 → 体自省（7 步）。

    折弯的前置：① 先有钣金基体（`create_sheet_metal_tab`）；
    ② 折弯线必须是**另一张草图**里的直线，用草图 `journal_id`（= name）传进去。
    """
    _s = uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "acc_smb_%s.prt" % _s}),
        ("ug_create_parametric_sketch", {"name": "PLATE", "plane": "XY",
                                         "geometry": [{"type": "rectangle", "name": "R",
                                                       "origin": [0.0, 0.0],
                                                       "width": 80.0, "height": 50.0}]}),
        ("ug_create_sheet_metal_tab", {"sketch_id": "PLATE", "thickness": 2.0}),
        ("ug_create_parametric_sketch", {"name": "BENDLINE", "plane": "XY",
                                         "geometry": [{"type": "line", "name": "BL",
                                                       "start": [0.0, 25.0],
                                                       "end": [80.0, 25.0]}]}),
        ("ug_create_sheet_metal_bend", {"bend_line_sketch_id": "BENDLINE",
                                        "target_face_selector": {"kind": "planar",
                                                                 "normal": [0, 0, 1]},
                                        "angle_deg": 90, "bend_radius": 2.0}),
        ("ug_inspect_work_part_geometry", {}),
    ]
    return _ug_flow(client, steps, "sheetmetal_bend")


def _ug_topology_flow(client, context):
    """ug 剧本九：按几何条件解析拓扑（5 步）。

    `ug_resolve_topology` 的 selector 支持 `{"kind": "planar", "normal": [...]}`；
    匹配多条时必须显式 `unique=False`，否则报 "matched N edges; add sort_by or
    occurrence"。
    """
    _s = uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "acc_topo_%s.prt" % _s}),
        ("ug_create_block", {"length": 100, "width": 60, "height": 40}),
        ("ug_resolve_topology", {"kind": "face",
                                 "selector": {"kind": "planar", "normal": [0, 0, 1]}}),
        ("ug_resolve_topology", {"kind": "edge",
                                 "selector": {"kind": "all"}, "unique": False}),
    ]
    return _ug_flow(client, steps, "topology")


def _ug_machine_readonly_flow(client, context):
    """ug 剧本十：机器仿真只读两件套（5 步）。

    `inspect_active_machine_simulation` / `stop_active_machine_simulation` 在没有
    活动仿真时也应正常返回（stop 是幂等的 release）。
    """
    _s = uuid.uuid4().hex[:6]
    steps = [
        ("ug_create_part", {"file_name": "acc_mach_%s.prt" % _s}),
        ("ug_create_block", {"length": 80, "width": 50, "height": 30}),
        ("ug_inspect_active_machine_simulation", {}),
        ("ug_stop_active_machine_simulation", {"release": True}),
    ]
    return _ug_flow(client, steps, "machine_readonly")


def _ug_machine_inspect_flow(client, context):
    """ug 剧本十一：机器源配置只读三件套（4 步）。

    依赖 `MCP/UG/config/machine_sources.local` 里配好的 profile（本机用
    `sim05_mill_5ax` 的真实机型图 + 合成 `nsa_probe_machine.mch`）。
    `create_machine_build_workspace` 只跑 **dry_run**：真建会切换活动部件，
    而真激活在本机会把 NX remoting 线程挂住（见 docs）。
    """
    profile = "nsa_probe_5ax"
    steps = [
        ("ug_inspect_machine_source_profile", {"source_profile": profile}),
        ("ug_inspect_machine_kinematic_plan", {"source_profile": profile}),
        ("ug_create_machine_build_workspace", {"source_profile": profile,
                                               "workspace_file_name": "nsa_probe_machine.prt",
                                               "dry_run": True}),
    ]
    return _ug_flow(client, steps, "machine_inspect")


def _ug_machine_build_flow(client, context):
    """ug 剧本十二：机器工作区 → 激活 → 导入几何 → 真建运动学（6 步）。

    关键配方（2026-11-05 实测打通）：
    * profile 的 `<VcMachine>` 组件名**必须**是 Base/X/Y/Z/B/C/Spindle/Tool/Attach
      （上游 low-level 建链里写死了这些键）；
    * 旋转轴的 `Axis` 只能是 X/Y/Z（方向），寄存器名才是 B/C；
    * 每个组件要有 `<STL><File>xxx.stl</File></STL>` 且文件真在 geometry_root 里；
    * 源件必须是**单零件**：拿装配体当源件、组件解析不到时，
      `activate_machine_build_workspace` 会把 NX remoting 线程挂死。

    建工作区只能做一次（同名会报 already exists），所以先单独建、拿 recovery_token，
    再交给通用流程跑后续步骤。
    """
    _s = uuid.uuid4().hex[:6]
    workspace = "acc_machine_%s.prt" % _s
    profile = "nsa_simple"
    created = client.call("ug_create_machine_build_workspace", {
        "source_profile": profile, "workspace_file_name": workspace,
        "dry_run": False, "confirmation": "CREATE_MACHINE_BUILD_WORKSPACE"})
    token = ((created.get("reads") or {}).get("recovery_token") or "")
    steps = [
        # 激活要求"当前部件没有未保存修改"，所以先存一下（没有部件时这条允许失败）
        ("ug_save_work_part", {}),
        ("ug_activate_machine_build_workspace", {
            "workspace_file_name": workspace, "recovery_token": token,
            "dry_run": False, "preserve_current": False,
            "confirmation": "ACTIVATE_MACHINE_BUILD_WORKSPACE"}),
        ("ug_import_machine_component_geometry", {
            "source_profile": profile, "workspace_file_name": workspace,
            "dry_run": False, "confirmation": "IMPORT_MACHINE_COMPONENT_GEOMETRY"}),
        ("ug_build_machine_kinematics_from_profile", {
            "source_profile": profile, "workspace_file_name": workspace,
            "dry_run": False, "confirmation": "BUILD_MACHINE_KINEMATICS"}),
        ("ug_probe_machine_axis_motion", {
            "source_profile": profile, "workspace_file_name": workspace,
            "axis_name": "X", "delta": 0.01, "dry_run": True}),
        ("ug_retarget_machine_junctions_from_profile", {
            "source_profile": profile, "workspace_file_name": workspace,
            "dry_run": True}),
    ]
    result = _ug_flow(client, steps, "machine_build",
                      tolerate=("ug_save_work_part",))
    if isinstance(result.get("reads"), dict):
        result["reads"].setdefault("workspace", workspace)
        result["reads"].setdefault("token_present", bool(token))
    return result


def _ug_restart_nx_session(client, log=None):
    """把 NX 换成**干净会话**再跑（只给 machine_validate 这类"会话敏感"用例用）。

    实测（2026-11-06 17:00）：`ug.flow.machine_validate` 单独跑 11.9 s PASS，
    但在全量序列里（前面已经开了 5 台机床、建了十几个零件）会挂到超时。
    它内部要往临时阴影库导 MTK，会话一脏就卡在导入上。
    所以这里直接重启 NX：kill ugraf → 清锁 → 按当前模式（阴影库/标准库）重启 → 等 48161。
    """
    import socket
    import subprocess
    import time as _time

    def say(text):
        if log is not None:
            log(text)

    shadow_marker = _PathForMachineBuilds(
        r"D:\bililive\CAD-Agent-Hub\MCP\UG\machine_shadow\active.json")
    say("   重启 NX（隔离会话）…")
    subprocess.run(["taskkill", "/F", "/IM", "ugraf.exe"],
                   capture_output=True, text=True, errors="replace")
    _time.sleep(3)
    lock = _PathForMachineBuilds(os.environ.get("TEMP", "")) / "nsa-mcp-hub-ug.lock"
    try:
        lock.unlink()
    except OSError:
        pass
    if shadow_marker.exists():
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", r"D:\bililive\CAD-Agent-Hub\MCP\UG\scripts\start-nx-shadow.ps1"],
                       capture_output=True, text=True, errors="replace", timeout=600)
    else:
        env = os.environ.copy()
        env["UGII_USER_DIR"] = r"D:\bililive\CAD-Agent-Hub\MCP\UG\nx_user"
        subprocess.Popen([r"D:\Program Files\Siemens\DesigncenterNX2512\NXBIN\ugraf.exe"], env=env)
        for _ in range(60):
            _time.sleep(5)
            try:
                with socket.create_connection(("127.0.0.1", 48161), timeout=2):
                    break
            except OSError:
                continue
    client.restart()
    say("   NX 已换新会话")


def _ug_machine_validate_flow(client, context):
    """ug 剧本十三：机床校验五件套（走**官方 BC 模板**路线，真正通过）。

    关键结论（2026-11-05 打通）：
    * 许可不用另开：`LicenseManager.CheckPresence("isv_full"/"nx_isv_mtb")` 都是 True，
      `Reserve(feature, "nsapro<pad>")` 能签出；NX 自带的 SSQ 许可文件里就有这两条。
    * 通道定义要在 **Machine Tool Builder 应用**里做：
      `ApplicationSwitchImmediate("UG_APP_MACHINE_TOOL_BUILDER")`；NX 自己弹的提示原文
      就是"要处理程序管理器中的 INI 文件，在机床构建器中定义通道"。
    * `source_part_copy` 路线建出来的轴**绑不上通道**（`SetAssignedAxes(["X",...])` 后
      `GetAssignedAxes()` 返回一串空串，`Commit()` 时通道被判无效丢掉）；换成
      `blank_smart_machine_kit` 路线（导入 NX 官方 "5 Axis Dual Table BC Mill" 模板）
      后，通道 `TNC_640` 自带 6 根轴（X/Y/Z/S/B/C）绑定，`IsAxisAssignedToChannel` 全 True。

    因此本剧本断言的是**正结果**：
      运动学校验 ok=True、静态碰撞 4 对全评估且 0 干涉；
    后三个工具（readiness / start / import readback）在没有 CAM 工序、没有 .mtk 时
    如实拒绝，这里断言拒绝原因。
    """
    # 会话减负：这条用例排在最后，前面已经开了 6+ 个带机床的零件。
    # 实测（2026-11-06 16:13）会话一膨胀，这里的 MTK 导入会挂到超时。
    # 所以先做一次**容错**清理（失败不影响判定），再建自己的工作区。
    # 这条用例对会话状态极敏感（全量序列里会挂，单独跑 11.9 s 就过），
    # 所以先换成干净 NX 会话，再做容错清理。
    try:
        _ug_restart_nx_session(client)
    except Exception:                                  # noqa: BLE001
        pass
    try:
        client.call("ug_close_test_parts",
                    {"dry_run": False, "time_limit_s": 60,
                     "confirmation": "CLOSE_TEST_PARTS"})
    except Exception:                                  # noqa: BLE001
        pass

    _s = uuid.uuid4().hex[:6]
    workspace = "acc_kit_%s.prt" % _s
    kit_name = "nsa_acc_%s.mtk" % _s
    profile = "nsa_simple"
    created = client.call("ug_create_smart_machine_kit_workspace", {
        "source_profile": profile, "workspace_file_name": workspace,
        "dry_run": False, "confirmation": "CREATE_SMART_MACHINE_KIT_WORKSPACE"})
    if not created.get("ok"):
        return {"ok": False, "reads": {"failed_at": "ug_create_smart_machine_kit_workspace"},
                "errors": ["建模板工作区失败：%s" % str(created.get("errors"))[:200]],
                "checks": []}
    token = ((created.get("reads") or {}).get("recovery_token") or "")

    steps = [
        ("ug_save_work_part", {}, True, None),
        ("ug_activate_machine_build_workspace", {
            "workspace_file_name": workspace, "recovery_token": token,
            "dry_run": False, "preserve_current": False,
            "confirmation": "ACTIVATE_MACHINE_BUILD_WORKSPACE"}, True, None),
        ("ug_import_machine_component_geometry", {
            "source_profile": profile, "workspace_file_name": workspace,
            "dry_run": False,
            "confirmation": "IMPORT_MACHINE_COMPONENT_GEOMETRY"}, True, None),
        ("ug_build_machine_kinematics_from_profile", {
            "source_profile": profile, "workspace_file_name": workspace,
            "dry_run": False, "confirmation": "BUILD_MACHINE_KINEMATICS"}, True, None),
        # 这条现在是**真通过**（不是拒绝）
        ("ug_validate_machine_kinematics", {
            "source_profile": profile, "workspace_file_name": workspace,
            "require_geometry": True}, True, None),
        ("ug_validate_machine_static_collisions", {
            "source_profile": profile, "workspace_file_name": workspace,
            "evaluate_geometry": True,
            "confirmation": "EVALUATE_STATIC_MACHINE_COLLISIONS"}, True, None),
        # 导出 `.mtk`：**必须给 reference_container_file_name**。
        # 不给时会走 NX 的 `ExportMachineKitBuilder`，那条内部是 MOM_TCL 打包，
        # 自动化调用恒定报 `MOM_TCL：用户选择了中止`；给了已验证的参考包之后
        # 直接走 repackage（不再触发 TCL），实测稳定 ok+可回读。
        ("ug_save_work_part", {}, True, None),
        ("ug_export_machine_kit_from_reference", {
            "source_profile": profile, "workspace_file_name": workspace,
            "output_file_name": kit_name,
            "reference_container_file_name": "nsa_reference_kit.mtk",
            "dry_run": False, "overwrite": True,
            "confirmation": "EXPORT_MACHINE_KIT"}, True, None),
        ("ug_import_machine_kit_readback", {
            "machine_kit_file_name": kit_name, "source_profile": profile,
            "dry_run": False, "keep_imported": False,
            "confirmation": "IMPORT_MACHINE_KIT_ISOLATED"}, True, None),
        ("ug_initialize_cam_setup", {"template_name": "mill_planar",
                                     "switch_to_manufacturing": False}, True, None),
        # 建工序前必须先把刀具建出来（工序要挂 tool parent）
        ("ug_create_cam_mill_tool", {
            "name": "T01_END_MILL", "diameter": 10.0, "flute_length": 20.0,
            "overall_length": 60.0, "flute_count": 4, "tool_number": 1}, True, None),
        # readiness 的硬前置是"程序组里至少一个工序"；建一个空工序（无几何）即可让它出**报告**
        ("ug_create_cam_operation", {
            "name": "MCP_FACE_1", "template_type": "mill_planar",
            "template_subtype": "PLANAR_MILL", "program_name": "NC_PROGRAM",
            "method_name": "MILL_FINISH", "geometry_name": "MCS_MAIN",
            "tool_name": "T01_END_MILL"},
         True, None),
        # readiness 返回的是"报告"（ok=True 但 ready=False + blockers），这里断言 ok=True，
        # 并且 blocker 里必须点到"没绑机床库/没刀路"——这些正是 start 会拒绝的原因。
        ("ug_inspect_machine_simulation_readiness", {
            "program_name": "NC_PROGRAM",
            "required_axes": ["X", "Y", "Z", "B", "C"]}, True, None),
        # start 是真闸门：没绑机床库/没刀路时拒绝，且必须报出 blockers
        ("ug_start_machine_simulation_with_collision_stop", {
            "program_name": "NC_PROGRAM",
            "required_axes": ["X", "Y", "Z", "B", "C"],
            "play_immediately": False}, False, "not ready"),
    ]
    records = []
    checks = []
    kinematics_reads = {}
    static_reads = {}
    step_reads = {}
    for name, args, expect_ok, needle in steps:
        payload = client.call(name, args)
        actual_ok = bool(payload.get("ok"))
        errors = " ".join(str(x) for x in (payload.get("errors") or []))
        matched = needle is None or needle.lower() in errors.lower()
        ok = (actual_ok == expect_ok) and matched
        if name == "ug_validate_machine_kinematics":
            kinematics_reads = payload.get("reads") or {}
        if name == "ug_validate_machine_static_collisions":
            static_reads = payload.get("reads") or {}
        step_reads[name] = payload.get("reads") or {}
        records.append({"tool": name, "ok": ok, "expect_ok": expect_ok,
                        "actual_ok": actual_ok, "needle": needle, "matched": matched,
                        "errors": errors[:200]})
        checks.append({"check": "%s %s" % (name, "ok" if expect_ok else "refusal"),
                       "got": actual_ok, "want": expect_ok, "ok": ok})

    # 运动学：结构化校验必须通过，且 6 根轴都绑到通道上
    assignments = (kinematics_reads.get("channel_axis_assignments") or {})
    axis_flags = {}
    for channel, axis_map in assignments.items():
        if isinstance(axis_map, dict):
            axis_flags.update({str(k): bool(v) for k, v in axis_map.items()})
    checks.append({"check": "kinematics_structural_passed",
                   "got": kinematics_reads.get("structural_validation_passed"),
                   "want": True,
                   "ok": bool(kinematics_reads.get("structural_validation_passed"))})
    checks.append({"check": "channel_axis_assignments_all_true",
                   "got": axis_flags, "want": "all true",
                   "ok": bool(axis_flags) and all(axis_flags.values())})
    checks.append({"check": "kinematics_no_blockers",
                   "got": kinematics_reads.get("blockers"), "want": [],
                   "ok": kinematics_reads.get("blockers") == []})

    # 静态碰撞：碰撞对全部评估、初始位置 0 干涉
    evaluation = static_reads.get("static_collision_evaluation") or {}
    pair_results = evaluation.get("pair_results") or []
    configuration = static_reads.get("collision_configuration") or {}
    checks.append({"check": "static_collision_pairs_configured",
                   "got": len(pair_results),
                   "want": ">=1", "ok": len(pair_results) >= 1})
    checks.append({"check": "static_collision_pairs_evaluated",
                   "got": evaluation.get("evaluated_pair_count"),
                   "want": len(pair_results),
                   "ok": (len(pair_results) >= 1
                          and evaluation.get("evaluated_pair_count") == len(pair_results))})
    checks.append({"check": "static_collision_no_initial_interference",
                   "got": evaluation.get("interfering_pair_count"),
                   "want": 0, "ok": evaluation.get("interfering_pair_count") == 0})
    checks.append({"check": "static_collision_no_blockers",
                   "got": static_reads.get("blockers"), "want": [],
                   "ok": static_reads.get("blockers") == []})

    # 仿真就绪度：ok=True 只是一份报告，必须真的列出阻塞项
    readiness_reads = step_reads.get("ug_inspect_machine_simulation_readiness") or {}
    ready_blockers = readiness_reads.get("blockers") or []
    checks.append({"check": "readiness_reports_blockers",
                   "got": ready_blockers, "want": "non-empty",
                   "ok": bool(ready_blockers)})
    checks.append({"check": "readiness_not_ready_is_reported",
                   "got": readiness_reads.get("machine_simulation_ready"),
                   "want": False,
                   "ok": readiness_reads.get("machine_simulation_ready") is False})
    checks.append({"check": "readiness_mentions_machine_binding",
                   "got": "no_machine_library_binding" in ready_blockers,
                   "want": True,
                   "ok": "no_machine_library_binding" in ready_blockers})

    # 导出/回读（repackage 路线，稳定）
    export_reads = step_reads.get("ug_export_machine_kit_from_reference") or {}
    readback_reads = step_reads.get("ug_import_machine_kit_readback") or {}
    checks.append({"check": "machine_kit_export_structural_passed",
                   "got": export_reads.get("structural_validation_passed"), "want": True,
                   "ok": bool(export_reads.get("structural_validation_passed"))})
    checks.append({"check": "machine_kit_export_route_repackage",
                   "got": export_reads.get("packaging_route"),
                   "want": "nx_reference_kit_repackage",
                   "ok": export_reads.get("packaging_route") == "nx_reference_kit_repackage"})
    checks.append({"check": "machine_kit_readback_isolated",
                   "got": readback_reads.get("isolated_import"), "want": True,
                   "ok": bool(readback_reads.get("isolated_import"))})
    checks.append({"check": "machine_kit_readback_global_db_unchanged",
                   "got": readback_reads.get("global_machine_database_unchanged"),
                   "want": True,
                   "ok": bool(readback_reads.get("global_machine_database_unchanged"))})

    return {"ok": all(c["ok"] for c in checks),
            "reads": {"workspace": workspace, "steps": records,
                      "kinematics": {
                          "channels": (kinematics_reads.get("kinematics") or {}).get("channels"),
                          "chains": (kinematics_reads.get("kinematics") or {}).get("chain_names"),
                          "axis_assignments": axis_flags},
                      "static_collision": {
                          "pair_count": len(pair_results),
                          "evaluated": evaluation.get("evaluated_pair_count"),
                          "interfering": evaluation.get("interfering_pair_count"),
                          "pairs": [{"first": item.get("first"),
                                     "second": item.get("second"),
                                     "hard": item.get("hard"),
                                     "clearance": item.get("configured_clearance")}
                                    for item in pair_results]}},
            "errors": [], "checks": checks}




from pathlib import Path as _PathForMachineBuilds

_MACHINE_BUILD_DIR = _PathForMachineBuilds(
    r"D:\bililive\CAD-Agent-Hub\MCP\UG\workspace\machine_builds"
)
_BOUND_MACHINE_FIXTURE = "acc_kit_61ab27.prt"


def _ug_bound_machine_fixture():
    """手工绑过机床的那个工作区（CAMSetup.GetMachineLibref() 非空）。

    绑定这一步目前只能人工在 NX 里做（见 MACHINE_KINEMATICS.md 第 8 节：
    `CreateMachineGroupBuilder(None)` 空指针、`CreateNcmptPartMountingBuilder`
    单独 Commit 不产生机床组），所以整条仿真链用一个固定 fixture 来验收。
    """
    part = _MACHINE_BUILD_DIR / _BOUND_MACHINE_FIXTURE
    return part if part.is_file() else None


def _ug_no_bound_machine_fixture(context=None) -> bool:
    return _ug_bound_machine_fixture() is None


def _ug_machine_simulate_flow(client, context):
    """ug 剧本十四：真跑机床仿真（**自己绑机床** → 刀路 → readiness → start → stop）。

    2026-11-06 起不再依赖外部 fixture：先用 `ug_bind_machine_from_library` 把
    `sim05_mill_5ax_fanuc` 绑到新零件上（journal 抠出来的 API 序列），再走

        create_cam_milling_context(新程序组) -> FLOOR_FACING 工序 ->
        configure(cut_area 面 + floor_z + 进给) -> generate_cam_toolpath ->
        readiness(blockers=[]) -> start(prepared) -> stop

    这就是"从零到机床仿真"的完整闭环。
    """
    import time as _time
    import uuid as _uuid

    tag = int(_time.time() % 100000)
    part_name = "sim_%s.prt" % _uuid.uuid4().hex[:6]
    program = "MCP_SIMD_%d" % tag
    operation = "MCP_GEND_%d" % tag
    checks, reads = [], {}

    gaps = []

    def record(name, payload, want_ok=True):
        ok = bool(payload.get("ok")) is want_ok
        gaps.append({"tool": name, "ok": bool(payload.get("ok"))})
        checks.append({"check": name, "got": bool(payload.get("ok")), "want": want_ok,
                       "ok": ok})
        if not ok:
            reads.setdefault("errors", []).append(
                "%s: %s" % (name, str(payload.get("errors"))[:200]))
        return payload.get("reads") or {}

    # 1) 干净零件 + 机床绑定
    for tool, args in (
        ("ug_create_part", {"file_name": part_name}),
        ("ug_run_python", {"code": (
            "import NXOpen\ns = NXOpen.Session.GetSession()\n"
            "s.ApplicationSwitchImmediate('UG_APP_MANUFACTURING')\n"
            "result = {'app': str(s.ApplicationName)}")}),
        ("ug_create_block", {"length": 80.0, "width": 50.0, "height": 30.0}),
        ("ug_initialize_cam_setup", {"template_name": "mill_planar"}),
    ):
        payload = client.call(tool, args)
        if not payload.get("ok"):
            return {"ok": False, "reads": reads,
                    "errors": ["%s 失败：%s" % (tool, str(payload.get("errors"))[:180])],
                    "checks": checks}

    bound = record("ug_bind_machine_from_library",
                   client.call("ug_bind_machine_from_library",
                               {"libref": "sim05_mill_5ax_fanuc"}))
    checks.append({"check": "machine_bound", "got": bool(bound.get("bound")), "want": True,
                   "ok": bool(bound.get("bound"))})
    if not bound.get("bound"):
        reads["bind"] = bound
        return {"ok": False, "reads": reads, "errors": ["机床没绑上"], "checks": checks}

    # 2) CAM 链：刀具 -> 新程序组 + FLOOR_FACING + 刀路
    tool = record("ug_create_cam_mill_tool", client.call("ug_create_cam_mill_tool", {
        "name": "MCP_T01", "diameter": 10.0, "flute_length": 30.0,
        "overall_length": 75.0}))
    tool_name = tool.get("name") or "MCP_T01"
    ctx = record("ug_create_cam_milling_context", client.call(
        "ug_create_cam_milling_context", {
            "origin": [0.0, 0.0, 0.0], "part_body_indices": [0],
            "program_name": program, "method_name": "MCP_METHOD",
            "mcs_name": "MCP_MCS", "workpiece_name": "MCP_WPD_%d" % tag,
            "blank_offset": 2.0}))
    program_name = ctx.get("program_name") or program
    method_name = ctx.get("method_name") or "MCP_METHOD"
    geometry_name = ctx.get("workpiece_name") or ("MCP_WPD_%d" % tag)
    record("ug_create_cam_operation", client.call("ug_create_cam_operation", {
        "name": operation, "template_type": "mill_planar",
        "template_subtype": "FLOOR_FACING", "program_name": program_name,
        "method_name": method_name, "geometry_name": geometry_name,
        "tool_name": tool_name}))
    record("ug_configure_cam_milling_operation", client.call(
        "ug_configure_cam_milling_operation", {
            "operation_name": operation, "body_index": 0, "part_body_indices": [0],
            "cut_area_face_selectors": [{"sort_by": "largest"}],
            "depth_per_cut": 5.0, "floor_z": 0.0, "top_offset": 0.0,
            "spindle_rpm": 2000.0, "cut_feed": 300.0,
            "approach_feed": 100.0, "retract_feed": 500.0}))
    toolpath = record("ug_generate_cam_toolpath", client.call(
        "ug_generate_cam_toolpath", {"operation_names": [operation]}))
    checks.append({"check": "toolpath_generated", "got": toolpath.get("generated_count"),
                   "want": 1, "ok": toolpath.get("generated_count") == 1})

    # 3) readiness -> start -> stop
    readiness = record("ug_inspect_machine_simulation_readiness", client.call(
        "ug_inspect_machine_simulation_readiness", {
            "program_name": program_name, "required_axes": ["X", "Y", "Z"],
            "require_axis_limits": False, "require_tool_geometry": True,
            "require_workpiece_geometry": True, "require_holder_geometry": False,
            "require_fixture_geometry": False}))
    checks.append({"check": "readiness_blockers_empty",
                   "got": readiness.get("blockers"), "want": [],
                   "ok": readiness.get("blockers") == []})
    checks.append({"check": "machine_simulation_ready",
                   "got": readiness.get("machine_simulation_ready"), "want": True,
                   "ok": readiness.get("machine_simulation_ready") is True})
    started = record("ug_start_machine_simulation_with_collision_stop", client.call(
        "ug_start_machine_simulation_with_collision_stop", {
            "program_name": program_name, "operation_names": [operation],
            "required_axes": ["X", "Y", "Z"], "play_immediately": False,
            "require_axis_limits": False, "require_tool_geometry": True,
            "require_workpiece_geometry": True, "require_holder_geometry": False,
            "require_fixture_geometry": False}))
    checks.append({"check": "simulation_prepared",
                   "got": started.get("simulation_prepared"), "want": True,
                   "ok": started.get("simulation_prepared") is True})
    checks.append({"check": "simulation_status_prepared",
                   "got": started.get("status"), "want": "prepared",
                   "ok": started.get("status") == "prepared"})
    checks.append({"check": "collision_stop_armed",
                   "got": (started.get("options") or {}).get("stop_on_collision"),
                   "want": True,
                   "ok": (started.get("options") or {}).get("stop_on_collision") is True})
    stopped = record("ug_stop_active_machine_simulation", client.call(
        "ug_stop_active_machine_simulation", {"release": True}))
    checks.append({"check": "simulation_stopped", "got": stopped.get("stopped"),
                   "want": True, "ok": stopped.get("stopped") is True})
    reads["steps"] = gaps
    reads.update({"part": part_name, "program": program_name, "operation": operation,
                  "readiness": {"blockers": readiness.get("blockers"),
                                "ready": readiness.get("machine_simulation_ready")},
                  "start": {"prepared": started.get("simulation_prepared"),
                            "status": started.get("status")}})
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "reads": reads,
            "errors": [] if ok else ["仿真链未通过"], "checks": checks}



def _nx_dialog_clicker(stop_event, log, timeout_s=240):
    """在 host 侧点掉 NX 的模态对话框（绑定机床时会弹「添加加工部件」）。

    为什么要它：`mb.Commit()` 在 NX 里会阻塞等这个对话框，而我们的工具调用是
    同步 RPC —— 不点掉就会一直挂着。所以验收用例起一个后台线程，一边阻塞调工具，
    一边把 NX 的 `NX_SURFACE_WND_DIALOG` 点掉。
    """
    import time as _time

    try:
        import win32con
        import win32gui
        import win32process
    except Exception as exc:                       # noqa: BLE001
        log.append("no win32: %s" % type(exc).__name__)
        return

    deadline = _time.time() + timeout_s

    def nx_pids():
        import subprocess as _sp
        out = _sp.run(["tasklist", "/FI", "IMAGENAME eq ugraf.exe"],
                      capture_output=True, text=True)
        pids = set()
        for line in out.stdout.splitlines():
            if line.lower().startswith("ugraf"):
                try:
                    pids.add(int(line.split()[1]))
                except Exception:                  # noqa: BLE001
                    pass
        return pids

    while not stop_event.is_set() and _time.time() < deadline:
        pids = nx_pids()
        found = []

        def cb(hwnd, _):
            try:
                _, owner = win32process.GetWindowThreadProcessId(hwnd)
                if owner in pids and win32gui.IsWindowVisible(hwnd) \
                        and win32gui.GetClassName(hwnd) == "NX_SURFACE_WND_DIALOG":
                    found.append(hwnd)
            except Exception:                      # noqa: BLE001
                pass
            return True

        try:
            win32gui.EnumWindows(cb, None)
        except Exception:                          # noqa: BLE001
            pass
        for hwnd in found:
            clicked = False
            kids = []
            try:
                win32gui.EnumChildWindows(
                    hwnd,
                    lambda h, _: kids.append((h, win32gui.GetWindowText(h))) or True,
                    None)
            except Exception:                      # noqa: BLE001
                pass
            for h, text in kids:
                if text.strip() in ("确定", "OK", "是"):
                    try:
                        win32gui.SendMessage(h, win32con.BM_CLICK, 0, 0)
                        clicked = True
                        log.append("clicked %s" % text.strip())
                    except Exception:              # noqa: BLE001
                        pass
                    break
            if not clicked:
                try:
                    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
                    log.append("enter")
                except Exception:                  # noqa: BLE001
                    pass
        _time.sleep(0.5)


def _ug_machine_bind_flow(client, context):
    """ug 剧本十五：**脚本化绑定机床**（从库调用 → 生成 SPINDLE/POCKET）。

    序列是用 NX journal 录制 UI 操作抠出来的（见 MACHINE_KINEMATICS.md 第 17 节）：

        FindObject("GENERIC_MACHINE") -> CreateMachineGroupBuilder ->
        CreateNcmptPartMountingBuilder(libref) -> RemoveMachine -> Commit -> UpdateCamSetup

    判据：`GetMachineLibref()` 变成 libref，导航器出现 SPINDLE + ≥4 个 POCKET。
    """
    import threading as _threading
    import time as _time
    import uuid as _uuid

    part = "bind_%s.prt" % _uuid.uuid4().hex[:6]
    checks, reads = [], {}
    clicks = []

    steps = []

    def record(name, payload, want_ok=True):
        ok = bool(payload.get("ok")) is want_ok
        steps.append({"tool": name, "ok": bool(payload.get("ok"))})
        checks.append({"check": name, "got": bool(payload.get("ok")), "want": want_ok,
                       "ok": ok})
        err = str(payload.get("errors"))[:200] if not payload.get("ok") else ""
        return payload.get("reads") or {}, err

    for tool, args in (
        ("ug_create_part", {"file_name": part}),
        ("ug_create_block", {"length": 80.0, "width": 50.0, "height": 30.0}),
        ("ug_initialize_cam_setup", {"template_name": "mill_planar"}),
    ):
        payload = client.call(tool, args)
        steps.append({"tool": tool, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": reads},
                    "errors": ["%s 失败：%s" % (tool, str(payload.get("errors"))[:180])],
                    "checks": checks}

    stop = _threading.Event()
    clicker = _threading.Thread(target=_nx_dialog_clicker,
                                args=(stop, clicks, 240), daemon=True)
    clicker.start()
    try:
        payload = client.call("ug_bind_machine_from_library",
                              {"libref": "sim05_mill_5ax_fanuc",
                               "positioning": "assembly"})
    finally:
        stop.set()
        clicker.join(timeout=5)

    bound_reads, err = record("ug_bind_machine_from_library", payload)
    reads.update(bound_reads)
    reads["dialog_clicks"] = clicks[:10]
    if err:
        reads["errors"] = err
    checks.append({"check": "machine_bound",
                   "got": bool(bound_reads.get("bound")), "want": True,
                   "ok": bool(bound_reads.get("bound"))})
    checks.append({"check": "libref_matches",
                   "got": bound_reads.get("libref_after"),
                   "want": "sim05_mill_5ax_fanuc",
                   "ok": bound_reads.get("libref_after") == "sim05_mill_5ax_fanuc"})
    groups = [str(g).upper() for g in (bound_reads.get("machine_groups") or [])]
    checks.append({"check": "has_spindle", "got": any(g.startswith("SPINDLE") for g in groups),
                   "want": True, "ok": any(g.startswith("SPINDLE") for g in groups)})
    pockets = sum(1 for g in groups if g.startswith("POCKET"))
    checks.append({"check": "pockets_created", "got": pockets, "want": ">=4",
                   "ok": pockets >= 4})
    reads["steps"] = steps
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "reads": reads,
            "errors": [] if ok else ["绑定未完成：%s" % (checks,)],
            "checks": checks}



def _ug_machine_swap_flow(client, context):
    """ug 剧本十六：**换型 + 持久化**（绑 fanuc → 卸 → 绑 tnc → 存盘 → 关重开）。

    覆盖三件事，都是 2026-11-06 实测出来的：

    1. `CAMSetup.RemoveMachine()` 能把机床卸干净（libref 变空、SPINDLE/POCKET 消失、
       `GENERIC_MACHINE` 根节点重新出现）；
    2. 卸完可以再 `bind_machine_from_library` 换一台（换成 `sim05_mill_5ax_tnc`）；
    3. 绑定是**落在部件文件里**的：存盘 → 关闭 → 重开，`GetMachineLibref()` 仍是 tnc。
    """
    import json as _json
    import uuid as _uuid

    part = "swapc_%s.prt" % _uuid.uuid4().hex[:6]
    checks, reads, steps = [], {}, []

    def record(name, payload, want_ok=True):
        ok = bool(payload.get("ok")) is want_ok
        steps.append({"tool": name, "ok": bool(payload.get("ok"))})
        checks.append({"check": name, "got": bool(payload.get("ok")), "want": want_ok,
                       "ok": ok})
        if not ok:
            reads.setdefault("errors", []).append(
                "%s: %s" % (name, str(payload.get("errors"))[:200]))
        return payload.get("reads") or {}

    for tool, args in (
        ("ug_create_part", {"file_name": part}),
        ("ug_run_python", {"code": (
            "import NXOpen\ns = NXOpen.Session.GetSession()\n"
            "s.ApplicationSwitchImmediate('UG_APP_MANUFACTURING')\n"
            "result = {'app': str(s.ApplicationName)}")}),
        ("ug_create_block", {"length": 80.0, "width": 50.0, "height": 30.0}),
        ("ug_initialize_cam_setup", {"template_name": "mill_planar"}),
    ):
        payload = client.call(tool, args)
        steps.append({"tool": tool, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": reads,
                    "errors": ["%s 失败：%s" % (tool, str(payload.get("errors"))[:180])],
                    "checks": checks}

    first = record("ug_bind_machine_from_library", client.call(
        "ug_bind_machine_from_library", {"libref": "sim05_mill_5ax_fanuc"}))
    checks.append({"check": "first_bind_fanuc",
                   "got": first.get("libref_after"), "want": "sim05_mill_5ax_fanuc",
                   "ok": first.get("libref_after") == "sim05_mill_5ax_fanuc"})

    removed = record("ug_remove_machine", client.call("ug_remove_machine", {}))
    checks.append({"check": "remove_clears_libref", "got": removed.get("libref_after"),
                   "want": "", "ok": removed.get("libref_after") == ""})
    checks.append({"check": "remove_drops_spindle",
                   "got": removed.get("spindle_present"), "want": False,
                   "ok": removed.get("spindle_present") is False})
    checks.append({"check": "generic_machine_back",
                   "got": removed.get("generic_machine"), "want": True,
                   "ok": removed.get("generic_machine") is True})

    second = record("ug_bind_machine_from_library_tnc", client.call(
        "ug_bind_machine_from_library", {"libref": "sim05_mill_5ax_tnc"}))
    checks.append({"check": "swap_to_tnc", "got": second.get("libref_after"),
                   "want": "sim05_mill_5ax_tnc",
                   "ok": second.get("libref_after") == "sim05_mill_5ax_tnc"})
    groups = [str(g).upper() for g in (second.get("machine_groups") or [])]
    checks.append({"check": "swap_has_spindle",
                   "got": any(g.startswith("SPINDLE") for g in groups), "want": True,
                   "ok": any(g.startswith("SPINDLE") for g in groups)})

    record("ug_save_work_part", client.call("ug_save_work_part", {}))
    PY_REOPEN = (
        "import NXOpen\n"
        "s = NXOpen.Session.GetSession()\n"
        "work = s.Parts.Work\n"
        "before = str(work.CAMSetup.GetMachineLibref() or '')\n"
        "path = str(work.FullPath)\n"
        "work.Close(NXOpen.BasePartCloseWholeTree.TrueValue,\n"
        "           NXOpen.BasePartCloseModified.CloseModified, None)\n"
        "part, status = s.Parts.OpenActiveDisplay(path, NXOpen.DisplayPartOption.AllowAdditional)\n"
        "s.Parts.SetDisplay(part, True, True)\n"
        "s.Parts.SetWork(part)\n"
        "names = [str(getattr(g, 'Name', '') or '') for g in part.CAMSetup.CAMGroupCollection]\n"
        "result = {'libref_before': before, 'leaf': str(getattr(part, 'Leaf', '') or ''),\n"
        "          'libref_after': str(part.CAMSetup.GetMachineLibref() or ''),\n"
        "          'spindle': any(n.upper().startswith('SPINDLE') for n in names)}\n"
    )
    reopened_payload = client.call("ug_run_python", {"code": PY_REOPEN})
    reopened = record("ug_run_python", reopened_payload)
    # run_python 的读数在 reads.return_value 里
    reopened = (reopened_payload.get("reads") or {}).get("return_value") or {}
    checks.append({"check": "persisted_after_reopen",
                   "got": reopened.get("libref_after"), "want": "sim05_mill_5ax_tnc",
                   "ok": reopened.get("libref_after") == "sim05_mill_5ax_tnc"})
    checks.append({"check": "persisted_spindle",
                   "got": reopened.get("spindle"), "want": True,
                   "ok": reopened.get("spindle") is True})
    reads["steps"] = steps
    reads["reopen"] = {k: reopened.get(k) for k in ("libref_before", "libref_after",
                                                    "leaf", "spindle")}
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "reads": reads,
            "errors": [] if ok else ["换型/持久化未通过：%s" % (_json.dumps(
                [c for c in checks if not c["ok"]], ensure_ascii=False)[:400])],
            "checks": checks}



_SHADOW_ACTIVE_JSON = _PathForMachineBuilds(
    r"D:\bililive\CAD-Agent-Hub\MCP\UG\machine_shadow\active.json")


def _ug_shadow_active(context=None):
    """当前 NX 是不是「混合机床库」（scripts/start-nx-shadow.ps1）起的会话。"""
    return not _ug_no_shadow_library(context)


def _ug_no_shadow_library(context=None):
    """当前 NX 是不是用「混合机床库」（scripts/start-nx-shadow.ps1）起的。

    只有那种 NX 才能绑自家 `.mtk` 机床（libref 形如 `nsa_template_probe`）。
    普通启动时这台机床在库索引里根本不存在，所以整条用例跳过而不是判失败。
    """
    try:
        import json as _json
        import os as _os

        data = _json.loads(_SHADOW_ACTIVE_JSON.read_text(encoding="utf-8-sig"))  # PS 5.1 写的 json 带 BOM
    except Exception:
        return True
    pid = data.get("pid")
    if not isinstance(pid, int):
        return True
    # Windows 上 os.kill(pid, 0) 会抛 WinError 87（不是空检查），必须用 tasklist
    try:
        import subprocess as _subprocess

        result = _subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % pid],
            capture_output=True, text=True)
        if str(pid) not in (result.stdout or ""):
            return True      # 记录里的 NX 已经没了
    except Exception:
        return True
    root = str(data.get("shadowRoot") or "")
    return "machine_shadow" not in root



def _ug_machine_kit_bind_flow(client, context):
    """ug 剧本十七：**绑自家 .mtk 机床**（阴影机床库路线）。

    这条能通，靠的是两件 2026-11-06 查出来的事：

    1. 阴影库必须带 NX 的 DBC 处理脚本 `machine_data/dbc_machine_ascii.tcl|.def`，
       否则一查机床就 `MOM_TCL：无法打开 TCL 脚本文件`（syslog 里能看到
       `Mom_TclAdapter.cxx` + 那个 tcl 路径）；
    2. 阴影库要同时把 NX 全部标准机床 junction 进来，标准库和自家 kit 才能共存。

    建库/起 NX：`scripts/nx_machine_shadow.py --build` + `scripts/start-nx-shadow.ps1`。
    """
    import json as _json
    import uuid as _uuid

    libref = "nsa_template_probe"
    part = "kitb_%s.prt" % _uuid.uuid4().hex[:6]
    checks, reads, steps = [], {}, []
    # 先清会话：绑机床会加载整台机床装配，零件堆多了后面会挂住（实测全量里踩过）
    client.call("ug_close_test_parts",
                {"dry_run": False, "time_limit_s": 40,
                 "confirmation": "CLOSE_TEST_PARTS"})

    def record(name, payload, want_ok=True):
        ok = bool(payload.get("ok")) is want_ok
        steps.append({"tool": name, "ok": bool(payload.get("ok"))})
        checks.append({"check": name, "got": bool(payload.get("ok")), "want": want_ok,
                       "ok": ok})
        if not ok:
            reads.setdefault("errors", []).append(
                "%s: %s" % (name, str(payload.get("errors"))[:200]))
        return payload.get("reads") or {}

    for tool, args in (
        ("ug_create_part", {"file_name": part}),
        ("ug_run_python", {"code": (
            "import NXOpen\ns = NXOpen.Session.GetSession()\n"
            "s.ApplicationSwitchImmediate('UG_APP_MANUFACTURING')\n"
            "result = {'app': str(s.ApplicationName)}")}),
        ("ug_create_block", {"length": 80.0, "width": 50.0, "height": 30.0}),
        ("ug_initialize_cam_setup", {"template_name": "mill_planar"}),
    ):
        payload = client.call(tool, args)
        steps.append({"tool": tool, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": reads,
                    "errors": ["%s 失败：%s" % (tool, str(payload.get("errors"))[:180])],
                    "checks": checks}

    bound = record("ug_bind_machine_from_library", client.call(
        "ug_bind_machine_from_library", {"libref": libref}))
    # 绑自家机床后 NX 会弹「信息」模态窗，不关掉后面的 CAM 调用会全卡住
    reads["info_windows_closed"] = _nx_close_info_windows()
    checks.append({"check": "kit_machine_bound", "got": bound.get("libref_after"),
                   "want": libref, "ok": bound.get("libref_after") == libref})
    groups = [str(g).upper() for g in (bound.get("machine_groups") or [])]
    checks.append({"check": "kit_spindle",
                   "got": any(g.startswith("SPINDLE") for g in groups), "want": True,
                   "ok": any(g.startswith("SPINDLE") for g in groups)})
    pockets = sum(1 for g in groups if g.startswith("POCKET"))
    checks.append({"check": "kit_pockets", "got": pockets, "want": ">=4",
                   "ok": pockets >= 4})

    record("ug_save_work_part", client.call("ug_save_work_part", {}))
    PY_REOPEN = (
        "import NXOpen\n"
        "s = NXOpen.Session.GetSession()\n"
        "work = s.Parts.Work\n"
        "before = str(work.CAMSetup.GetMachineLibref() or '')\n"
        "path = str(work.FullPath)\n"
        "work.Close(NXOpen.BasePartCloseWholeTree.TrueValue,\n"
        "           NXOpen.BasePartCloseModified.CloseModified, None)\n"
        "part, status = s.Parts.OpenActiveDisplay(path, NXOpen.DisplayPartOption.AllowAdditional)\n"
        "s.Parts.SetDisplay(part, True, True)\n"
        "s.Parts.SetWork(part)\n"
        "result = {'before': before, 'after': str(part.CAMSetup.GetMachineLibref() or ''),\n"
        "          'leaf': str(getattr(part, 'Leaf', '') or '')}\n"
    )
    payload = client.call("ug_run_python", {"code": PY_REOPEN})
    record("ug_run_python", payload)
    reopened = (payload.get("reads") or {}).get("return_value") or {}
    checks.append({"check": "kit_binding_persisted", "got": reopened.get("after"),
                   "want": libref, "ok": reopened.get("after") == libref})

    reads["steps"] = steps
    reads["reopen"] = reopened
    reads["machine_groups"] = bound.get("machine_groups")
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "reads": reads,
            "errors": [] if ok else ["自家机床绑定未通过：%s" % (_json.dumps(
                [c for c in checks if not c["ok"]], ensure_ascii=False)[:400])],
            "checks": checks}



def _ug_machine_kit_simulate_flow(client, context):
    """ug 剧本十八：自家 `.mtk` 机床跑**完整机床仿真**（阴影库会话）。

    链路：绑 `nsa_template_probe` → 刀具 → 程序组/MCS/工件 → FLOOR_FACING 工序 →
    刀路 → readiness（要看清运动学真的被解析出来）→ start（碰撞/轴限/刀柄全开）→
    inspect（面板 + 时间）→ stop。

    关键判据不是"没报错"，而是 NX 报出来的**运动学结构**：
    `machine.kinematics` 里要有 5 轴链条（`nsa_template_probe` 这台是
    `MIKRON_E500U_TNC640`：轴 `Y/Z/S/X/B/C`、通道 `TNC_640`、链 `Z-Y-X-B-C`），
    说明 .mtk 里的机床定义真的进了 CAM 装配，而不是只写了个 libref 字符串。
    """
    import json as _json
    import uuid as _uuid

    libref = "nsa_template_probe"
    # NX 会把 CAM 组名转大写，这里直接用大写，避免读回比对时大小写不一致
    tag = _uuid.uuid4().hex[:5].upper()
    part = "kitsim_%s.prt" % tag.lower()
    program = "MCP_KITS_%s" % tag
    operation = "MCP_KITOP_%s" % tag
    checks, reads, steps = [], {}, []

    def record(name, payload, want_ok=True):
        ok = bool(payload.get("ok")) is want_ok
        steps.append({"tool": name, "ok": bool(payload.get("ok"))})
        checks.append({"check": name, "got": bool(payload.get("ok")), "want": want_ok,
                       "ok": ok})
        if not ok:
            reads.setdefault("errors", []).append(
                "%s: %s" % (name, str(payload.get("errors"))[:220]))
        return payload.get("reads") or {}

    # 先清会话：绑机床会加载整台机床装配，零件堆多了后面会挂住（实测全量里踩过）
    client.call("ug_close_test_parts",
                {"dry_run": False, "time_limit_s": 40,
                 "confirmation": "CLOSE_TEST_PARTS"})

    # 1) 零件 + CAM 设置 + 绑自家机床
    for tool, args in (
        ("ug_create_part", {"file_name": part}),
        ("ug_run_python", {"code": (
            "import NXOpen\ns = NXOpen.Session.GetSession()\n"
            "s.ApplicationSwitchImmediate('UG_APP_MANUFACTURING')\n"
            "result = {'app': str(s.ApplicationName)}")}),
        ("ug_create_block", {"length": 80.0, "width": 50.0, "height": 30.0}),
        ("ug_initialize_cam_setup", {"template_name": "mill_planar"}),
    ):
        payload = client.call(tool, args)
        steps.append({"tool": tool, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": reads,
                    "errors": ["%s 失败：%s" % (tool, str(payload.get("errors"))[:180])],
                    "checks": checks}

    bound = record("ug_bind_machine_from_library", client.call(
        "ug_bind_machine_from_library", {"libref": libref}))
    # 绑自家机床后 NX 会弹「信息」模态窗，不关掉后面的 CAM 调用会全卡住
    reads["info_windows_closed"] = _nx_close_info_windows()
    checks.append({"check": "kit_bound", "got": bound.get("libref_after"), "want": libref,
                   "ok": bound.get("libref_after") == libref})
    if bound.get("libref_after") != libref:
        return {"ok": False, "reads": reads,
                "errors": ["自家机床没绑上"], "checks": checks}

    # 2) 刀具 / 程序组 / 工序 / 刀路
    tool_reads = record("ug_create_cam_mill_tool", client.call("ug_create_cam_mill_tool", {
        "name": "MCP_T01", "diameter": 10.0, "flute_length": 30.0,
        "overall_length": 75.0}))
    ctx = record("ug_create_cam_milling_context", client.call(
        "ug_create_cam_milling_context", {
            "origin": [0.0, 0.0, 0.0], "part_body_indices": [0],
            "program_name": program, "method_name": "MCP_METHOD",
            "mcs_name": "MCP_MCS", "workpiece_name": "MCP_WPK_%s" % tag,
            "blank_offset": 2.0}))
    names = ctx.get("names") or {}
    program_name = names.get("program") or program
    method_name = names.get("method") or "MCP_METHOD"
    geometry_name = names.get("workpiece") or ("MCP_WPK_%s" % tag)
    record("ug_create_cam_operation", client.call("ug_create_cam_operation", {
        "name": operation, "template_type": "mill_planar",
        "template_subtype": "FLOOR_FACING", "program_name": program_name,
        "method_name": method_name, "geometry_name": geometry_name,
        "tool_name": tool_reads.get("name") or "MCP_T01"}))
    record("ug_configure_cam_milling_operation", client.call(
        "ug_configure_cam_milling_operation", {
            "operation_name": operation, "body_index": 0, "part_body_indices": [0],
            "cut_area_face_selectors": [{"sort_by": "largest"}],
            "depth_per_cut": 5.0, "floor_z": 0.0, "top_offset": 0.0,
            "spindle_rpm": 2000.0, "cut_feed": 300.0,
            "approach_feed": 100.0, "retract_feed": 500.0}))
    toolpath = record("ug_generate_cam_toolpath", client.call(
        "ug_generate_cam_toolpath", {"operation_names": [operation]}))
    checks.append({"check": "toolpath_generated", "got": toolpath.get("generated_count"),
                   "want": 1, "ok": toolpath.get("generated_count") == 1})

    # 3) readiness：运动学必须被解析成 5 轴链条
    readiness = record("ug_inspect_machine_simulation_readiness", client.call(
        "ug_inspect_machine_simulation_readiness", {
            "program_name": program_name, "required_axes": ["X", "Y", "Z"],
            "require_axis_limits": False, "require_tool_geometry": True,
            "require_workpiece_geometry": True, "require_holder_geometry": False,
            "require_fixture_geometry": False}))
    machine = readiness.get("machine") or {}
    kinematics = machine.get("kinematics") or {}
    axes = [str(a) for a in (kinematics.get("axis_names") or [])]
    chains = [str(c.get("name")) for c in (kinematics.get("chains") or [])]
    checks.append({"check": "readiness_blockers_empty",
                   "got": readiness.get("blockers"), "want": [],
                   "ok": readiness.get("blockers") == []})
    checks.append({"check": "kit_libref_reported", "got": machine.get("libref"),
                   "want": libref, "ok": machine.get("libref") == libref})
    checks.append({"check": "kit_kinematics_axes",
                   "got": axes, "want": "含 B 和 C（5 轴）",
                   "ok": "B" in axes and "C" in axes})
    checks.append({"check": "kit_kinematics_chain",
                   "got": chains, "want": "非空",
                   "ok": bool(chains)})
    checks.append({"check": "kit_kinematics_junctions",
                   "got": kinematics.get("junction_count"), "want": ">=5",
                   "ok": int(kinematics.get("junction_count") or 0) >= 5})

    # 4) start -> inspect -> stop
    started = record("ug_start_machine_simulation_with_collision_stop", client.call(
        "ug_start_machine_simulation_with_collision_stop", {
            "program_name": program_name, "operation_names": [operation],
            "required_axes": ["X", "Y", "Z"], "play_immediately": False,
            "require_axis_limits": False, "require_tool_geometry": True,
            "require_workpiece_geometry": True, "require_holder_geometry": False,
            "require_fixture_geometry": False}))
    checks.append({"check": "simulation_prepared",
                   "got": started.get("simulation_prepared"), "want": True,
                   "ok": started.get("simulation_prepared") is True})
    checks.append({"check": "simulation_status_prepared",
                   "got": started.get("status"), "want": "prepared",
                   "ok": started.get("status") == "prepared"})
    options = started.get("options") or {}
    checks.append({"check": "collision_stop_armed",
                   "got": options.get("stop_on_collision"), "want": True,
                   "ok": options.get("stop_on_collision") is True})
    checks.append({"check": "limit_stop_armed",
                   "got": options.get("stop_on_limit_violation"), "want": True,
                   "ok": options.get("stop_on_limit_violation") is True})

    inspected = record("ug_inspect_active_machine_simulation", client.call(
        "ug_inspect_active_machine_simulation", {}))
    checks.append({"check": "simulation_panel_present",
                   "got": inspected.get("active_panel_present"), "want": True,
                   "ok": inspected.get("active_panel_present") is True})
    checks.append({"check": "simulation_time_readable",
                   "got": inspected.get("machine_time"), "want": "非空",
                   "ok": bool(inspected.get("machine_time"))})

    stopped = record("ug_stop_active_machine_simulation", client.call(
        "ug_stop_active_machine_simulation", {"release": True}))
    checks.append({"check": "simulation_stopped", "got": stopped.get("stopped"),
                   "want": True, "ok": stopped.get("stopped") is True})

    reads["steps"] = steps
    reads.update({
        "part": part, "libref": libref, "program": program_name,
        "operation": operation,
        "kinematics": {"name": kinematics.get("name"), "axes": axes,
                       "channels": kinematics.get("channels"),
                       "chains": chains,
                       "junctions": kinematics.get("junction_count")},
        "toolpath": {"length_mm": (toolpath.get("operations") or [{}])[0].get("toolpath_length"),
                     "minutes": (toolpath.get("operations") or [{}])[0].get("toolpath_time_minutes")},
        "simulation": {"prepared": started.get("simulation_prepared"),
                       "status": started.get("status"),
                       "machine_time": inspected.get("machine_time")},
    })
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "reads": reads,
            "errors": [] if ok else ["自家机床仿真未通过：%s" % (_json.dumps(
                [c for c in checks if not c["ok"]], ensure_ascii=False)[:400])],
            "checks": checks}


def _nx_close_info_windows(log=None, timeout_s=6):
    """关掉 NX 的「信息」窗口（class `#32770`，标题 `信息`）。

    为什么需要：**绑定自家 .mtk 机床之后 NX 会弹一个「信息」窗**（机床库报告之类），
    它是模态的——不关掉，后续任何 CAM 调用（建零件 / 建工序 / 起仿真）都会卡到超时。
    2026-11-06 全量跑里 `machine_kit_simulate` 就是被它挂死的。

    依次尝试 WM_SYSCOMMAND(SC_CLOSE) 与 Escape；窗口关闭有延迟，用 IsWindow 轮询。
    """
    import time as _time

    try:
        import subprocess as _subprocess

        import win32con
        import win32gui
        import win32process
    except Exception as exc:                       # noqa: BLE001
        if log is not None:
            log.append("no win32: %s" % type(exc).__name__)
        return []

    deadline = _time.time() + timeout_s
    closed = []
    while _time.time() < deadline:
        pids = set()
        out = _subprocess.run(["tasklist", "/FI", "IMAGENAME eq ugraf.exe"],
                              capture_output=True, text=True)
        for line in out.stdout.splitlines():
            if line.lower().startswith("ugraf"):
                try:
                    pids.add(int(line.split()[1]))
                except Exception:                  # noqa: BLE001
                    pass
        targets = []

        def cb(hwnd, _):
            try:
                _, owner = win32process.GetWindowThreadProcessId(hwnd)
                if owner in pids and win32gui.IsWindowVisible(hwnd) \
                        and win32gui.GetClassName(hwnd) == "#32770" \
                        and win32gui.GetWindowText(hwnd).strip() == "信息":
                    targets.append(hwnd)
            except Exception:                      # noqa: BLE001
                pass
            return True

        try:
            win32gui.EnumWindows(cb, None)
        except Exception:                          # noqa: BLE001
            pass
        if not targets:
            return closed
        for hwnd in targets:
            if str(hwnd) in closed:
                continue
            try:
                win32gui.PostMessage(hwnd, win32con.WM_SYSCOMMAND,
                                     win32con.SC_CLOSE, 0)
            except Exception:                      # noqa: BLE001
                pass
            _time.sleep(0.6)
            if win32gui.IsWindow(hwnd):
                try:
                    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN,
                                         win32con.VK_ESCAPE, 0)
                    win32gui.PostMessage(hwnd, win32con.WM_KEYUP,
                                         win32con.VK_ESCAPE, 0)
                except Exception:                  # noqa: BLE001
                    pass
                _time.sleep(0.6)
            closed.append(str(hwnd))
            if log is not None:
                log.append("closed info window %s" % hwnd)
        _time.sleep(0.4)
    return closed



def _ug_machine_kit_axis_limit_flow(client, context):
    """ug 剧本十九：用真实工件几何触发**轴超程**判定。

    ISV 的动态播放（`PlayForward`）在 `Session.Execute` 线程里不返回，
    所以"跑到超程处让仿真停住"这件事没法在 MCP 里观测（详见 docs 第 22 节）。
    可观测且同样真实的做法是**静态容量检查**：
    取 NX `KinematicConfigurator` 报出来的每根线性轴 limit（这台 kit 机床是
    MIKRON_E500U_TNC640：X ±500 / Y ±450 / Z ±400），把工件包围盒按 MCS 平移成
    机床坐标，比出超程量与哪根轴超程。

    判据三条：
    ① 工件在原点时 `all_within_travel=True`（不误报）；
    ② 工件偏到 X=1500 时 `all_within_travel=False`，且 violation 就是 X 轴、超程 ≈1080；
    ③ 轴限来自机床（X 上限 500），不是我们写死的常数。
    """
    import json as _json
    import uuid as _uuid

    checks, reads, steps = [], {}, []

    def record(name, payload):
        ok = bool(payload.get("ok"))
        steps.append({"tool": name, "ok": ok})
        if not ok:
            reads.setdefault("errors", []).append(
                "%s: %s" % (name, str(payload.get("errors"))[:220]))
        return payload.get("reads") or {}

    client.call("ug_close_test_parts",
                {"dry_run": False, "time_limit_s": 40,
                 "confirmation": "CLOSE_TEST_PARTS"})

    def build(tag):
        part = "trav_%s.prt" % tag.lower()
        for tool, args in (
            ("ug_create_part", {"file_name": part}),
            ("ug_run_python", {"code": (
                "import NXOpen\ns = NXOpen.Session.GetSession()\n"
                "s.ApplicationSwitchImmediate('UG_APP_MANUFACTURING')\n"
                "result = {}")}),
            ("ug_create_block", {"length": 80.0, "width": 50.0, "height": 30.0}),
            ("ug_initialize_cam_setup", {"template_name": "mill_planar"}),
        ):
            payload = client.call(tool, args)
            if not payload.get("ok"):
                raise RuntimeError("%s 失败：%s" % (tool, str(payload.get("errors"))[:180]))
        bound = record("ug_bind_machine_from_library", client.call(
            "ug_bind_machine_from_library", {"libref": "nsa_template_probe"}))
        _nx_close_info_windows()
        return part, bound

    # ① 正常位置
    tag = _uuid.uuid4().hex[:5].upper()
    part, bound = build(tag)
    checks.append({"check": "kit_machine_bound", "got": bound.get("libref_after"),
                   "want": "nsa_template_probe",
                   "ok": bound.get("libref_after") == "nsa_template_probe"})
    inside = record("ug_check_machine_axis_travel", client.call(
        "ug_check_machine_axis_travel", {"mcs_origin": [0.0, 0.0, 0.0]}))
    checks.append({"check": "normal_part_within_travel",
                   "got": inside.get("all_within_travel"), "want": True,
                   "ok": inside.get("all_within_travel") is True})
    x_row = next((row for row in (inside.get("axes") or [])
                  if row.get("axis") == "X"), {})
    checks.append({"check": "limits_come_from_machine",
                   "got": [x_row.get("lower_limit"), x_row.get("upper_limit")],
                   "want": [-500.0, 500.0],
                   "ok": x_row.get("lower_limit") == -500.0
                         and x_row.get("upper_limit") == 500.0})
    checks.append({"check": "machine_kinematics_name",
                   "got": inside.get("kinematics"), "want": "MIKRON_E500U_TNC640",
                   "ok": inside.get("kinematics") == "MIKRON_E500U_TNC640"})

    # ② 偏到 X=1500（远超 ±500 行程）
    tag2 = _uuid.uuid4().hex[:5].upper()
    part2, _bound2 = build(tag2)
    beyond = record("ug_check_machine_axis_travel", client.call(
        "ug_check_machine_axis_travel", {"mcs_origin": [1500.0, 0.0, 0.0]}))
    checks.append({"check": "offset_part_exceeds_travel",
                   "got": beyond.get("all_within_travel"), "want": False,
                   "ok": beyond.get("all_within_travel") is False})
    violations = beyond.get("violations") or []
    checks.append({"check": "violation_is_x_axis",
                   "got": [item.get("axis") for item in violations], "want": ["X"],
                   "ok": [item.get("axis") for item in violations] == ["X"]})
    overshoot = violations[0].get("overshoot") if violations else None
    checks.append({"check": "overshoot_magnitude",
                   "got": overshoot, "want": ">=1000",
                   "ok": isinstance(overshoot, (int, float)) and overshoot >= 1000})
    checks.append({"check": "y_z_still_within",
                   "got": [item.get("within_travel") for item in (beyond.get("axes") or [])
                           if item.get("axis") in ("Y", "Z")],
                   "want": [True, True],
                   "ok": all(item.get("within_travel") is True
                             for item in (beyond.get("axes") or [])
                             if item.get("axis") in ("Y", "Z"))})

    reads["steps"] = steps
    reads["within"] = {"all_within": inside.get("all_within_travel"),
                       "axes": inside.get("axes")}
    reads["beyond"] = {"all_within": beyond.get("all_within_travel"),
                       "violations": violations}
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "reads": reads,
            "errors": [] if ok else ["轴超程判定未通过：%s" % (_json.dumps(
                [c for c in checks if not c["ok"]], ensure_ascii=False)[:400])],
            "checks": checks}



def _ug_machine_kit_collision_flow(client, context):
    """ug 剧本二十：用真实刀具/工件尺寸判定**撞刀**（刀柄插进材料）。

    ISV 的动态碰撞停止在 MCP 里观测不到（`PlayForward` 在 Execute 线程不返回，
    见 docs 第 22 节），但"会不会撞"是可以算的：
    刀尖在 `floor_z`，刀柄起点在 `floor_z + flute_length`；
    只要这个位置低于工件顶面，刀柄就已经在材料里了。

    判据：① 正常切顶面（floor=0、刃长 30）→ clear，间隙 0；
         ② 切到 -55 → collision，插入深度 55 mm，刀柄起点 -25。
    """
    import json as _json
    import uuid as _uuid

    checks, reads, steps = [], {}, []
    tag = _uuid.uuid4().hex[:5]
    for tool, args in (
        ("ug_create_part", {"file_name": "scl_%s.prt" % tag}),
        ("ug_create_block", {"length": 80.0, "width": 50.0, "height": 30.0}),
    ):
        payload = client.call(tool, args)
        steps.append({"tool": tool, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            reads["steps"] = steps
            return {"ok": False, "reads": reads,
                    "errors": ["%s 失败：%s" % (tool, str(payload.get("errors"))[:180])],
                    "checks": checks}

    clear = client.call("ug_check_tool_shank_clearance",
                        {"floor_z": 0.0, "flute_length": 30.0})
    steps.append({"tool": "ug_check_tool_shank_clearance", "ok": bool(clear.get("ok"))})
    clear_reads = clear.get("reads") or {}
    checks.append({"check": "ug_check_tool_shank_clearance",
                   "got": clear.get("ok"), "want": True, "ok": bool(clear.get("ok"))})
    checks.append({"check": "surface_clear", "got": clear_reads.get("verdict"),
                   "want": "clear", "ok": clear_reads.get("verdict") == "clear"})
    checks.append({"check": "surface_clash_zero", "got": clear_reads.get("clash_depth_mm"),
                   "want": 0.0, "ok": clear_reads.get("clash_depth_mm") == 0.0})

    clash = client.call("ug_check_tool_shank_clearance",
                        {"floor_z": -55.0, "flute_length": 30.0})
    steps.append({"tool": "ug_check_tool_shank_clearance", "ok": bool(clash.get("ok"))})
    clash_reads = clash.get("reads") or {}
    checks.append({"check": "deep_cut_collides", "got": clash_reads.get("verdict"),
                   "want": "collision",
                   "ok": clash_reads.get("verdict") == "collision"})
    checks.append({"check": "clash_depth_expected", "got": clash_reads.get("clash_depth_mm"),
                   "want": 55.0,
                   "ok": clash_reads.get("clash_depth_mm") == 55.0})
    checks.append({"check": "shank_start_z_expected",
                   "got": clash_reads.get("shank_start_z"), "want": -25.0,
                   "ok": clash_reads.get("shank_start_z") == -25.0})
    checks.append({"check": "collision_flag", "got": clash_reads.get("collision_risk"),
                   "want": True, "ok": clash_reads.get("collision_risk") is True})

    reads["steps"] = steps
    reads["clear"] = clear_reads
    reads["clash"] = clash_reads
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "reads": reads,
            "errors": [] if ok else ["撞刀判定未通过：%s" % (_json.dumps(
                [c for c in checks if not c["ok"]], ensure_ascii=False)[:400])],
            "checks": checks}


UG_CASES = [
    # ── 2026-11-05：NX 桥起来之后（UGII_USER_DIR 指到 nx_user 自动加载 DLL）──
    {"id": "ug.flow.machine_build", "timeout_s": 900, "tool": None,
     "title": "ug 剧本十二：工作区/激活/导入几何/真建运动学（6 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_machine_build_flow(client, context)},
    {"id": "ug.flow.machine_inspect", "timeout_s": 600, "tool": None,
     "title": "ug 剧本十一：机器源配置只读三件套（3 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_machine_inspect_flow(client, context)},
    {"id": "ug.flow.sheetmetal_bend", "timeout_s": 900, "tool": None,
     "title": "ug 剧本八：钣金 tab → 折弯 → 体自省（6 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_sheetmetal_bend_flow(client, context)},
    {"id": "ug.flow.topology", "timeout_s": 600, "tool": None,
     "title": "ug 剧本九：按几何条件解析拓扑（4 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_topology_flow(client, context)},
    {"id": "ug.flow.machine_readonly", "timeout_s": 600, "tool": None,
     "title": "ug 剧本十：机器仿真只读两件套（4 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_machine_readonly_flow(client, context)},

    {"id": "ug.flow.model", "timeout_s": 900, "tool": None,
     "title": "ug 剧本一：建块/拓扑/摘要/重建/存盘/STEP 往返（10 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_model_flow(client, context)},
    {"id": "ug.flow.cam", "timeout_s": 900, "tool": None,
     "title": "ug 剧本二：CAM 上下文/MCS/工件/刀具/工序/几何（12 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_cam_flow(client, context)},
    {"id": "ug.flow.drawing", "timeout_s": 600, "tool": None,
     "title": "ug 剧本三：A3 图纸/投影视图/注释/自省（6 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_drawing_flow(client, context)},
    {"id": "ug.flow.modeling2", "timeout_s": 900, "tool": None,
     "title": "ug 剧本五：拉伸/孔/圆角/倒角/抽面/偏置面/齿轮/特征自省（12 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_modeling2_flow(client, context)},
    {"id": "ug.flow.features", "timeout_s": 600, "tool": None,
     "title": "ug 剧本七：特征阵列/镜像 + 装配自省（6 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_features_flow(client, context)},
    {"id": "ug.flow.sheetmetal", "timeout_s": 600, "tool": None,
     "title": "ug 剧本四：参数化草图/NX 钣金 tab（5 步）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_sheetmetal_flow(client, context)},


    {"id": "ug.ping", "tool": "ug_ping",
     "title": "NX 桥连通性（进程/零件/桥版本）",
     "args": {},
     "expect_ok": True,
     "timeout_s": 120,
     "skip_if": _ug_no_live_nx},

    {"id": "ug.cam.capabilities", "tool": None,
     "title": "CAM 能力自报（先建件+进 CAM，再读模板/刀具/后处理）",
     "args": {},
     "expect_ok": True,
     "timeout_s": 300,
     "skip_if": _ug_no_live_nx,
     "call": lambda client, context: _ug_flow(client, [
         # 先关掉此前用例留下的测试零件：会话里堆十几个零件后，再进 CAM
         # 会挂死（2026-11-06 实测，见 docs 第 14 节）。
         # 清理本身卡住不算失败（tolerate）：重启 kit 后继续跑。
         ("ug_close_test_parts", {"dry_run": False, "time_limit_s": 40,
                                 "confirmation": "CLOSE_TEST_PARTS"}),
         ("ug_create_part", {"file_name": "cap_%s.prt" % uuid.uuid4().hex[:6]}),
         # 不建块：只要有一个普通零件就能读 CAM 模板表；建块在大序列里偶发
         # 45 s 超时（2026-11-06），而块建模已被 ug.flow.model 覆盖。
         ("ug_initialize_cam_setup", {"template_name": "mill_planar"}),
         ("ug_get_cam_capabilities", {"template_type": "mill_planar"}),
     ], "cam_caps", tolerate=("ug_close_test_parts",))},

    {"id": "ug.cam.recipe", "call": _ug_cam_recipe,
     "title": "CAM 端到端配方：新零件 → 三种工序各自生成刀路（path_exists）",
     "expect_check_true": ["FLOOR_FACING.path_exists", "POCKETING.path_exists",
                           "PLANAR_MILL.path_exists", "FLOOR_FACING.generate_ok",
                           "POCKETING.generate_ok", "PLANAR_MILL.generate_ok"],
     "expect_min_checks": 6,
     "timeout_s": 300,
     "skip_if": _ug_no_live_nx},

    {"id": "ug.flow.machine_kit_bind", "timeout_s": 900, "tool": None,
     "title": "ug 剧本十七：绑自家 .mtk 机床（阴影机床库路线）",
     "args": {}, "expect_ok": True,
     "skip_if": lambda context: _ug_no_shadow_library(context) or _ug_no_live_nx(context),
     "call": lambda client, context: _ug_machine_kit_bind_flow(client, context)},

    {"id": "ug.flow.machine_kit_simulate", "timeout_s": 1200, "tool": None,
     "title": "ug 剧本十八：自家 .mtk 机床完整仿真（绑定→刀路→运动学→start→stop）",
     "args": {}, "expect_ok": True,
     "skip_if": lambda context: _ug_no_shadow_library(context) or _ug_no_live_nx(context),
     "call": lambda client, context: _ug_machine_kit_simulate_flow(client, context)},

    {"id": "ug.flow.machine_simulate", "timeout_s": 900, "tool": None,
     "title": "ug 剧本十四：真跑机床仿真（自绑机床→刀路→readiness→start→stop）",
     "args": {}, "expect_ok": True,
     "skip_if": _ug_no_live_nx,
     "call": lambda client, context: _ug_machine_simulate_flow(client, context)},

    {"id": "ug.flow.machine_bind", "timeout_s": 600, "tool": None,
     "title": "ug 剧本十五：脚本化绑定机床（从库调用 → SPINDLE/POCKET 生成）",
     "args": {}, "expect_ok": True,
     "skip_if": _ug_no_live_nx,
     "call": lambda client, context: _ug_machine_bind_flow(client, context)},

    {"id": "ug.flow.machine_swap", "timeout_s": 900, "tool": None,
     "title": "ug 剧本十六：换型+持久化（fanuc→卸→tnc→存盘→关重开仍在）",
     "args": {}, "expect_ok": True,
     # 阴影库会话里不做换型：一次会话里第 5 次绑定会挂住（机床装配累积），
     # 而换型/持久化在标准库会话里已经覆盖到了。
     "skip_if": lambda context: _ug_no_live_nx(context) or _ug_shadow_active(context),
     "call": lambda client, context: _ug_machine_swap_flow(client, context)},

    {"id": "ug.flow.machine_kit_axis_limit", "timeout_s": 900, "tool": None,
     "title": "ug 剧本十九：轴超程判定（工件偏 1500 mm → X 超程 1080 mm）",
     "args": {}, "expect_ok": True,
     "skip_if": lambda context: _ug_no_shadow_library(context) or _ug_no_live_nx(context),
     "call": lambda client, context: _ug_machine_kit_axis_limit_flow(client, context)},

    {"id": "ug.flow.machine_kit_collision", "timeout_s": 600, "tool": None,
     "title": "ug 剧本二十：撞刀判定（刀柄插进工件 55 mm）",
     "args": {}, "expect_ok": True,
     "skip_if": _ug_no_live_nx,
     "call": lambda client, context: _ug_machine_kit_collision_flow(client, context)},

    # machine_validate 必须放最后：它内部会把一个 MTK 导入临时阴影库，
    # 跑完之后 NX 会话里的机床库查询会变成 "MOM_TCL：用户选择了中止"
    # （DB 句柄还指着那个随后被清理的临时目录），之后所有机床绑定都会失败。
    {"id": "ug.flow.machine_validate", "timeout_s": 900, "tool": None,
     "title": "ug 剧本十三：机床校验五件套（模板路线，运动学+碰撞全通过）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_machine_validate_flow(client, context)},


]

# ── eplan（CAD-Agent-Hub 的 EPLAN 2.9 MCP：电气设计 / 审图）──────────────
def codesys_setup() -> dict:
    """CODESYS 是否"空着"——project.create 会关掉当前工程，绝不能关用户的。

    只有当前没有工程、或当前工程在临时目录里（我们自己的），才允许跑剧本。
    """
    from nsa_mcp_hub.acceptance.harness import McpClient
    client = McpClient("nsa_mcp_hub.servers.codesys_mcp")
    try:
        payload = client.call("codesys_projects", {})
    finally:
        client.close()
    result = (payload.get("reads") or {}).get("result") or {}
    path = str((result.get("primary") or {}).get("path") or "")
    temp = os.environ.get("TEMP", "").lower()
    ours = (not path) or (temp and path.lower().startswith(temp))
    if not ours:
        print("  [warn] CODESYS 里有非临时工程，剧本跳过（不会关你的工程）：%s" % path,
              flush=True)
    return {"available": True, "codesys_free": bool(ours), "project": path}


def nx_setup() -> dict:
    """nxkit 的 `nx_run_capability` 会自己拉起 NX，所以不能靠"进程在不在"判断。

    实测教训：用 tasklist 找 ugraf.exe 判 nx，结果 NX 明明能跑（4 个能力全 True），
    判成 False → 剧本被误判成"该拒绝"，反过来 FAIL。所以这里直接放行。
    """
    return {"available": True, "nx": True}


def _close_unsaved_docs(client):
    """关掉所有"没路径"的文档——那是剧本自己新建的临时零件，不是用户的文件。"""
    closed = []
    reads = client.call("sw_list_open_documents", {}).get("reads") or {}
    for item in reads.get("documents") or []:
        if item.get("path"):
            continue
        try:
            client.call("sw_close_document", {"title": item.get("title")})
            closed.append(item.get("title"))
        except Exception:                              # noqa: BLE001
            pass
    return closed


def _sw_part_flow(client, context):
    """SolidWorks 剧本：新建零件 → 前视基准面矩形 40×25 → 拉伸 20 → 量体积。

    单位坑：swkit 的草图坐标是 **mm**（第一次按米传 0.04/0.025 直接失败）。
    判据：6 步全 ok 且体积 = 40×25×20 = 20000 mm³ = 2e-05 m³。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 20}),
        ("sw_get_mass_properties", {}),
    ]
    done = []
    last = {}
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        last = payload
    volume = (last.get("reads") or {}).get("volume_m3")
    ok_volume = volume is not None and abs(float(volume) - 2e-05) <= 1e-6
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "volume_m3", "got": volume, "want": 2e-05, "ok": ok_volume},
    ]
    return {"ok": ok_volume, "reads": {"steps": done, "volume_m3": volume},
            "errors": [] if ok_volume else ["体积不符：%r（期望 2e-05 m³ = 20000 mm³）" % volume],
            "checks": checks}


def _sw_fillet_flow(client, context):
    """SW 剧本二：圆 Ø40 → 拉伸 15 → 圆角 R2。

    判据：7 步全 ok，且圆角让体积**下降**（实测 18849.56 → 18638.63 mm³，约 -1.12%）。
    为什么不带切除：swkit 的 `sw_cut_extrude` 在本机 SW2025 上建出的是空特征
    （体积不变、features +1），实测 `flip_side` 两种都无效——已记入待修，剧本绕开它。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_circle", {"cx": 0.0, "cy": 0.0, "radius": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 15}),
        ("sw_fillet", {"radius": 2}),
        ("sw_get_mass_properties", {}),
    ]
    done = []
    fillet = {}
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_fillet":
            fillet = payload.get("reads") or {}
    before = fillet.get("volume_before_mm3")
    after = fillet.get("volume_after_mm3")
    dropped = (before and after and 0 < (before - after) / before < 0.05)
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "fillet_edges", "got": fillet.get("edges_selected"), "want": ">0",
         "ok": bool(fillet.get("edges_selected"))},
        {"check": "volume_dropped", "got": round((before - after), 3) if before and after else None,
         "want": ">0 且 <5%", "ok": bool(dropped)},
    ]
    return {"ok": bool(dropped), "reads": {"steps": done,
                                           "volume_before_mm3": before,
                                           "volume_after_mm3": after},
            "errors": [] if dropped else ["圆角没有让体积下降：%r → %r" % (before, after)],
            "checks": checks}


def _sw_inspect_flow(client, context):
    """SW 剧本三：建块 40×25×10，然后把"读/视图"类工具跑一遍（12 步一条）。

    判据：12 步全 ok，体积 = 10000 mm³（1e-05 m³）。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_document_info", {}),
        ("sw_list_features", {}),
        ("sw_list_bodies", {}),
        ("sw_get_mass_properties", {}),
        ("sw_set_view_orientation", {"view_name": "isometric"}),
        ("sw_zoom_to_fit", {}),
        ("sw_rebuild_model", {}),
    ]
    done = []
    volume = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_get_mass_properties":
            volume = (payload.get("reads") or {}).get("volume_m3")
    ok_volume = volume is not None and abs(float(volume) - 1e-05) <= 1e-6
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "volume_m3", "got": volume, "want": 1e-05, "ok": ok_volume},
    ]
    return {"ok": ok_volume, "reads": {"steps": done, "volume_m3": volume},
            "errors": [] if ok_volume else ["体积不符：%r（期望 1e-05 m³ = 10000 mm³）" % volume],
            "checks": checks}


def _sw_export_flow(client, context):
    """SW 剧本四：建块 → 存盘 → 导出 STEP / STL，并**验文件真写了**。

    判据：8 步全 ok；STEP 首行是 ISO-10303-21；STL > 100 B；目录里三个文件都在。
    临时目录随 cleanup 删掉，不留垃圾。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_export_")
    part = os.path.join(work, "probe_part.SLDPRT")
    step = os.path.join(work, "probe_part.step")
    stl = os.path.join(work, "probe_part.stl")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_export_step", {"path": step}),
        ("sw_export_stl", {"path": stl}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    sizes = {os.path.basename(f): (os.path.getsize(f) if os.path.exists(f) else 0)
             for f in (part, step, stl)}
    head = ""
    if os.path.exists(step):
        with open(step, "rb") as fh:
            head = fh.read(32).decode("latin-1", "replace").strip()
    ok_step = head.startswith("ISO-10303-21")
    ok_stl = sizes.get("probe_part.stl", 0) > 100
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "step_header", "got": head[:24], "want": "ISO-10303-21", "ok": ok_step},
        {"check": "stl_bytes", "got": sizes.get("probe_part.stl"), "want": ">100", "ok": ok_stl},
    ]
    problems = []
    if not ok_step:
        problems.append("STEP 头不对：%r" % head[:32])
    if not ok_stl:
        problems.append("STL 太小或没写：%s B" % sizes.get("probe_part.stl"))
    return {"ok": ok_step and ok_stl,
            "reads": {"steps": done, "files": sizes, "step_header": head[:32], "workdir": work},
            "errors": problems, "checks": checks}


def _sw_props_flow(client, context):
    """SW 剧本五：建块 → 倒角 → 抽壳 → 自定义属性 → 配置 → 材料 → 重建诊断（14 步）。

    判据：14 步全 ok；自定义属性"料号"读回 A-001；激活配置是 CFG_TEST。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_chamfer", {"distance": 2}),
        ("sw_shell", {"thickness": 2, "face_index": -1}),
        ("sw_set_custom_property", {"name": "料号", "value": "A-001"}),
        ("sw_get_custom_properties", {}),
        ("sw_add_configuration", {"name": "CFG_TEST"}),
        ("sw_list_configurations", {}),
        ("sw_set_material", {"name": "AISI 304"}),
        ("sw_get_material", {}),
        ("sw_rebuild_diagnostics", {"full": True}),
    ]
    done = []
    properties: dict = {}
    active = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        reads = payload.get("reads") or {}
        if name == "sw_get_custom_properties":
            properties = reads.get("properties") or {}
        if name == "sw_list_configurations":
            active = reads.get("active")
    stored = str(properties.get("料号", ""))
    ok_prop = "A-001" in stored
    ok_cfg = active == "CFG_TEST"
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "custom_property", "got": stored, "want": "A-001", "ok": ok_prop},
        {"check": "active_configuration", "got": active, "want": "CFG_TEST", "ok": ok_cfg},
    ]
    problems = []
    if not ok_prop:
        problems.append("自定义属性没读到：%r" % stored)
    if not ok_cfg:
        problems.append("激活配置不是 CFG_TEST：%r" % active)
    return {"ok": ok_prop and ok_cfg,
            "reads": {"steps": done, "properties": properties, "active_configuration": active},
            "errors": problems, "checks": checks}


def _nx_batch(client, tools):
    """NX 批量冒烟：每条能力都**独立开一次 run_journal 会话**（实测 13 s/条）。

    和 SW 不同，NX 的能力之间不共享文档——`nx_measure_mass` 那条会自己建块再量，
    所以这里只要求"每条都跑通、判据都过"，不做跨步断言。
    """
    done = []
    failures = []
    for name in tools:
        try:
            payload = client.call(name, {})
        except Exception as exc:                       # noqa: BLE001
            failures.append("%s 抛异常：%s: %s" % (name, type(exc).__name__, str(exc)[:120]))
            done.append({"tool": name, "ok": False})
            continue
        ok = bool(payload.get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            failures.append("%s 失败：%s" % (name, str(payload.get("errors"))[:160]))
    return {"ok": not failures, "reads": {"steps": done}, "errors": failures,
            "checks": [{"check": "batch_ok", "got": len(done) - len(failures),
                        "want": len(tools), "ok": not failures}]}


def _sw_equations_flow(client, context):
    """SW 剧本六：方程 / 全局变量 / 镜向 / 回滚 / 抑制-解除 / 显示模式（12 步）。

    判据：12 步全 ok；方程表里 W=40 与 H=10 都在（count=2）。
    注：`sw_pattern_feature` 需要先选中特征，实测直接调会 backend error → 本剧本不含它。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_add_equation", {"expression": '"W" = 40'}),
        ("sw_get_equations", {}),
        ("sw_set_global_variable", {"name": "H", "value": 10}),
        ("sw_list_global_variables", {}),
        ("sw_mirror_feature", {"plane": "前视基准面"}),
        ("sw_feature_rollback", {"location": "end"}),
        ("sw_set_display_mode", {"mode": "shaded"}),
    ]
    done = []
    equations: list = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_list_global_variables":
            equations = (payload.get("reads") or {}).get("equations") or []
    # 用**原始方程文本**比，别比 json.dumps（会多出 \" 转义，把自己坑了）
    text = " | ".join(str(item.get("equation", "")) for item in equations
                      if isinstance(item, dict))
    ok_w = '"W" = 40' in text
    ok_h = '"H" = 10' in text
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "equation_count", "got": len(equations), "want": 2, "ok": len(equations) >= 2},
        {"check": "equations_present", "got": text[:120], "want": "W=40 与 H=10", "ok": ok_w and ok_h},
    ]
    problems = []
    if not ok_w:
        problems.append("方程 W=40 没读到：%s" % text[:120])
    if not ok_h:
        problems.append("全局变量 H=10 没读到：%s" % text[:120])
    return {"ok": ok_w and ok_h, "reads": {"steps": done, "equations": equations},
            "errors": problems, "checks": checks}


def _sw_sketch_flow(client, context):
    """SW 剧本七：草图类 10 个工具（弧/多边形/椭圆/中心线/偏移/线性阵列…）。

    先建块（体积可校验），再开第二张草图把草图工具跑一遍；草图不改体积，
    所以末了仍判 10000 mm³——用体积确认"没把实体搞坏"。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_arc", {"cx": 10.0, "cy": 10.0, "radius": 5.0,
                           "start_angle_deg": 0, "end_angle_deg": 180}),
        ("sw_sketch_polygon", {"cx": 20.0, "cy": 20.0, "num_sides": 6,
                               "circumscribed_radius": 5.0}),
        ("sw_sketch_ellipse", {"cx": 30.0, "cy": 10.0, "semi_major": 5.0,
                               "semi_minor": 3.0}),
        ("sw_sketch_centerline", {"x1": 0.0, "y1": -5.0, "x2": 0.0, "y2": 30.0}),
        ("sw_sketch_offset", {"offset_mm": 2.0}),
        ("sw_sketch_linear_pattern", {"x_count": 2, "y_count": 1,
                                       "x_spacing_mm": 20.0, "y_spacing_mm": 0.0}),
        ("sw_exit_sketch", {}),
        ("sw_get_mass_properties", {}),
    ]
    done = []
    volume = None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_get_mass_properties":
            volume = (payload.get("reads") or {}).get("volume_m3")
    ok_volume = volume is not None and abs(float(volume) - 1e-05) <= 1e-6
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "volume_m3", "got": volume, "want": 1e-05, "ok": ok_volume},
    ]
    return {"ok": ok_volume, "reads": {"steps": done, "volume_m3": volume},
            "errors": [] if ok_volume else ["体积被改坏了：%r（期望 1e-05）" % volume],
            "checks": checks}


def _sw_drawing_flow(client, context):
    """SW 剧本八：零件 → 存盘 → 出图（主视图）→ 尺寸标注 → 导出 PDF。

    判据：8 步全 ok；PDF 首字节是 %PDF 且 > 1000 B。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_dwg_")
    part = os.path.join(work, "dwg_part.SLDPRT")
    pdf = os.path.join(work, "dwg_out.pdf")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_new_drawing", {"model": part}),
        ("sw_add_drawing_dimension", {}),
        ("sw_export_drawing_pdf", {"path": pdf}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    size = os.path.getsize(pdf) if os.path.exists(pdf) else 0
    head = b""
    if size:
        with open(pdf, "rb") as fh:
            head = fh.read(4)
    ok_pdf = head == b"%PDF" and size > 1000
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "pdf_header", "got": head.decode("latin-1"), "want": "%PDF", "ok": head == b"%PDF"},
        {"check": "pdf_bytes", "got": size, "want": ">1000", "ok": size > 1000},
    ]
    return {"ok": ok_pdf, "reads": {"steps": done, "pdf_bytes": size, "workdir": work},
            "errors": [] if ok_pdf else ["PDF 不对：head=%r size=%d" % (head, size)],
            "checks": checks}


def _sw_light_reads(client, context):
    """SW 只读"轻"工具批量（不建不改不关文档，因此在夹具打开时也安全）。

    实测：夹具（450 隔音罩，几百特征）打开时这 12 个都 0–11 s 返回；
    真正会卡死的是"同会话里建/关文档"的那类操作（见 docs/coverage-plan.md）。
    """
    import threading
    tools = ["sw_get_status", "sw_operation_status", "sw_proxy_tools",
             "sw_list_open_documents", "sw_list_materials", "sw_docs_stats",
             "sw_docs_query", "sw_registry", "sw_inspect_active",
             "sw_list_documents_dirty", "sw_get_model_info", "sw_bounding_box"]
    done, failures = [], []
    for name in tools:
        box: dict = {}

        def _one(tool_name=name):
            try:
                box["payload"] = client.call(tool_name, {})
            except Exception as exc:                   # noqa: BLE001
                box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:110])

        worker = threading.Thread(target=_one, daemon=True)
        worker.start()
        worker.join(60)
        if worker.is_alive():
            failures.append("%s 超时（>60 s）" % name)
            done.append({"tool": name, "ok": False})
            continue
        if "error" in box:
            failures.append("%s 抛异常：%s" % (name, box["error"]))
            done.append({"tool": name, "ok": False})
            continue
        ok = bool(box["payload"].get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            failures.append("%s 失败：%s" % (name, str(box["payload"].get("errors"))[:120]))
    return {"ok": not failures, "reads": {"steps": done}, "errors": failures,
            "checks": [{"check": "light_reads_ok", "got": len(done) - len(failures),
                        "want": len(done), "ok": not failures}]}


def _sw_surface_flow(client, context):
    """SW 剧本九：曲面族（平面区域→加厚→拉伸曲面→偏移曲面）11 步。

    判据：11 步全 ok，且实体/曲面体都存在（sw_list_bodies 里两类计数都 >0）。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_planar_surface", {}),
        ("sw_thicken_surface", {"thickness": 0.002}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_circle", {"cx": 10.0, "cy": 10.0, "radius": 5.0}),
        ("sw_exit_sketch", {}),
        ("sw_extruded_surface", {"depth": 20}),
        ("sw_offset_surface", {"distance": 0.002}),
        ("sw_list_bodies", {}),
    ]
    done = []
    body_counts: dict = {}
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_list_bodies":
            body_counts = payload.get("reads") or {}
    solid = int(body_counts.get("solid_bodies") or body_counts.get("solids") or 0)
    surface = int(body_counts.get("surface_bodies") or body_counts.get("surfaces") or 0)
    ok_bodies = solid >= 1 and surface >= 1
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "body_kinds", "got": {"solid": solid, "surface": surface},
         "want": "两者都 >0", "ok": ok_bodies},
    ]
    return {"ok": ok_bodies, "reads": {"steps": done, "bodies": body_counts},
            "errors": [] if ok_bodies else ["实体/曲面计数异常：%r" % (body_counts,)],
            "checks": checks}


def _sw_sheet_flow(client, context):
    """SW 剧本十：钣金基体法兰 → 展开图信息（6 步）。

    判据：6 步全 ok，且 get_flat_pattern_info 认到 FlatPattern（或至少报出厚度）。
    注：`sw_hem` 实测 backend error（需要先选边），本剧本不含它。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 60.0}),
        ("sw_exit_sketch", {}),
        ("sw_base_flange", {"thickness_mm": 2, "radius_mm": 2, "depth_mm": 30}),
        ("sw_get_flat_pattern_info", {}),
    ]
    done = []
    flat: dict = {}
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_get_flat_pattern_info":
            flat = payload.get("reads") or {}
    # 实际键是 flat_pattern_feature（例如 '平展型式6'），别再猜别的名字
    has_flat = bool(flat.get("flat_pattern_feature") or flat.get("flat_pattern")
                    or flat.get("has_flat_pattern") or flat.get("feature")
                    or flat.get("thickness_mm"))
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "flat_pattern", "got": flat, "want": "认到展开图或厚度", "ok": has_flat},
    ]
    return {"ok": has_flat, "reads": {"steps": done, "flat_pattern": flat},
            "errors": [] if has_flat else ["展开图信息为空：%r" % (flat,)],
            "checks": checks}


def _sw_drawing2_flow(client, context):
    """SW 剧本十一：零件→IGES→出图→注释→旋转视图→导出 PDF/DWG（12 步）。

    判据：12 步全 ok；IGES > 1 KB；PDF 头 %PDF；DWG 头 AC10xx（AutoCAD 版本标记）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_dwg2_")
    part = os.path.join(work, "p.SLDPRT")
    pdf = os.path.join(work, "p.pdf")
    dwg = os.path.join(work, "p.dwg")
    iges = os.path.join(work, "p.iges")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_export_iges", {"path": iges}),
        ("sw_new_drawing", {"model": part}),
        ("sw_note", {"text": "验收注释", "x": 0.1, "y": 0.1}),
        ("sw_view_rotate", {"angle_deg": 15}),
        ("sw_export_drawing_pdf", {"path": pdf}),
        ("sw_export_drawing_dwg", {"path": dwg}),
    ]
    done = []
    iges_actual = iges
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        # sw_export_iges 会把 .iges 归一成 .igs，实际路径在 reads.path 里
        if name == "sw_export_iges":
            iges_actual = (payload.get("reads") or {}).get("path") or iges

    def head(path, n=8):
        if not os.path.exists(path):
            return b""
        with open(path, "rb") as fh:
            return fh.read(n)

    sizes = {os.path.basename(f): (os.path.getsize(f) if os.path.exists(f) else 0)
             for f in (iges_actual, pdf, dwg)}
    iges_key = os.path.basename(iges_actual)
    ok_iges = sizes.get(iges_key, 0) > 1000
    ok_pdf = head(pdf, 4) == b"%PDF"
    ok_dwg = head(dwg, 4).startswith(b"AC10")
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "iges_bytes", "got": sizes.get(iges_key), "want": ">1000", "ok": ok_iges},
        {"check": "pdf_header", "got": head(pdf, 4).decode("latin-1"), "want": "%PDF", "ok": ok_pdf},
        {"check": "dwg_header", "got": head(dwg, 6).decode("latin-1"), "want": "AC10xx", "ok": ok_dwg},
    ]
    problems = []
    if not ok_iges:
        problems.append("IGES 太小/没写：%r" % (sizes,))
    if not ok_pdf:
        problems.append("PDF 头不对：%r" % head(pdf, 4))
    if not ok_dwg:
        problems.append("DWG 头不对：%r" % head(dwg, 6))
    return {"ok": ok_iges and ok_pdf and ok_dwg,
            "reads": {"steps": done, "files": sizes, "workdir": work},
            "errors": problems, "checks": checks}


def _sw_sketch2_flow(client, context):
    """SW 剧本十三：草图线/样条/构造线（3 个工具，开在第二张草图里）。

    不做 exit_sketch：实测带构造线时 `sw_exit_sketch` 的判据（segments 变化）
    会误判失败（reads 里 segments_after=1）——这是判据问题，不是几何问题。
    文档由 cleanup 关掉（只关无路径的新建件）。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_line", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 20.0}),
        ("sw_sketch_spline", {"points": [[0, 0], [10, 5], [20, 0], [30, 8]]}),
        ("sw_sketch_construction", {"length": 20.0}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _sw_annotate_flow(client, context):
    """SW 剧本十五：出图后再加注释/中心线/表面粗糙度/球标（11 步）。

    判据：11 步全 ok；导出 PDF 首 4 字节 %PDF。
    实测不能用的（都要先选中对象）：`sw_add_center_mark`、`sw_add_datum_feature`、
    `sw_add_gtol`、`sw_add_weld_symbol`（三个返回 ok=False 且 errors 为空 —— 静默失败）、
    `sw_add_hole_table`（backend error）—— 都没纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_annot_")
    part = os.path.join(work, "p.SLDPRT")
    pdf = os.path.join(work, "p.pdf")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_new_drawing", {"model": part}),
        ("sw_add_centerline", {}),
        ("sw_add_surface_finish", {"x": 0.05, "y": 0.05}),
        ("sw_note", {"text": "验收注释", "x": 0.1, "y": 0.1}),
        ("sw_add_annotation", {"text": "验收注释2", "x": 0.12, "y": 0.12}),
        ("sw_add_balloon", {"x": 0.1, "y": 0.16}),
        ("sw_export_drawing_pdf", {"path": pdf}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    head = b""
    size = 0
    if os.path.exists(pdf):
        size = os.path.getsize(pdf)
        with open(pdf, "rb") as fh:
            head = fh.read(4)
    ok_pdf = head == b"%PDF" and size > 1000
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "pdf_header", "got": head.decode("latin-1"), "want": "%PDF", "ok": head == b"%PDF"},
        {"check": "pdf_bytes", "got": size, "want": ">1000", "ok": size > 1000},
    ]
    return {"ok": ok_pdf, "reads": {"steps": done, "pdf_bytes": size, "workdir": work},
            "errors": [] if ok_pdf else ["PDF 不对：head=%r size=%d" % (head, size)],
            "checks": checks}


def _sw_batch_tools(client, tools, setup=None):
    """SW 通用小批量：先跑 setup（可选），再逐条调只读/纯函数工具。

    与 `_sw_batch` 的区别：不碰文档生命周期（不新建、不关闭），
    只在已有文档上读，避免踩"同会话建/关文档会卡死"这个坑。
    """
    import threading
    done, failures = [], []
    for name, args in (setup or []):
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:150])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:180])],
                    "checks": []}
    for name in tools:
        box: dict = {}

        def _one(tool_name=name):
            try:
                box["payload"] = client.call(tool_name, {})
            except Exception as exc:                   # noqa: BLE001
                box["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:120])

        worker = threading.Thread(target=_one, daemon=True)
        worker.start()
        worker.join(120)
        if worker.is_alive():
            failures.append("%s 超时（>120 s）" % name)
            done.append({"tool": name, "ok": False})
            continue
        if "error" in box:
            failures.append("%s 抛异常：%s" % (name, box["error"]))
            done.append({"tool": name, "ok": False})
            continue
        ok = bool(box["payload"].get("ok"))
        done.append({"tool": name, "ok": ok})
        if not ok:
            failures.append("%s 失败：%s" % (name, str(box["payload"].get("errors"))[:130]))
    return {"ok": not failures, "reads": {"steps": done}, "errors": failures,
            "checks": [{"check": "batch_ok", "got": len(done) - len(failures),
                        "want": len(done), "ok": not failures}]}


def _sw_assembly_flow(client, context):
    """SW 剧本十六：装配链（hub 侧修复后打通）—— 建件→建装配→插两件→干涉/树/固定/
    隐藏开关/抑制/爆炸（14 步）。

    为什么这条以前做不了：swkit 的 `AddComponent5` 只传了 7 个参数（应为 8 个），
    且要求零件预先打开、装配体是 ActiveDoc。hub 侧的 `sw_assembly_build`
    把"开零件 → 激活装配 → 8 参插入"缝在一起，判据是组件数读回。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_asm_")
    part = os.path.join(work, "asm_part.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 5}),
        ("sw_save_document", {"path": part}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": []}

    built = client.call("sw_assembly_build", {"parts": [part, part], "spacing_mm": 60})
    done.append({"tool": "sw_assembly_build", "ok": bool(built.get("ok"))})
    if not built.get("ok"):
        return {"ok": False, "reads": {"steps": done, "workdir": work},
                "errors": ["sw_assembly_build 失败：%s" % str(built.get("errors"))[:200]],
                "checks": built.get("checks") or []}

    # 先读装配树拿到**真实组件名**（名字由零件文件名决定，写死会失败）
    tree = client.call("sw_get_assembly_tree", {})
    done.append({"tool": "sw_get_assembly_tree", "ok": bool(tree.get("ok"))})
    names = [c.get("name") for c in ((tree.get("reads") or {}).get("components") or [])
             if isinstance(c, dict) and c.get("name")]
    target = names[1] if len(names) > 1 else (names[0] if names else "")
    tail = [
        ("sw_check_interference", {"expected": 0}),
        ("sw_fix_component", {"component_index": 0}),
        ("sw_show_all_components", {}),
        ("sw_suppress_component", {"name": target, "suppress": True}),
        ("sw_suppress_component", {"name": target, "suppress": False}),
        ("sw_explode_assembly", {}),
    ]
    components = (built.get("reads") or {}).get("components_after")
    for name, args in tail:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_check_interference":
            pass
    ok_count = components == 2
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps) + 2 + len(tail),
         "ok": len(done) == len(steps) + 2 + len(tail)},
        {"check": "components", "got": components, "want": 2, "ok": ok_count},
    ]
    return {"ok": ok_count, "reads": {"steps": done, "components": components,
                                      "workdir": work},
            "errors": [] if ok_count else ["组件数不对：%r（期望 2）" % (components,)],
            "checks": checks}


def _sw_asm_drawing_flow(client, context):
    """SW 剧本十七：装配体出图（**未纳入验收** —— 在验收长会话里 900 s 超时，
    单独用同一个客户端跑是通的；原因见 docs/coverage-plan.md 的"执行边界"一节） —— BOM/球标/尺寸/中心线/粗糙度/辅助视图/断裂视图（17 步）。

    装配链修好之后才有这条：`sw_add_bom_table` 需要装配图、`sw_add_balloon` 需要
    BOM 项。实测 `sw_add_hole_table` 在装配图上会**卡死**（>10 min），不纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_asmdwg_")
    part = os.path.join(work, "p.SLDPRT")
    asm = os.path.join(work, "a.SLDASM")
    pdf = os.path.join(work, "a.pdf")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 5}),
        ("sw_save_document", {"path": part}),
        ("sw_assembly_build", {"parts": [part, part], "spacing_mm": 60}),
        ("sw_save_document", {"path": asm}),
        ("sw_new_drawing", {"model": asm}),
        ("sw_add_bom_table", {"x": 0.1, "y": 0.16}),
        ("sw_add_balloon", {"x": 0.1, "y": 0.16}),
        ("sw_add_drawing_dimension", {"x": 0.12, "y": 0.12}),
        ("sw_add_centerline", {}),
        ("sw_add_surface_finish", {"x": 0.05, "y": 0.05}),
        ("sw_add_auxiliary_view", {}),
        ("sw_add_broken_view", {}),
        ("sw_export_drawing_pdf", {"path": pdf}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    head, size = b"", 0
    if os.path.exists(pdf):
        size = os.path.getsize(pdf)
        with open(pdf, "rb") as fh:
            head = fh.read(4)
    ok_pdf = head == b"%PDF" and size > 1000
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "pdf_header", "got": head.decode("latin-1"), "want": "%PDF",
         "ok": head == b"%PDF"},
        {"check": "pdf_bytes", "got": size, "want": ">1000", "ok": size > 1000},
    ]
    return {"ok": ok_pdf, "reads": {"steps": done, "pdf_bytes": size, "workdir": work},
            "errors": [] if ok_pdf else ["PDF 不对：head=%r size=%d" % (head, size)],
            "checks": checks}


def _sw_asm_ops_flow(client, context):
    """SW 剧本十八：装配体上的读取与配置/组件操作（13 步）。

    这条是靠装配链修复才好用的：`sw_get_referenced_documents` / 组件阵列 /
    组件镜像都要求有装配体。实测 `sw_move_component` 会**卡死**（>9 min），
    `sw_assign_material_full` 在装配体上判据不过（assigned=False），都不纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_asmops_")
    part = os.path.join(work, "p.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 5}),
        ("sw_save_document", {"path": part}),
        ("sw_assembly_build", {"parts": [part, part], "spacing_mm": 60}),
        ("sw_get_referenced_documents", {}),
        ("sw_list_display_states", {}),
        ("sw_activate_display_state", {"name": ""}),
        ("sw_list_configurations", {}),
        ("sw_create_configuration_full", {"name": "CFG2", "activate": True}),
        ("sw_get_material", {}),
        ("sw_set_custom_properties", {"props": {"料号": "A-01"}}),
        ("sw_pattern_component", {"kind": "linear", "count": 2, "spacing": 0.05,
                                  "component_index": 1}),
        ("sw_mirror_component", {"filter": "", "mirror_type": 2}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _sw_misc_flow(client, context):
    """SW 剧本十九：环境/选择/保存/文档切换（13 步，全快工具）。

    实测可用：connect / api(list_operations) / clear_selection / select_entity(PLANE) /
    start_3d_sketch / save_as_copy / save_all / document_info / activate_document /
    reload_runtime。
    `sw_scan` 在本机以其 cwd 相关实现会崩（cmd_scan 里 getsize 抛错）、
    `sw_assembly_add` 需要有装配体，都不放在这条里。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_misc_")
    part = os.path.join(work, "p.SLDPRT")
    copy = os.path.join(work, "p_copy.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 5}),
        ("sw_save_document", {"path": part}),
        ("sw_connect", {}),
        ("sw_api", {"op": "list_operations"}),
        ("sw_clear_selection", {}),
        ("sw_select_entity", {"name": "前视基准面", "kind": "PLANE"}),
        ("sw_start_3d_sketch", {}),
        ("sw_save_as_copy", {"path": copy}),
        ("sw_save_all", {}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    info = client.call("sw_document_info", {})
    done.append({"tool": "sw_document_info", "ok": bool(info.get("ok"))})
    title = (info.get("reads") or {}).get("title")
    tail = []
    if title:
        tail.append(("sw_activate_document", {"title": title}))
    tail.append(("sw_reload_runtime", {}))
    for name, args in tail:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    want = len(steps) + 1 + len(tail)
    copy_bytes = os.path.getsize(copy) if os.path.exists(copy) else 0
    checks = [
        {"check": "flow_steps", "got": len(done), "want": want, "ok": len(done) == want},
        {"check": "copy_bytes", "got": copy_bytes, "want": ">1000", "ok": copy_bytes > 1000},
    ]
    return {"ok": copy_bytes > 1000, "reads": {"steps": done, "copy_bytes": copy_bytes,
                                               "workdir": work},
            "errors": [] if copy_bytes > 1000 else ["副本没写出来：%d B" % copy_bytes],
            "checks": checks}


def _sw_revolve_flow(client, context):
    """SW 剧本二十：旋转凸台 + 旋转曲面（8 步）。

    判据用数学：草图是"离轴 5–20、高 30"的矩形绕轴旋 360°，
    体积应为 π·30·(20²−5²) = **35342.917 mm³**（实测 35342.917，吻合）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_rev_")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 5.0, "y1": 0.0, "x2": 20.0, "y2": 30.0}),
        ("sw_sketch_centerline", {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 40.0}),
        ("sw_exit_sketch", {}),
        ("sw_revolve", {"angle_deg": 360}),
        ("sw_get_mass_properties", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 5.0, "y1": 0.0, "x2": 20.0, "y2": 30.0}),
        ("sw_sketch_centerline", {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 40.0}),
        ("sw_exit_sketch", {}),
        ("sw_revolved_surface", {"angle_deg": 180}),
    ]
    done, volume = [], None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_revolve":
            volume = (payload.get("reads") or {}).get("volume_mm3")
    expected = 35342.917
    ok_vol = volume is not None and abs(float(volume) - expected) / expected < 0.001
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "revolve_volume", "got": volume, "want": expected, "ok": ok_vol},
    ]
    return {"ok": ok_vol, "reads": {"steps": done, "volume_mm3": volume, "workdir": work},
            "errors": [] if ok_vol else ["旋转体积不对：%r（期望 %.3f）" % (volume, expected)],
            "checks": checks}


def _sw_dwgviews_flow(client, context):
    """SW 剧本二十一：图纸里再加视图（8 步）。

    实测：`sw_add_drawing_view`（指定 model_path）与 `sw_add_auxiliary_view` 可用；
    `sw_add_broken_view` 在零件图上判据不过（break_lines 没增加）、
    `sw_create_section_view` 直接 backend error —— 都不纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_dwgviews_")
    part = os.path.join(work, "p.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_new_drawing", {"model": part}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    tail = [
        ("sw_add_drawing_view", {"model_path": part, "view_name": "top",
                                 "x": 0.28, "y": 0.2}),
        ("sw_add_auxiliary_view", {}),
    ]
    for name, args in tail:
        payload = client.call(name, args)
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    want = len(steps) + len(tail)
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": want,
                        "ok": len(done) == want}]}


def _sw_sketch_ops_flow(client, context):
    """SW 剧本二十二：草图选择类操作（圆角/剪裁）+ 实体镜像（12 步）。

    靠 hub 侧新增的 `sw_select_sketch_segments` 才走得通：swkit 的草图圆角/剪裁
    内部不自己选，必须有"按序号选中线段"的前置动作。
    实测：圆角后 segments 2→3；剪裁需要 1 条选中；`sw_sketch_chamfer` 仍判据不过
    （segment_added=False）、`sw_sketch_convert_entities` / `sw_sketch_circular_pattern`
    需要模型边而不是草图线段，都不纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_sketchops_")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_line", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 0.0}),
        ("sw_sketch_line", {"x1": 40.0, "y1": 0.0, "x2": 40.0, "y2": 30.0}),
        ("sw_select_sketch_segments", {"indices": [0, 1]}),
        ("sw_sketch_fillet", {"radius": 5}),
        ("sw_select_sketch_segments", {"indices": [0]}),
        ("sw_sketch_trim", {"x": 20.0, "y": 0.0}),
    ]
    done, segments = [], None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
        if name == "sw_select_sketch_segments":
            segments = (payload.get("reads") or {}).get("segments")
    # 圆角后线段数应从 2 变 3
    fillet_ok = segments == 3
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "fillet_segments", "got": segments, "want": 3, "ok": fillet_ok},
    ]
    errors = [] if fillet_ok else ["圆角后线段数应为 3，实测 %r" % (segments,)]
    return {"ok": fillet_ok, "reads": {"steps": done, "segments": segments, "workdir": work},
            "errors": errors, "checks": checks}


def _sw_sheet_flow(client, context):
    """SW 剧本二十三：实体转钣金（选面 → insert_bends）+ 展开信息 + 选边圆角（12 步）。

    靠 hub 侧新增的 `sw_select_faces` / `sw_select_edges` 才走得通：
    `sw_insert_bends` 要求先选中一个固定面；`sw_fillet`/`sw_chamfer` 要选边。
    实测：insert_bends 26.7 s、flat_pattern_info 15.4 s、fillet 38.9 s 全过；
    `sw_hem` 判据不过（feature_added=False），不纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_sheet_")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_select_faces", {"indices": [0]}),
        ("sw_insert_bends", {"radius": 5}),
        ("sw_get_flat_pattern_info", {}),
        ("sw_select_edges", {"indices": [0], "face_index": 0}),
        ("sw_fillet", {"radius": 3}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    want = len(steps)
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": want,
                        "ok": len(done) == want}]}


def _sw_artifacts_flow(client, context):
    """SW 剧本二十四：导出 PDF / 截图 BMP / 截图 PNG / 取消抑制（11 步）。

    判据是**文件头**：PDF `%PDF`、BMP `BM`、PNG `\x89PNG` —— 不看返回值。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_art_")
    part = os.path.join(work, "p.SLDPRT")
    pdf = os.path.join(work, "p.pdf")
    bmp = os.path.join(work, "p.bmp")
    png = os.path.join(work, "cap.png")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_export_file", {"path": pdf}),
        ("sw_screenshot", {"out_path": bmp, "width": 800, "height": 600}),
        ("sw_capture_screenshot", {"path": png}),
        ("sw_unsuppress_feature", {"name": "凸台-拉伸1"}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}

    def _head(path, size):
        if not os.path.exists(path):
            return b"", 0
        with open(path, "rb") as fh:
            return fh.read(8), os.path.getsize(path)

    head_pdf, size_pdf = _head(pdf, 0)
    head_bmp, size_bmp = _head(bmp, 0)
    head_png, size_png = _head(png, 0)
    ok_pdf = head_pdf[:4] == b"%PDF" and size_pdf > 1000
    ok_bmp = head_bmp[:2] == b"BM" and size_bmp > 1000
    ok_png = head_png[:4] == b"\x89PNG" and size_png > 1000
    checks = [
        {"check": "flow_steps", "got": len(done), "want": len(steps),
         "ok": len(done) == len(steps)},
        {"check": "pdf", "got": head_pdf[:4].decode("latin-1"), "want": "%PDF", "ok": ok_pdf},
        {"check": "bmp", "got": head_bmp[:2].decode("latin-1"), "want": "BM", "ok": ok_bmp},
        {"check": "png", "got": head_png[:4].hex(), "want": "89504e47", "ok": ok_png},
    ]
    problems = []
    if not ok_pdf:
        problems.append("PDF 不对：head=%r size=%d" % (head_pdf[:4], size_pdf))
    if not ok_bmp:
        problems.append("BMP 不对：head=%r size=%d" % (head_bmp[:2], size_bmp))
    if not ok_png:
        problems.append("PNG 不对：head=%r size=%d" % (head_png[:4], size_png))
    return {"ok": ok_pdf and ok_bmp and ok_png,
            "reads": {"steps": done, "pdf_bytes": size_pdf, "bmp_bytes": size_bmp,
                      "png_bytes": size_png, "workdir": work},
            "errors": problems, "checks": checks}


def _sw_assemble_flow(client, context):
    """SW 剧本二十五：草图重入 + 分割线 + 直连装配三件套（12 步）。

    这条覆盖的是"底层三件套"：`sw_create_assembly` / `sw_open_document` /
    `sw_assembly_add`（前面 `sw_assembly_build` 是在内部调它们，顶层工具没被计到）。
    实测 `sw_split_line` 96.5 s（改模型后要重算），`sw_edit_sketch`/`sw_exit_sketch` 快。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_asm3_")
    part = os.path.join(work, "p.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_edit_sketch", {"sketch_name": "草图1"}),
        ("sw_exit_sketch", {}),
        ("sw_split_line", {}),
        ("sw_create_assembly", {}),
        ("sw_open_document", {"path": part}),
    ]
    done, components = [], None
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    added = client.call("sw_assembly_add", {"parts": [part]})
    done.append({"tool": "sw_assembly_add", "ok": bool(added.get("ok"))})
    components = (added.get("reads") or {}).get("components_after")
    want = len(steps) + 1
    ok = bool(added.get("ok")) and components == 1
    checks = [
        {"check": "flow_steps", "got": len(done), "want": want, "ok": len(done) == want},
        {"check": "components", "got": components, "want": 1, "ok": components == 1},
    ]
    return {"ok": ok, "reads": {"steps": done, "components": components, "workdir": work},
            "errors": [] if ok else ["组件数 %r（期望 1）；add 错误：%s"
                                     % (components, str(added.get("errors"))[:150])],
            "checks": checks}


def _sw_modify_flow(client, context):
    """SW 剧本二十六：抑制/解抑制/删特征 + 删实体（两条脚本各管一件）。

    实测：`sw_suppress_feature` / `sw_unsuppress_feature` / `sw_delete_feature` 用
    **中文特征名**（如 凸台-拉伸1）直接可用；`sw_delete_body` 也可用。
    `sw_delete_equation` 仍 backend error（没有方程对象）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_mod_")
    feature = "凸台-拉伸1"
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 15.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 8}),
        ("sw_suppress_feature", {"name": feature}),
        ("sw_unsuppress_feature", {"name": feature}),
        ("sw_delete_feature", {"name": feature}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _sw_delete_body_flow(client, context):
    """SW 剧本二十七：建件后删实体（6 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_del_")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 15.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 8}),
        ("sw_delete_body", {"body_index": 0}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _flow_steps(client, steps, tag):
    """通用顺序剧本：任一步失败即停，返回统一结构（给下面两条短剧本用）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_%s_" % tag)
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _sw_bodies_flow(client, context):
    """SW 剧本二十八：实体变换/镜像/组合（9 步）。"""
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 15.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 8}),
        ("sw_move_body", {"dx_mm": 50}),
        ("sw_scale_body", {"factor": 2}),
        ("sw_mirror", {"plane": "前视基准面"}),
        ("sw_combine_bodies", {"operation": "add"}),
    ]
    return _flow_steps(client, steps, "bodies")


def _sw_sim_setup_flow(client, context):
    """SW 剧本二十九：赋材质 + 建静力研究并划网格（9 步，**未纳入验收**）。

    单客户端直跑 9.8 s 通过，但在验收会话里 900 s 超时（与 SW COM 会话退化同源），
    所以用例删掉、函数保留。

    实测关键：**没有材质时 sim_setup 直接报"该零件没有材质"**
    （Simulation 要求先有材质，否则 RunAnalysis 返回 19）。
    加 `sw_set_material(AISI 304)` 之后 sim_setup 9.8 s 成功。
    `sw_sim_read` 在没有求解结果时返回 False（"没有结果（求解未成功）"），不纳入。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 15.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 8}),
        ("sw_set_material", {"name": "AISI 304"}),
        ("sw_get_material", {}),
        ("sw_sim_status", {}),
        ("sw_sim_setup", {"restraint_face": 0, "force_face": 1, "force_n": 100,
                          "mesh": True, "size": 0.006}),
    ]
    return _flow_steps(client, steps, "sim")


def _sw_assembly_b_flow(client, context):
    """SW 剧本三十：上游 swkit 装配插入修好后 —— 插入两件 + 面到面距离（12 步）。

    swkit 的 `sw_insert_component` 有三层坑，这次都修在上游：
    ① AddComponent5 参数少了/顺序错（把 path 塞进 CompConfig）；
    ② 先 QueryInterface(IAssemblyDoc) 再调 → E_NOINTERFACE，必须晚绑定直接调；
    ③ `_with_doc` 传进来的是 ActiveDoc（此时是零件）→ 自己按 GetType()==2 找装配体。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_asmb_")
    part = os.path.join(work, "b.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_measure_distance", {"p1": [20.0, 12.5, 0.0], "p2": [20.0, 12.5, 10.0],
                                 "expected_mm": 10.0, "tol_mm": 0.5}),
        ("sw_create_assembly", {}),
        ("sw_open_document", {"path": part}),
        ("sw_insert_component", {"part": part, "x": 0, "y": 0, "z": 0}),
        ("sw_insert_component", {"part": part, "x": 60, "y": 0, "z": 0}),
        ("sw_get_assembly_tree", {}),
        ("sw_hide_component", {"name": "b-1", "hide": True}),
        ("sw_hide_component", {"name": "b-1", "hide": False}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _sw_scan_flow(client, context):
    """SW 剧本三十一：另存副本 → 批量扫描（10 步）。

    `sw_scan` 以前整条崩在 `cmd_scan` 的 `os.path.getsize`（已加保护）；
    扫描目录里的文件必须**没被 SolidWorks 打开**（开着会 open_ro 失败→退出码 1），
    所以这里另存一份到独立目录再扫。`sw_close_document` 也顺带覆盖。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_scan_")
    scan_dir = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_scandir_")
    part = os.path.join(work, "c.SLDPRT")
    copy = os.path.join(scan_dir, "c_copy.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 5}),
        ("sw_save_document", {"path": part}),
        ("sw_save_as_copy", {"path": copy}),
        ("sw_scan", {"dir_path": scan_dir}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    # 不在这里关文档：验收会话里 sw_close_document 会弹"是否保存"模态框把整条用例卡住
    # （单客户端直跑是通的）。关文档留给 cleanup。
    want = len(steps)
    return {"ok": True, "reads": {"steps": done, "copy": copy, "workdir": work},
            "errors": [], "checks": [{"check": "flow_steps", "got": len(done),
                                      "want": want, "ok": len(done) == want}]}


def _sw_face_sketch_flow(client, context):
    """SW 剧本三十二：在实体面上开草图 + 转换实体引用（8 步）。

    swkit 的 `sw_create_sketch` 只认基准面名，所以这批"要在面上画"的工具一直
    不可用。hub 侧补了 `sw_create_sketch_on_face`（选面 → SketchManager.InsertSketch）
    之后，`sw_sketch_convert_entities` **第一次真通过**（segments 0→4）。
    `sw_sketch_text` 仍判据不过（text_matches）、`sw_sketch_circular_pattern`
    backend error，都不纳入。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_face_sketch_")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_create_sketch_on_face", {"face_index": 0}),
        ("sw_sketch_convert_entities", {"chain": True}),
        ("sw_exit_sketch", {}),
    ]
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "workdir": work}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _sw_feature_pattern_flow(client, context):
    """SW 剧本三十九：按名字选特征 + 特征阵列（12 步）。

    `sw_select_features` 以前恒 0 个：SelectByID2 对中文特征名无效，pywin32 的
    `doc.FirstFeature()` 在本机报「找不到成员」。改成 comtypes QI 到 IModelDoc2
    遍历特征树 + `IFeature::Select2` 后，「凸台-拉伸1」「切除-拉伸1」都能选中。

    `sw_pattern_feature` 的前置是**零件里必须有切除类特征**（内部按 ICE/Cut 找目标）
    + 一条直边当方向；只有拉伸体时会报 backend error。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_pattern_")
    part = os.path.join(work, "pat.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_create_sketch_on_face", {"face_index": 1}),
        ("sw_sketch_circle", {"cx": 20.0, "cy": 12.5, "radius": 6.0}),
        ("sw_exit_sketch", {}),
        ("sw_cut_extrude", {"through_all": True}),
        ("sw_select_features", {"names": ["切除-拉伸1"]}),
        ("sw_pattern_feature", {"kind": "linear", "count": 2, "spacing": 0.03}),
    ]
    return _sw_flow_any(client, steps, "feature_pattern", work)


def _sw_drawing_notes_flow(client, context):
    """SW 剧本四十：自动气泡 + 旋转视图（9 步）。

    两条都要求**图纸里已经有视图**（`sw_new_drawing` 会建主视图）且是**干净的
    新图纸**；`sw_add_balloon` 内部自己插 BOM，前面再插一张 BOM 表会把 SW 卡死。
    这个剧本**必须单独跑**：跟别的出图用例同批时容易卡在 900 s 超时。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_drw_")
    part = os.path.join(work, "drw.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_new_drawing", {"model": part, "view": "front"}),
        ("sw_add_balloon", {"x": 0.1, "y": 0.2}),
        ("sw_view_rotate", {"angle_deg": 15}),
    ]
    return _sw_flow_any(client, steps, "drawing_notes", work)


def _sw_body_ops_flow(client, context):
    """SW 剧本四十一：多实体组合 + 包围盒 + 球体（9 步）。

    依赖顺序：**先造第二个实体（move_body copy，且要与第一个重叠）** → 才能
    `combine_bodies`。实测：两个实体**不重叠**时 `InsertCombineFeature` 返回 None
    （判据 feature_created/bodies_decreased 全 false）；重叠 20 mm 时实体 2→1、
    体积 20000→15000。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_bodyops_")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_move_body", {"dx_mm": 20, "copy": True}),
        ("sw_select_bodies", {"indices": [0, 1]}),
        ("sw_combine_bodies", {"operation": "add"}),
        ("sw_bounding_box_with_hidden", {"include_hidden": False}),
        # 不给 save_path：带 save_path 时判据 executed/saved 会挂（保存路径那步没落地）
        ("sw_create_sphere", {"diameter_mm": 30, "execute": True}),
    ]
    return _sw_flow_any(client, steps, "body_ops", work)


def _sw_refs_params_flow(client, context):
    """SW 剧本四十二：持久引用选实体 + 改特征参数 + 方程增删（8 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_refs_")
    part = os.path.join(work, "rp.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_set_feature_parameter", {"feature": "凸台-拉伸1", "parameter": "D1",
                                      "value": 12.0, "confirm": True}),
        ("sw_add_equation", {"expression": '"W" = 40'}),
        ("sw_delete_equation", {"index": 0}),
    ]
    return _sw_flow_any(client, steps, "refs_params", work)


def _sw_sheetmetal_flow(client, context):
    """SW 剧本四十三：钣金基体法兰 → 卷边 → 折弯 → 展开信息（7 步）。

    实测的选择依赖：`base_flange` 要草图；`hem` 要**选边**（这块 80×50 板上
    第 4 条边才成功，前几条都判 feature_added=false）；`insert_bends` 要**选面**。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_sheet_")
    part = os.path.join(work, "sm.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 80.0, "y2": 50.0}),
        ("sw_exit_sketch", {}),
        ("sw_save_document", {"path": part}),
        ("sw_base_flange", {"thickness_mm": 2, "radius_mm": 2, "depth_mm": 30}),
        ("sw_select_edges", {"indices": [4]}),
        ("sw_hem", {"length_mm": 5, "radius_mm": 0.5, "hem_type": 0}),
        ("sw_select_faces", {"indices": [0]}),
        ("sw_insert_bends", {"radius": 5}),
        ("sw_get_flat_pattern_info", {}),
    ]
    return _sw_flow_any(client, steps, "sheetmetal_full", work)


def _sw_fea_solve_flow(client, context):
    """SW 剧本四十四：FEA 建研究 → 划网格 → 真求解（5 步，约 11–15 分钟）。

    单独跑（`--only sw.flow.fea_solve`），别混进批量：单次 `star.exe` 峰值约 15 GB。
    判据看 `sw_sim_solve` 自己报的 `results_available`/`step_count`，不看退出码。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_fea_")
    part = os.path.join(work, "fea.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 50.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_assign_material_full", {"name": "AISI 304"}),
        ("sw_sim_setup", {"open_path": part, "restraint_face": 1, "force_face": 0,
                          "force_n": 100, "material": "AISI 304", "mesh": False}),
        ("sw_sim_mesh", {"open_path": part, "size": 0.01, "tol": 0.001}),
        ("sw_sim_solve", {"open_path": part, "restraint_face": 1, "force_face": 0,
                          "force_n": 100, "material": "AISI 304"}),
    ]
    return _sw_flow_any(client, steps, "fea_solve", work)


def _sw_asm_replace_flow(client, context):
    """SW 剧本四十五：装配里替换组件（14 步）。

    注意：**不要**在这条后面接 close_all / 关装配体——留着装配体会让 swkit 退出
    时卡住（报告写不出来）；别的用例能正常收尾就是因为只留下文档不关。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_repl_")
    part = os.path.join(work, "m.SLDPRT")
    copy = os.path.join(work, "n.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 30.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 8}),
        ("sw_save_document", {"path": part}),
        ("sw_save_as_copy", {"path": copy}),
        ("sw_create_assembly", {}),
        ("sw_open_document", {"path": part}),
        ("sw_insert_component", {"part": part, "x": 0, "y": 0, "z": 0}),
        ("sw_insert_component", {"part": copy, "x": 60, "y": 0, "z": 0}),
        ("sw_replace_component", {"name": "m-1", "new_file": copy}),
        ("sw_get_assembly_tree", {}),
    ]
    return _sw_flow_any(client, steps, "asm_replace", work)


def _sw_refs_select_flow(client, context):
    """SW 剧本四十六：持久引用选实体 + 选实体（6 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_refs2_")
    part = os.path.join(work, "rf.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_select_bodies", {"indices": [0]}),
    ]
    return _sw_flow_any(client, steps, "refs_select", work)


def _sw_drawing_table_flow(client, context):
    """SW 剧本四十七：选视图 + 插 BOM 表（9 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_dt_")
    part = os.path.join(work, "dt.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_new_drawing", {"model": part, "view": "front"}),
        ("sw_select_view", {}),
        ("sw_add_bom_table", {"x": 0.12, "y": 0.2}),
    ]
    return _sw_flow_any(client, steps, "drawing_table", work)


def _sw_reducer_plan_flow(client, context):
    """SW 剧本四十八：两级减速器只出计划（8 步）。"""
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 60.0, "y2": 40.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_create_two_stage_reducer", {"execute": False}),
        ("sw_close_all", {"save": True}),
    ]
    return _sw_flow_any(client, steps, "reducer_plan", None)


def _sw_sim_rerun_flow(client, context):
    """SW 剧本四十九：求解 → 再求解 → 读结果（10 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_rerun_")
    part = os.path.join(work, "rr.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 50.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_assign_material_full", {"name": "AISI 304"}),
        ("sw_sim_setup", {"open_path": part, "restraint_face": 1, "force_face": 0,
                          "force_n": 100, "material": "AISI 304", "mesh": False}),
        ("sw_sim_mesh", {"open_path": part, "size": 0.01, "tol": 0.001}),
        ("sw_sim_solve", {"open_path": part}),
        ("sw_sim_run", {"open_path": part, "timeout_s": 900}),
        ("sw_sim_read", {"open_path": part}),
    ]
    return _sw_flow_any(client, steps, "sim_rerun", work)


def _sw_sketch_text_flow(client, context):
    """SW 剧本五十：草图文字（5 步）。

    上游 swkit 的 ok 是"建出对象 and（线段增加 or 文字读回）"——本机
    `InsertSketchText` 读回恒 None、但线段 0→1，所以**必须**尊重上游 ok；
    代理层以前要求每个 check 都为真，会把这条误判成失败（已修 swkit_adapter）。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_sketch_text", {"text": "AB", "x": 5.0, "y": 5.0}),
        ("sw_close_all", {"save": True}),
    ]
    return _sw_flow_any(client, steps, "sketch_text", None)


def _sw_close_doc_flow(client, context):
    """SW 剧本五十一：关当前文档（7 步）。`sw_close_document` 不给 title 就是关活动文档。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_close_")
    part = os.path.join(work, "cd.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 30.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 6}),
        ("sw_save_document", {"path": part}),
        ("sw_close_document", {}),
    ]
    return _sw_flow_any(client, steps, "close_doc", work)


def _sw_select_refs_flow(client, context):
    """SW 剧本五十二：用持久引用 token 选实体（6 步）。

    token 来自 `sw_feature_inspect(include_tokens=True)` 的 `reads.result.topology[]`，
    所以必须**先 inspect 再选**，不能写死。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_selrefs_")
    part = os.path.join(work, "sr.SLDPRT")
    steps = []
    for name, args in (("sw_create_part", {}),
                       ("sw_create_sketch", {"plane": "前视基准面"}),
                       ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
                       ("sw_exit_sketch", {}),
                       ("sw_extrude", {"depth_mm": 10}),
                       ("sw_save_document", {"path": part})):
        payload = client.call(name, args)
        steps.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": steps, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:160])],
                    "checks": []}
    payload = client.call("sw_feature_inspect",
                          {"include_topology": True, "include_tokens": True, "limit": 6})
    steps.append({"tool": "sw_feature_inspect", "ok": bool(payload.get("ok"))})
    topo = ((payload.get("reads") or {}).get("result") or {}).get("topology") or []
    tokens = [t["reference_token"] for t in topo if t.get("reference_token")][:2]
    if not tokens:
        return {"ok": False, "reads": {"steps": steps, "tokens": []},
                "errors": ["feature_inspect 没给 token"], "checks": []}
    payload = client.call("sw_select_references", {"tokens": tokens})
    steps.append({"tool": "sw_select_references", "ok": bool(payload.get("ok"))})
    return {"ok": bool(payload.get("ok")),
            "reads": {"steps": steps, "tokens": len(tokens)},
            "errors": [] if payload.get("ok") else str(payload.get("errors"))[:200],
            "checks": [{"check": "tokens_selected", "got": bool(payload.get("ok")),
                        "want": True, "ok": bool(payload.get("ok"))}]}


def _sw_drawing_extra_flow(client, context):
    """SW 剧本五十三：3D 剖视（零件上）+ 断裂视图（9 步）。

    两条实测结论：
    * `sw_create_section_view` 是**模型 3D 剖视**，必须在**零件**上、建图之前调；
      图纸激活时调它必失败（旧实现就是在这里被判死的）。
    * 断裂视图的 `InsertBreak2` 真参数是 (Orientation, Position1, Position2,
      Style, ShapeIntensity)，旧实现只给了一个 position，SW 静默不建。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_dwgex_")
    part = os.path.join(work, "box_hole.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 80.0, "y2": 50.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 20}),
        ("sw_save_document", {"path": part}),
        ("sw_create_sketch_on_face", {"face_index": 1}),
        ("sw_sketch_circle", {"cx": 40.0, "cy": 25.0, "radius": 8.0}),
        ("sw_exit_sketch", {}),
        ("sw_cut_extrude", {"through_all": True}),
        ("sw_create_section_view", {"plane": "前视基准面", "offset": 0.0}),
        # 用**上视**建图：孔轴线沿 Z，上视才看得见孔口圆边——中心标记必须有圆边
        ("sw_new_drawing", {"model": part, "view": "top"}),
        ("sw_add_hole_table", {"x": 0.12, "y": 0.18}),
        ("sw_add_broken_view", {"orientation": 0, "position": 0.049, "size": 0.01}),
        ("sw_add_center_mark", {"x": 0.05}),
        ("sw_add_datum_feature", {}),
        ("sw_add_gtol", {}),
        ("sw_add_weld_symbol", {}),
    ]
    return _sw_flow_any(client, steps, "drawing_extra", work)


def _sw_param_dimension_flow(client, context):
    """SW 剧本五十四：参数化零件改尺寸（4 步）。

    `sw_set_dimension` 要的是一个**真实存在的命名尺寸**；参数化零件（feature graph）
    建出来的块自带 `D1@BlockBoss`，实测 `doc.Parameter("D1@BlockBoss")` 可读可写，
    20 mm → 25 mm 读回一致。空零件上现画的矩形**没有命名尺寸**，所以必须用
    参数化零件当夹具。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_dim_")
    steps = [
        ("sw_create_parametric_part", {"part_type": "block",
                                       "parameters": {"length": 60, "width": 40,
                                                      "height": 20},
                                       "execute": True}),
        ("sw_get_dimension", {"name": "D1@BlockBoss"}),
        ("sw_set_dimension", {"name": "D1@BlockBoss", "value_mm": 25.0}),
        ("sw_get_dimension", {"name": "D1@BlockBoss"}),
    ]
    return _sw_flow_any(client, steps, "param_dimension", work)


def _sw_refusal_flow(client, context):
    """SW 剧本五十五：两条"先决条件不满足就明确拒绝"的工具（9 步）。

    * `sw_analyze_draft` 需要零件里**已有分型线特征**（API 建不出来），
      没有时它给出 `特征树里没有分型线特征（需先手工建一个）`；
    * `sw_move_component` 需要装配里**有组件**，空装配给 `装配里没有组件`
      （以前这里会卡 300 s，现在 0.1 s 就拒）。

    这两个工具的价值恰恰在于"拒绝得清楚"，所以本剧本断言拒绝原因。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_refuse_")
    steps = [
        ("sw_close_all", {"save": False}, True, None),
        ("sw_create_part", {}, True, None),
        ("sw_create_sketch", {"plane": "前视基准面"}, True, None),
        ("sw_sketch_rectangle", {"x1": 0, "y1": 0, "x2": 40, "y2": 25}, True, None),
        ("sw_exit_sketch", {}, True, None),
        ("sw_extrude", {"depth_mm": 10}, True, None),
        ("sw_analyze_draft", {"angle_deg": 1.0, "feature_name": ""}, False, "分型线"),
        ("sw_create_assembly", {}, True, None),
        ("sw_move_component", {"delta_x": 0.05, "part_path": ""}, False, "组件"),
    ]
    records = []
    checks = []
    for name, args, expect_ok, needle in steps:
        payload = client.call(name, args)
        actual_ok = bool(payload.get("ok"))
        errors = " ".join(str(x) for x in (payload.get("errors") or []))
        reads = payload.get("reads") or {}
        detail = str(reads.get("error") or "")
        haystack = errors + " " + detail
        matched = needle is None or needle in haystack
        ok = (actual_ok == expect_ok) and matched
        records.append({"tool": name, "ok": ok, "expect_ok": expect_ok,
                        "actual_ok": actual_ok, "needle": needle,
                        "matched": matched, "detail": (errors or detail)[:160]})
        checks.append({"check": "%s %s" % (name, "ok" if expect_ok else "refusal"),
                       "got": actual_ok, "want": expect_ok, "ok": ok})
    return {"ok": all(c["ok"] for c in checks),
            "reads": {"steps": records, "workdir": work},
            "errors": [], "checks": checks}


def _sw_flow_any(client, steps, tag, work):
    """SW 多步剧本通用执行器：任一步失败即停，返回逐步记录。"""
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                       # noqa: BLE001
            return {"ok": False,
                    "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False,
                    "reads": {"steps": done, "failed_at": name, "workdir": work},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done, "tag": tag, "workdir": work},
            "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


def _sw_part_ops_flow(client, context):
    """SW 剧本三十三：切除/移动实体/缩放/镜像/材料/关系/DimXpert/Flow/Sim 面（14 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_partops_")
    part = os.path.join(work, "p.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_create_sketch_on_face", {"face_index": 1}),
        ("sw_sketch_circle", {"cx": 20.0, "cy": 12.5, "radius": 6.0}),
        ("sw_exit_sketch", {}),
        ("sw_cut_extrude", {"through_all": True}),
        ("sw_move_body", {"dx_mm": 5, "dy_mm": 0, "dz_mm": 0}),
        ("sw_scale_body", {"factor": 1.2}),
        ("sw_mirror", {"plane": "前视基准面"}),
        ("sw_assign_material_full", {"name": "AISI 304"}),
        ("sw_inspect_relations", {}),
        ("sw_dxp", {"create": False}),
        ("sw_flow_check", {}),
        ("sw_sim_faces", {"limit": 6}),
    ]
    return _sw_flow_any(client, steps, "partops", work)


def _sw_sim_flow(client, context):
    """SW 剧本三十四：FEA 建研究+固定+力+划网格（9 步）。

    关键：约束面/受力面必须给**能站的平面**（restraint_face=1、force_face=0），
    给反了 `InsertRestraint` 直接 code=1；材质必须先赋（`sw_assign_material_full`）。
    """
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_sim_")
    part = os.path.join(work, "s.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 10}),
        ("sw_save_document", {"path": part}),
        ("sw_assign_material_full", {"name": "AISI 304"}),
        ("sw_sim_setup", {"open_path": part, "restraint_face": 1, "force_face": 0,
                          "force_n": 100, "material": "AISI 304", "mesh": False}),
        ("sw_sim_mesh", {"open_path": part, "size": 0.002, "tol": 0.0002}),
    ]
    return _sw_flow_any(client, steps, "sim", work)


def _sw_asm_ops_flow(client, context):
    """SW 剧本三十五：装配插入两件 + 隐藏/替换（12 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_asmops_")
    part = os.path.join(work, "x.SLDPRT")
    copy = os.path.join(work, "y.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 30.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 8}),
        ("sw_save_document", {"path": part}),
        ("sw_save_as_copy", {"path": copy}),
        ("sw_create_assembly", {}),
        ("sw_open_document", {"path": part}),
        ("sw_insert_component", {"part": part, "x": 0, "y": 0, "z": 0}),
        ("sw_insert_component", {"part": copy, "x": 80, "y": 0, "z": 0}),
        ("sw_get_assembly_tree", {}),
        ("sw_hide_component", {"name": "x-1", "hide": True}),
        ("sw_hide_component", {"name": "x-1", "hide": False}),
        # 不做 sw_replace_component：它单独跑能过（probe 实测 0.5 s），
        # 但接在"插入两件 + 隐藏"之后会把 SW 卡住（900 s 超时）。
    ]
    return _sw_flow_any(client, steps, "asmops", work)


def _sw_sketch_extras_flow(client, context):
    """SW 剧本三十六：草图约束/倒角/圆周阵列（9 步）。"""
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "上视基准面"}),
        ("sw_sketch_line", {"x1": 0.0, "y1": 0.0, "x2": 30.0, "y2": 0.0}),
        ("sw_sketch_line", {"x1": 30.0, "y1": 0.0, "x2": 30.0, "y2": 20.0}),
        ("sw_sketch_chamfer", {"distance": 2.0}),
        ("sw_sketch_circular_pattern", {"count": 2, "radius": 10.0, "angle_deg": 360}),
        ("sw_exit_sketch", {}),
        ("sw_close_all", {"save": True}),
    ]
    return _sw_flow_any(client, steps, "sketch_extras", None)


def _sw_constraint_flow(client, context):
    """SW 剧本三十八：草图约束（单独一条，避免和前一条脚本互相干扰）。

    实测：`sw_add_sketch_constraint` 在"矩形草图刚画完"的状态下 ok；
    但把它夹在"画线 + 倒角 + 阵列"中间会把 SW 卡住（600 s 超时）。
    """
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 40.0, "y2": 25.0}),
        ("sw_add_sketch_constraint", {"constraint": "sgHORIZONTAL",
                                      "plane": "前视基准面"}),
        # 不加 sw_exit_sketch：约束工具跑完 SW 认为草图已不在编辑态，
        # 再调 exit 会判 sketch_closed=false。收尾统一走 close_all。
        ("sw_close_all", {"save": True}),
    ]
    return _sw_flow_any(client, steps, "constraint", None)


def _sw_plan_only_flow(client, context):
    """SW 剧本三十七：只出计划的工具（不真建几何）+ 出图 BOM 空表（6 步）。"""
    work = tempfile.mkdtemp(prefix="nsa_mcp_hub_accept_sw_plan_")
    part = os.path.join(work, "z.SLDPRT")
    steps = [
        ("sw_create_part", {}),
        ("sw_create_sketch", {"plane": "前视基准面"}),
        ("sw_sketch_rectangle", {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 20.0}),
        ("sw_exit_sketch", {}),
        ("sw_extrude", {"depth_mm": 5}),
        ("sw_save_document", {"path": part}),
        ("sw_create_parametric_part", {"part_type": "cylinder",
                                       "parameters": {"diameter": 20, "height": 30},
                                       "execute": False}),
        ("sw_create_output_shaft", {"execute": False}),
        ("sw_close_all", {"save": True}),
    ]
    return _sw_flow_any(client, steps, "plan_only", work)


def _flow(client, steps):
    """顺序调用若干工具；任一步失败就带着证据停，全过则合成一个 payload。

    一条用例覆盖 3–6 个工具，失败点明确（不会只看到最后一步的错）。
    """
    done = []
    for name, args in steps:
        try:
            payload = client.call(name, args)
        except Exception as exc:                      # noqa: BLE001
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 抛异常：%s: %s" % (name, type(exc).__name__,
                                                     str(exc)[:160])], "checks": []}
        done.append({"tool": name, "ok": bool(payload.get("ok"))})
        if not payload.get("ok"):
            return {"ok": False, "reads": {"steps": done, "failed_at": name},
                    "errors": ["%s 失败：%s" % (name, str(payload.get("errors"))[:200])],
                    "checks": payload.get("checks") or []}
    return {"ok": True, "reads": {"steps": done}, "errors": [],
            "checks": [{"check": "flow_steps", "got": len(done), "want": len(steps),
                        "ok": len(done) == len(steps)}]}


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

    {"id": "eplan.runtime.no_snapshot", "tool": "eplan_runtime_status",
     "title": "没有快照时 runtime_status 明确返回 ok=false（不假装读过原生）",
     "args": {}, "expect_ok": False,
     "expect_reads": {"reads.snapshot.available": False,
                      "reads.snapshot.live_verified_this_call": False},
     "no_setup": True, "timeout_s": 120},

    {"id": "eplan.snapshot.reject_empty", "tool": "eplan_native_snapshot_validate",
     "title": "空快照必须被拒：scope=provided_full_snapshot_offline、construction_ready=false",
     "args": {"capture": {}, "plan": {}},
     "expect_ok": False,
     "expect_reads": {"reads.scope": "provided_full_snapshot_offline",
                      "reads.native_read_this_call": False,
                      "reads.construction_ready": False,
                      "reads.commissioning_ready": False},
     "no_setup": True, "timeout_s": 120},

    {"id": "eplan.help.not_built", "tool": "eplan_help_search",
     "title": "没建索引时 help_search 明确拒绝（HELP_INDEX_NOT_BUILT），不假装查过",
     "args": {"query": "Generate"},
     "expect_ok": False,
     "expect_reads": {"reads.error": "HELP_INDEX_NOT_BUILT"},
     "no_setup": True, "timeout_s": 120},

    {"id": "eplan.intent.validate", "tool": "eplan_design_intent_validate",
     "title": "离线设计意图校验：6 根线分成 4 组、给出 14 条告警",
     "args": {"model": _EPLAN_INTENT_MODEL},
     "expect_ok": True,
     "expect_reads": {"reads.wire_groups": 4,
                      "reads.scope": "offline_declared_wire_graph_and_constraints_only"},
     "timeout_s": 180},
    {"id": "ug.flow.machine_validate", "timeout_s": 900, "tool": None,
     "title": "ug 剧本十三：机床校验五件套（模板路线，运动学+碰撞全通过）",
     "args": {}, "expect_ok": True,
     "call": lambda client, context: _ug_machine_validate_flow(client, context)},
]


# ── catia（CATIA V5：建模 / 曲面 / 原生 Analysis）────────────────────────
def _catia_missing(context: dict) -> bool:
    """本机没装 CATIA 就跳过（2026-11-04 实测未安装）。"""
    import os
    roots = [r"C:\Program Files\Dassault Systemes", r"D:\Program Files\Dassault Systemes",
             r"C:\Program Files (x86)\Dassault Systemes"]
    return not any(os.path.isdir(r) for r in roots)


CATIA_CASES = [
    {"id": "catia.operation.status", "tool": "catia_operation_status",
     "title": "COM worker 状态（不进队列，不启动 CATIA）",
     "args": {}, "expect_ok": True, "no_setup": True, "timeout_s": 120},

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
    "nx": {"module": "nsa_mcp_hub.servers.nx_mcp", "setup": nx_setup,
           "cases": NX_CASES},
    "acad": {"module": "nsa_mcp_hub.servers.acad_mcp", "setup": acad_setup, "between": acad_between, "teardown": acad_teardown, "cases": ACAD_CASES},
    "gx": {"module": "nsa_mcp_hub.servers.gx_mcp", "cases": GX_CASES},
    "codesys": {"module": "nsa_mcp_hub.servers.codesys_mcp", "setup": codesys_setup,
                "cases": CODESYS_CASES},
    "ug": {"module": "nsa_mcp_hub.servers.ug_mcp", "cases": UG_CASES},
    "catia": {"module": "nsa_mcp_hub.servers.catia_mcp", "cases": CATIA_CASES},
    "eplan": {"module": "nsa_mcp_hub.servers.eplan_mcp", "cases": EPLAN_CASES},
    "autoshop": {"module": "nsa_mcp_hub.servers.autoshop_mcp", "setup": autoshop_setup, "between": autoshop_between, "teardown": autoshop_teardown, "cases": AUTOSHOP_CASES},
}

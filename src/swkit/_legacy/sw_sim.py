# -*- coding: utf-8 -*-
"""sw_sim.py — SolidWorks Simulation (FEA) 自动化工具

设计前提（全部实测，2026-10-19）：
  * 加载项顺序：有关档时 LoadAddIn 返回 -1。必须先 CloseAllDocuments（--reset），
    再 LoadAddIn(Simulation\\cosworks.dll)，然后开文档；GetAddInObject 要轮询到非空。
  * 材质必须在建研究之前设定。研究创建时材质为空 → RunAnalysis 恒返回 19，
    事后补设材质也救不回来（UpdateAllComponents 无效），只能新建研究。
  * 力的数值必须走编辑会话：ForceBeginEdit → 设值 → ForceEndEdit，否则读回恒为 1.0。
  * AddRestraint / AddForce 的 Type：约束=0、普通力=1（0/2/3/4/5 全部失败）。
  * 实体参数传 Python 元组，comtypes 自动转 SAFEARRAY；元素必须由 comtypes 读出的
    GetSelectedObject6 拿到，pywin32 的 dispatch 会报 "does not define a Count method"。
  * 选面用 SelectByID2，Callout 必须传 VARIANT(VT_DISPATCH, None)，否则类型不匹配。
  * CreateMesh(0, 0.01, 0.0005) 会让 cwbcbfmesh 涨到 16 GB（容差小 4 倍 → 单元数 4³=64 倍）。
    安全档：type=1、size>=0.02 m、tol>=0.002 m。本工具默认拒绝更激进的参数。
  * 结果：GetMinMaxDisplacement(0, 0, None, 0)、GetMinMaxStress(0, 0, 0, None, 0)。
  * 求解耗时约 13 分钟（40 mm 级零件），star.exe 峰值约 15 GB。

用法：
  python sw_sim.py status                     # 诊断：文档/材质/加载项/研究数
  python sw_sim.py faces --limit 12           # 列出面（供选约束面/受力面）
  python sw_sim.py list                       # 列出研究及其结果状态
  python sw_sim.py setup --restraint-face 0 --force-face 1 --force 100
  python sw_sim.py mesh                       # 划网格（含参数校验）
  python sw_sim.py run                        # 求解
  python sw_sim.py read --out fea.json        # 读结果
  python sw_sim.py solve --restraint-face 0 --force-face 1 --force 100 \
                         --out fea.json        # 一条龙：建研究→网格→求解→读结果
  python sw_sim.py status --open "D:\\x\\part.SLDPRT" --reset
"""
import argparse
import json
import os
import sys
import threading
import time

VENDOR = os.environ.get("SWKIT_VENDOR") or ""
if os.path.isdir(VENDOR) and VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)

SW_DIR = r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
SIM_DLL = os.path.join(SW_DIR, r"Simulation\cosworks.dll")

# 网格安全档（实测：低于此值内存会爆炸）
SAFE_MIN_SIZE = 0.02      # 全局尺寸下限，米
SAFE_MIN_TOL = 0.002      # 容差下限，米
SAFE_MESH_TYPE = 1        # 0/2 均未验证过安全性


# ---------------------------------------------------------------- 基础
def _pyw():
    import win32com.client.dynamic as d
    return d


def _none_disp():
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def _tlbs():
    from comtypes.client import GetModule, CreateObject
    sw = GetModule(os.path.join(SW_DIR, "sldworks.tlb"))
    cw = GetModule(os.path.join(SW_DIR, "Simulation", "cosworks.tlb"))
    return sw, cw, CreateObject


def _addin_ready(app_w, progid="SldWorks.Simulation"):
    try:
        return app_w.GetAddInObject(progid) is not None
    except Exception:
        return False


def ensure_addin(app_w, reset=False, tries=12, delay=2.0):
    """保证 Simulation 加载项可用。reset=True 时允许先关闭全部文档再加载。"""
    if _addin_ready(app_w):
        return True
    for i in range(tries):
        try:
            app_w.LoadAddIn(SIM_DLL)
        except Exception:
            pass
        if _addin_ready(app_w):
            return True
        if i == 1 and reset:
            try:
                app_w.CloseAllDocuments(True)
                print("  [reset] 已关闭全部文档")
            except Exception as e:
                print("  [reset] 关闭失败：%s" % str(e)[:80])
        time.sleep(delay)
    return _addin_ready(app_w)


def _open(args):
    """返回 (doc_w, md, part, cw, app)。"""
    d = _pyw()
    app_w = d.Dispatch("SldWorks.Application")
    if not ensure_addin(app_w, reset=getattr(args, "reset", False)):
        raise SystemExit("  Simulation 加载项不可用。\n"
                         "  → 若 SW 里已打开文档，加 --reset 允许先关闭全部文档再加载")
    if getattr(args, "open", None):
        import pythoncom
        import win32com.client
        err = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warn = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        typ = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}.get(
            os.path.splitext(args.open)[1].lower(), 1)
        doc_w = app_w.OpenDoc6(os.path.abspath(args.open), typ, 1, "", err, warn)
        if doc_w is None:
            raise SystemExit("  打不开：%s (err=%s)" % (args.open, err.value))
    else:
        doc_w = app_w.ActiveDoc
        if doc_w is None:
            raise SystemExit("  当前没有打开的文档")
    doc_w = d.Dispatch(doc_w)

    sw, cw, CreateObject = _tlbs()
    app = CreateObject(sw.SldWorks)
    md = app.ActiveDoc.QueryInterface(sw.IModelDoc2)
    part = md.QueryInterface(sw.IPartDoc) if hasattr(sw, "IPartDoc") else None
    return doc_w, md, part, cw, app


def _study_mgr(app, cw):
    o = app.GetAddInObject("SldWorks.Simulation").CosmosWorks
    wmd = o.ActiveDoc.QueryInterface(cw.ICWModelDoc)
    return wmd.StudyManager


def _study(sm, name=None):
    n = int(sm.StudyCount)
    if n <= 0:
        raise SystemExit("  该文档没有仿真研究")
    if name:
        for i in range(n):
            st = sm.GetStudy(i)
            if st is not None and str(st.Name) == name:
                return st
        raise SystemExit("  找不到研究：%s" % name)
    return sm.GetStudy(n - 1)


def _faces(doc_w):
    bodies = list(doc_w.GetBodies2(0, True) or [])
    out = []
    for b in bodies:
        out.extend(list(b.GetFaces() or []))
    return out


def _pick(md, doc_w, face):
    """选中一个面，返回 comtypes 的 IDispatch（可直接放进元组）。"""
    box = face.GetBox
    cx = (box[0] + box[3]) / 2.0
    cy = (box[1] + box[4]) / 2.0
    cz = (box[2] + box[5]) / 2.0
    doc_w.ClearSelection2(True)
    doc_w.Extension.SelectByID2("", "FACE", cx, cy, cz, False, 0, _none_disp(), 0)
    return md.SelectionManager.GetSelectedObject6(1, -1)


def _material(part):
    try:
        return str(part.MaterialIdName or "")
    except Exception:
        return ""


def _require_material(part, name):
    cur = _material(part)
    if cur:
        return cur
    if not name:
        raise SystemExit("  该零件没有材质。\n"
                         "  → Simulation 要求先有材质再建研究（否则 RunAnalysis 返回 19）。\n"
                         "  → 用 --material \"AISI 304\" 指定，或先在 SW 界面里赋值。")
    for lib in ("SolidWorks Materials.sldmat", ""):
        try:
            part.SetMaterialPropertyName2("", lib, name)
            if _material(part):
                return _material(part)
        except Exception:
            continue
    raise SystemExit("  材质设置失败：%s" % name)


# ---------------------------------------------------------------- 内存看门狗
def _free_gb():
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullAvailPhys / (1024.0 ** 3)
    except Exception:
        return -1.0


def _start_guard(threshold_gb, which=("cwbcbfmesh", "star")):
    """后台线程：可用物理内存低于阈值时杀掉求解/网格进程。返回 stop event。"""
    if not threshold_gb or threshold_gb <= 0:
        return None
    stop = threading.Event()
    killed = []

    def loop():
        import subprocess
        while not stop.is_set():
            free = _free_gb()
            if 0 <= free < threshold_gb:
                for exe in which:
                    try:
                        subprocess.run(["taskkill", "/IM", exe + ".exe", "/F"],
                                       capture_output=True, timeout=10)
                    except Exception:
                        pass
                killed.append(free)
                print("\n  [内存看门狗] 可用仅 %.2f GB，已终止 %s" % (free, "/".join(which)))
                return
            time.sleep(2.0)

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    return stop


# ---------------------------------------------------------------- 命令
def cmd_status(args):
    doc_w, md, part, cw, app = _open(args)
    print("  文档       =", md.GetTitle())
    print("  材质       =", repr(_material(part)) if part is not None else "(非零件)")
    print("  Simulation = 已就绪")
    try:
        sm = _study_mgr(app, cw)
        n = int(sm.StudyCount)
        act = sm.ActiveStudy
        print("  研究数     = %d（活动 index=%s）" % (n, act))
        for i in range(n):
            st = sm.GetStudy(i)
            if st is None:
                continue
            res = st.Results
            print("    [%d] %-22s type=%s results=%s"
                  % (i, st.Name, st.AnalysisType, "有" if res is not None else "无"))
    except Exception as e:
        print("  研究信息   = 读取失败：%s" % str(e)[:80])
    print("  可用内存   = %.1f GB" % _free_gb())
    return 0


def cmd_faces(args):
    doc_w, md, part, cw, app = _open(args)
    faces = _faces(doc_w)
    print("  文档 =", md.GetTitle(), "| 面数 =", len(faces))
    print("  idx  中心(x,y,z) mm                    尺寸 mm")
    for i, f in enumerate(faces[:args.limit]):
        b = f.GetBox
        cx, cy, cz = ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)
        dx, dy, dz = (abs(b[3] - b[0]), abs(b[4] - b[1]), abs(b[5] - b[2]))
        print("  %-4d (%9.2f,%9.2f,%9.2f)   %7.2f x %7.2f x %7.2f"
              % (i, cx * 1000, cy * 1000, cz * 1000, dx * 1000, dy * 1000, dz * 1000))
    return 0


def cmd_list(args):
    doc_w, md, part, cw, app = _open(args)
    sm = _study_mgr(app, cw)
    n = int(sm.StudyCount)
    print("  文档 = %s | 研究数 = %d" % (md.GetTitle(), n))
    for i in range(n):
        st = sm.GetStudy(i)
        if st is None:
            continue
        try:
            steps = st.Results.QueryInterface(cw.ICWResults).GetMaximumAvailableSteps()
        except Exception:
            steps = "-"
        print("  [%d] %-24s type=%-2s results=%s steps=%s"
              % (i, st.Name, st.AnalysisType,
                 "有" if st.Results is not None else "无", steps))
    return 0


def _do_setup(args, app, md, part, doc_w, cw, sm):
    mat = _require_material(part, args.material)
    print("  材质 =", mat)
    faces = _faces(doc_w)
    if args.restraint_face >= len(faces) or args.force_face >= len(faces):
        raise SystemExit("  面索引越界（共 %d 个面，用 faces 命令查看）" % len(faces))
    sel_r = _pick(md, doc_w, faces[args.restraint_face])
    sel_f = _pick(md, doc_w, faces[args.force_face])

    name = args.study or ("FEA_%d" % int(time.time() % 100000))
    code, study = sm.CreateNewStudy2(name, 0)
    print("  研究 = %s（code=%s）" % (name, code))
    if not study:
        raise SystemExit("  建研究失败，code=%s" % code)
    sm.ActiveStudy = int(sm.StudyCount) - 1

    lrm = study.LoadsAndRestraintsManager
    rc = lrm.AddRestraint(0, (sel_r,), None)
    print("  约束 = code %s" % rc[0])
    if rc[0] != 0:
        raise SystemExit("  约束失败，code=%s" % rc[0])
    fc, fo = lrm.AddForce(1, (sel_f,), None)
    print("  力   = code %s" % fc)
    if fo is None:
        raise SystemExit("  力失败，code=%s（Type 必须为 1）" % fc)
    fo.ForceBeginEdit()
    fo.NormalForceOrTorqueValue = float(args.force_value)
    fo.ForceEndEdit()
    print("  力值 = %s N" % fo.NormalForceOrTorqueValue)
    return study, name


def validate_mesh_params(args):
    """在接触 SW 之前先拦住危险参数。"""
    bad = []
    if args.size < SAFE_MIN_SIZE:
        bad.append("size=%s < %s" % (args.size, SAFE_MIN_SIZE))
    if args.tol < SAFE_MIN_TOL:
        bad.append("tol=%s < %s" % (args.tol, SAFE_MIN_TOL))
    if args.mesh_type != SAFE_MESH_TYPE:
        bad.append("mesh_type=%s != %s" % (args.mesh_type, SAFE_MESH_TYPE))
    if bad and not args.unsafe_mesh:
        raise SystemExit("  网格参数超出安全档：%s\n"
                         "  实测容差 0.0005 会让网格进程涨到 16 GB。\n"
                         "  → 确需尝试请加 --unsafe-mesh，并配合 --mem-guard 1.5"
                         % "；".join(bad))


def _do_mesh(args, study):
    size, tol, mtype = args.size, args.tol, args.mesh_type
    bad = []
    if size < SAFE_MIN_SIZE:
        bad.append("size=%s < %s" % (size, SAFE_MIN_SIZE))
    if tol < SAFE_MIN_TOL:
        bad.append("tol=%s < %s" % (tol, SAFE_MIN_TOL))
    if mtype != SAFE_MESH_TYPE:
        bad.append("mesh_type=%s != %s" % (mtype, SAFE_MESH_TYPE))
    if bad and not args.unsafe_mesh:
        raise SystemExit("  网格参数超出安全档：%s\n"
                         "  实测容差 0.0005 会让网格进程涨到 16 GB。\n"
                         "  → 确需尝试请加 --unsafe-mesh，并配合 --mem-guard 1.5"
                         % "；".join(bad))
    print("  网格参数 = type=%d size=%s tol=%s%s"
          % (mtype, size, tol, "（--force 已越过安全档）" if bad else ""))
    t0 = time.time()
    rc = study.CreateMesh(mtype, size, tol)
    print("  CreateMesh = %s  %.1fs" % (rc, time.time() - t0))
    if rc != 0:
        raise SystemExit("  网格失败，code=%s" % rc)
    return rc


def _do_run(study):
    t0 = time.time()
    rc = study.RunAnalysis()
    print("  RunAnalysis = %s  %.1fs" % (rc, time.time() - t0))
    if rc != 0:
        hint = ""
        if rc == 19:
            hint = "\n  → code 19 通常是『材质为空』：研究必须在材质设定之后创建"
        raise SystemExit("  求解失败，code=%s%s" % (rc, hint))
    return rc


def _read_results(study, cw):
    res = study.Results
    if res is None:
        raise SystemExit("  没有结果（求解未成功）")
    r2 = res.QueryInterface(cw.ICWResults)
    steps = r2.GetMaximumAvailableSteps()
    disp = r2.GetMinMaxDisplacement(0, 0, None, 0)

    stress, stress_err = None, None
    for attempt in range(3):
        try:
            stress = r2.GetMinMaxStress(0, 0, 0, None, 0)
            if isinstance(stress, tuple) and stress and stress[0] == 0:
                stress_err = None
                break
            stress_err = "GetMinMaxStress 返回 %r" % (stress[0] if isinstance(stress, tuple) else stress,)
        except Exception as e:
            stress_err = str(e)[:140]
        if attempt == 1:
            # 兜底：激活配置后重试（重新打开文档后应力偶尔读不到）
            try:
                study.ActivateConfiguration()
            except Exception:
                pass
        time.sleep(1.0)

    def unpack(v):
        """实测返回 (err, (units_code, min, id, max))。"""
        if isinstance(v, tuple) and len(v) >= 2 and isinstance(v[1], tuple) and len(v[1]) == 4:
            b = v[1]
            return {"units_code": b[0], "min": b[1], "min_id": b[2], "max": b[3]}
        return {"raw": repr(v)[:200]}

    out = {"steps": steps, "displacement": unpack(disp)}
    ok = isinstance(stress, tuple) and len(stress) > 0 and stress[0] == 0
    out["stress"] = unpack(stress) if ok else {"error": stress_err or "未知"}
    return out


def _print_results(r):
    d = r["displacement"]
    print("  步数 =", r["steps"])
    if "min" in d:
        # 实测该零件位移单位是 mm、应力单位是 Pa（SI 默认）
        print("  位移 = min %.6g (节点 %s) / max %.6g (mm)" % (d["min"], d.get("min_id"), d["max"]))
    s = r["stress"]
    if isinstance(s, dict) and "error" in s:
        print("  应力 = 不可用（%s）" % s["error"])
        print("  提示：位移可靠；应力需在求解后同一会话立即读取，")
        print("  重新打开文档后 CW 常返回 code 1。")
    elif isinstance(s, dict) and "min" in s:
        print("  应力 = min %.6g / max %.6g (Pa ≈ %.1f MPa)"
              % (s["min"], s["max"], s["max"] / 1e6))
        print("  提示：固定端锐边常有应力奇异，max 会偏大，宜看位移或加圆角")


def cmd_setup(args):
    validate_mesh_params(args)
    doc_w, md, part, cw, app = _open(args)
    sm = _study_mgr(app, cw)
    study, name = _do_setup(args, app, md, part, doc_w, cw, sm)
    if not args.no_mesh:
        stop = _start_guard(args.mem_guard)
        try:
            _do_mesh(args, study)
        finally:
            if stop:
                stop.set()
    print("  \u2713 研究就绪：%s" % name)
    return 0


def cmd_mesh(args):
    validate_mesh_params(args)
    doc_w, md, part, cw, app = _open(args)
    sm = _study_mgr(app, cw)
    study = _study(sm, args.study)
    stop = _start_guard(args.mem_guard)
    try:
        _do_mesh(args, study)
    finally:
        if stop:
            stop.set()
    return 0


def cmd_run(args):
    doc_w, md, part, cw, app = _open(args)
    sm = _study_mgr(app, cw)
    study = _study(sm, args.study)
    print("  研究 =", study.Name, "| 可用内存 = %.1f GB" % _free_gb())
    stop = _start_guard(args.mem_guard)
    try:
        _do_run(study)
    finally:
        if stop:
            stop.set()
    print("  \u2713 求解完成")
    return 0


def cmd_read(args):
    doc_w, md, part, cw, app = _open(args)
    sm = _study_mgr(app, cw)
    study = _study(sm, args.study)
    print("  文档 =", md.GetTitle(), "| 研究 =", study.Name)
    r = _read_results(study, cw)
    _print_results(r)
    if args.out:
        payload = {"document": md.GetTitle(), "study": str(study.Name), **r}
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print("  JSON → %s (%d B)" % (args.out, os.path.getsize(args.out)))
    return 0


def cmd_solve(args):
    validate_mesh_params(args)
    doc_w, md, part, cw, app = _open(args)
    sm = _study_mgr(app, cw)
    study, name = _do_setup(args, app, md, part, doc_w, cw, sm)
    stop = _start_guard(args.mem_guard)
    try:
        _do_mesh(args, study)
        _do_run(study)
    finally:
        if stop:
            stop.set()
    r = _read_results(study, cw)
    _print_results(r)
    if args.out:
        payload = {"document": md.GetTitle(), "study": name, **r}
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print("  JSON → %s (%d B)" % (args.out, os.path.getsize(args.out)))
    return 0


# ---------------------------------------------------------------- 入口
def main():
    ap = argparse.ArgumentParser(description="SolidWorks Simulation (FEA) 自动化工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, mesh=False):
        p.add_argument("--open", help="先打开该零件")
        p.add_argument("--study", help="研究名（默认最后一个）")
        p.add_argument("--reset", action="store_true",
                       help="加载项不可用时允许先关闭全部文档再加载（会丢未保存修改）")
        if mesh:
            p.add_argument("--size", type=float, default=SAFE_MIN_SIZE, help="全局尺寸，米（默认 0.02）")
            p.add_argument("--tol", type=float, default=SAFE_MIN_TOL, help="容差，米（默认 0.002）")
            p.add_argument("--mesh-type", type=int, default=SAFE_MESH_TYPE, help="网格类型（默认 1）")
            p.add_argument("--unsafe-mesh", dest="unsafe_mesh", action="store_true",
                           help="越过网格安全档")
            p.add_argument("--mem-guard", type=float, default=0.0,
                           help="可用内存低于该 GB 数时终止网格/求解进程（默认关闭）")

    p = sub.add_parser("status", help="诊断文档/材质/加载项/研究")
    common(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("faces", help="列出面（选约束面/受力面）")
    common(p)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_faces)

    p = sub.add_parser("list", help="列出研究")
    common(p)
    p.set_defaults(func=cmd_list)

    for name, fn, helptext in (
        ("setup", cmd_setup, "建研究 + 约束 + 力（可选同时划网格）"),
        ("solve", cmd_solve, "一条龙：建研究→网格→求解→读结果"),
    ):
        p = sub.add_parser(name, help=helptext)
        common(p, mesh=True)
        p.add_argument("--restraint-face", type=int, default=0, help="约束面索引（默认 0）")
        p.add_argument("--force-face", type=int, default=1, help="受力面索引（默认 1）")
        p.add_argument("--force", dest="force_value", type=float, default=100.0,
                       help="法向力，N（默认 100）")
        p.add_argument("--material", help="材质名，如 \"AISI 304\"（零件无材质时必填）")
        p.add_argument("--no-mesh", action="store_true", help="setup 时只建研究不划网格")
        p.add_argument("--out", help="JSON 输出路径")
        p.set_defaults(func=fn)

    p = sub.add_parser("mesh", help="只划网格")
    common(p, mesh=True)
    p.set_defaults(func=cmd_mesh)

    p = sub.add_parser("run", help="只求解")
    common(p)
    p.add_argument("--mem-guard", type=float, default=0.0, help="内存看门狗阈值（GB）")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("read", help="读位移/应力")
    common(p)
    p.add_argument("--out", help="JSON 输出路径")
    p.set_defaults(func=cmd_read)

    args = ap.parse_args()
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        print("  错误：%s" % str(e)[:300])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

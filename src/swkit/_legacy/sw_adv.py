# -*- coding: utf-8 -*-
"""sw_adv.py \u2014 SolidWorks \u5269\u4f59\u80fd\u529b\u8865\u9f50\u5de5\u5177\uff08P0/P1/P2\uff09

\u8bbe\u8ba1\u539f\u5219
--------
1. \u4e0d\u6539\u3001\u4e0d\u6ce8\u518c `user-solidworks` MCP\uff08D:\\bililive\\Solidworks-MCP-Server\uff09\uff0c\u4e0e\u5b83\u5e76\u5b58\u3002
2. \u53ea\u8bfb\u6253\u5f00\uff08OpenDoc6 options=3 = silent|readonly\uff09\uff0c\u4e0d\u4f1a\u6539\u7528\u6237\u56fe\u7eb8\u3002
3. \u6bcf\u4e00\u6b65\u90fd\u628a\u771f\u5b9e\u8fd4\u56de\u503c\u5199\u8fdb\u62a5\u544a\uff0c\u4e0d\u5047\u8bbe\u6210\u529f\u3002

\u547d\u4ee4
----
  props  <file>                 \u5355\u6587\u4ef6\u81ea\u5b9a\u4e49\u5c5e\u6027\uff08\u542b\u6bcf\u4e2a\u914d\u7f6e\uff09
  scan   <dir> [--pattern ...]  \u4e00\u4e2a\u4f1a\u8bdd\u626b\u63cf\u6574\u4e2a\u76ee\u5f55\uff08\u4e0d\u91cd\u590d\u542f\u52a8 SW\uff09
  sim    status                 Simulation \u52a0\u8f7d\u9879\u53ef\u7528\u6027\u81ea\u68c0
  dxp    info <file>            DimXpert \u72b6\u6001\u4e0e\u6570\u91cf
"""
import argparse
import json
import os
import sys
import time

import pythoncom
import win32com.client
import win32com.client.dynamic

def _add_vendor():
    """把自包含的 comtypes 加入 sys.path（不动用户 venv）。"""
    if VENDOR not in sys.path:
        sys.path.insert(0, VENDOR)


def _safe(fn, default=None):
    """实测：Flow 的 GetProjectsCount() 在 AddProject 之后会抛 E_FAIL，查询类调用全部包一层。"""
    try:
        return fn()
    except Exception as e:
        return "ERR %s" % (str(e)[:60],) if default is None else default


def _ct():
    """comtypes 强类型所需的三个类型库（按需生成包装）。"""
    _add_vendor()
    from comtypes.client import GetModule
    return GetModule(SW_TLB), GetModule(DX_TLB), GetModule(FS_SRV_TLB), GetModule(FS_API_TLB)


def _val(obj, name, *a):
    """\u5c5e\u6027\u4e0e\u65b9\u6cd5\u901a\u7528\uff1a\u80fd\u8c03\u5c31\u8c03\uff0c\u4e0d\u80fd\u5c31\u53d6\u5c5e\u6027\uff1b\u8fd4\u56de\u5143\u7ec4\u65f6\u53d6\u7b2c\u4e00\u9879\u3002

    \u5b9e\u6d4b\uff1a\u665a\u7ed1\u5b9a\u4e0b `GetNames` / `GetConfigurationNames` / `GetTitle`
    \u6709\u7684\u662f\u5c5e\u6027\u3001\u6709\u7684\u662f\u65b9\u6cd5\uff0c\u4e14 `Get` \u8fd4\u56de (value, resolved) \u5143\u7ec4\u3002
    """
    v = getattr(obj, name)
    if callable(v):
        v = v(*a)
    if isinstance(v, tuple) and v:
        v = v[0]
    return v


SW_DIR = r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
FS_DIR = r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS Flow Simulation"
SW_TLB = SW_DIR + r"\sldworks.tlb"
DX_TLB = SW_DIR + r"\swdimxpert.tlb"
FS_SRV_TLB = FS_DIR + r"\binCFW\EFDApiSrv.tlb"
FS_API_TLB = FS_DIR + r"\binCFW\EFDApi.tlb"
VENDOR = os.environ.get("SWKIT_VENDOR") or ""

DEFAULT_OUT = os.environ.get("SWKIT_OUT") or os.path.join(os.path.expanduser("~"), "swkit_out")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
EXTS = (".sldprt", ".sldasm", ".slddrw")


# ---------------------------------------------------------------- \u57fa\u7840
def connect(timeout=180):
    """\u62ff\u5230 SolidWorks \u5b9e\u4f8b\u3002\u6ce8\u610f\uff1aRevisionNumber \u5728\u665a\u7ed1\u5b9a\u4e0b\u662f**\u5c5e\u6027**\u3002"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            app = win32com.client.dynamic.Dispatch("SldWorks.Application")
            if app is not None:
                _ = app.RevisionNumber          # \u8bfb\u5c5e\u6027\uff0c\u80fd\u8bfb\u5c31\u7b97\u5c31\u7eea
                return app
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("\u7b49\u4e0d\u5230 SolidWorks COM\uff08%.0fs\uff09" % timeout)


def open_ro(app, path):
    """\u53ea\u8bfb\u65b9\u5f0f\u6253\u5f00\uff0c\u8fd4\u56de (doc, err, warn)\u3002"""
    ext = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}.get(os.path.splitext(path)[1].lower(), 0)
    err = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = app.OpenDoc6(path, ext, 3, "", err, warn)   # 3 = silent | readonly
    return doc, err.value, warn.value


def configs_of(doc):
    """\u5217\u914d\u7f6e\u540d\uff08\u5c5e\u6027\u8fd8\u662f\u65b9\u6cd5\uff0c\u4e24\u79cd\u90fd\u8bd5\uff09\u3002"""
    try:
        names = _val(doc, "GetConfigurationNames")
        if isinstance(names, str):
            return [names]          # 实测：只有一个配置时返回的是字符串，不是列表
        if names:
            return [str(x) for x in names]
    except Exception:
        pass
    try:
        n = doc.GetConfigurationCount
        n = n() if callable(n) else n
        out = []
        for i in range(int(n or 0)):
            try:
                out.append(str(doc.ConfigurationManager.ActiveConfiguration.Name))
            except Exception:
                break
        return out or ["Default"]
    except Exception:
        return ["Default"]


def read_props(doc):
    """\u8bfb\u6bcf\u4e2a\u914d\u7f6e\u7684\u81ea\u5b9a\u4e49\u5c5e\u6027\u3002"""
    res = {}
    try:
        ext = doc.Extension
    except Exception as e:
        return {"_error": "no Extension: %r" % (e,)}
    for cfg in configs_of(doc):
        bag = {}
        try:
            cpm = _val(ext, "CustomPropertyManager", cfg)
            names = _val(cpm, "GetNames") or []
            if isinstance(names, str):
                names = [names]      # 只有一个属性时同样返回字符串
            for nm in names:
                try:
                    bag[str(nm)] = _val(cpm, "Get", str(nm))
                except Exception:
                    bag[str(nm)] = None
        except Exception as e:
            bag["_error"] = repr(e)
        res[cfg] = bag
    return res


def walk(root, pattern=None):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.lower().endswith(EXTS):
                continue
            if pattern and pattern.lower() not in fn.lower():
                continue
            out.append(os.path.join(dirpath, fn))
    return sorted(out)


# ---------------------------------------------------------------- \u5b50\u547d\u4ee4
def cmd_props(args):
    app = connect()
    doc, err, warn = open_ro(app, os.path.abspath(args.file))
    if doc is None:
        print(json.dumps({"ok": False, "file": args.file, "err": err, "warn": warn},
                         ensure_ascii=False))
        return 2
    info = {
        "ok": True,
        "file": os.path.abspath(args.file),
        "bytes": os.path.getsize(args.file),
        "configs": configs_of(doc),
        "props": read_props(doc),
    }
    try:
        app.CloseDoc(_val(doc, "GetTitle"))
    except Exception:
        pass
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


def cmd_scan(args):
    files = walk(args.dir, args.pattern)
    if not files:
        print(json.dumps({"ok": True, "scanned": 0, "note": "\u6ca1\u6709\u5339\u914d\u6587\u4ef6"},
                         ensure_ascii=False))
        return 0
    app = connect()
    rows, t0 = [], time.time()
    for i, path in enumerate(files, 1):
        row = {"file": path, "bytes": os.path.getsize(path)}
        try:
            doc, err, warn = open_ro(app, path)
            if doc is None:
                row.update({"ok": False, "open_err": err})
            else:
                row.update({"ok": True, "configs": configs_of(doc), "props": read_props(doc)})
                try:
                    app.CloseDoc(_val(doc, "GetTitle"))
                except Exception:
                    pass
        except Exception as e:
            row.update({"ok": False, "error": repr(e)})
        rows.append(row)
        if args.verbose:
            print("  [%d/%d] %s ok=%s" % (i, len(files), os.path.basename(path), row.get("ok")),
                  file=sys.stderr)
    dt = time.time() - t0
    out = {
        "ok": True, "dir": os.path.abspath(args.dir), "scanned": len(rows),
        "elapsed_sec": round(dt, 1),
        "ok_count": sum(1 for r in rows if r.get("ok")),
        "fail_count": sum(1 for r in rows if not r.get("ok")),
        "rows": rows,
    }
    os.makedirs(DEFAULT_OUT, exist_ok=True)
    if not args.out:
        args.out = os.path.join(DEFAULT_OUT, "scan_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("  \u626b\u63cf %d \u4e2a\u6587\u4ef6\uff0c\u6210\u529f %d / \u5931\u8d25 %d\uff0c\u8017\u65f6 %.1fs"
          % (out["scanned"], out["ok_count"], out["fail_count"], dt))
    print("  \u62a5\u544a\uff1a%s" % args.out)
    return 0 if out["fail_count"] == 0 else 1


def cmd_sim(args):
    app = connect()
    sw = os.path.dirname(os.path.abspath(args.exe))
    dll = os.path.join(sw, r"Simulation\cosworks.dll")
    res = {"exe_dir": sw, "sim_dll": dll, "exists": os.path.exists(dll)}
    try:
        res["load_addin"] = app.LoadAddIn(dll)
    except Exception as e:
        res["load_addin_error"] = repr(e)
    obj = None
    for i in range(6):
        try:
            obj = app.GetAddInObject("SldWorks.Simulation")
        except Exception:
            obj = None
        if obj is not None:
            res["get_addin_object_round"] = i + 1
            break
        time.sleep(2)
    res["get_addin_object"] = obj is not None
    if obj is not None:
        names = []
        for nm in ("ActiveDoc", "StudyManager", "Application"):
            try:
                obj.__getattr__(nm)
                names.append(nm)
            except Exception:
                pass
        res["idispatch_names_ok"] = names
    res["conclusion"] = ("\u53ef\u7528" if res.get("idispatch_names_ok")
                         else "\u5bf9\u8c61\u5b58\u5728\u4f46\u65e0\u53ef\u7528\u6210\u5458\uff08\u672c\u673a\u5b9e\u6d4b\uff09")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def cmd_dxp(args):
    """DimXpert：读方案与数量；--autodim 会**修改并保存**目标文件。

    实测链路（§566）：
      ext.DimXpertManager(配置名, True) -> IDimXpertManager
      .DimXpertPart → QueryInterface(IDimXpertPart) → GetFeatureCount()/GetAnnotationCount()
    """
    _add_vendor()
    from comtypes.client import CreateObject
    sw, dx, _, _ = _ct()
    app = CreateObject(sw.SldWorks)
    try:
        app.CloseAllDocuments(True)
    except Exception:
        pass
    doc = app.OpenDoc(os.path.abspath(args.file), 1)
    if doc is None:
        print(json.dumps({"ok": False, "reason": "OpenDoc returned None"}, ensure_ascii=False))
        return 2
    md = doc.QueryInterface(sw.IModelDoc2)
    cfg = args.config
    dm = md.Extension.DimXpertManager(cfg, True)
    part = dm.DimXpertPart.QueryInterface(dx.IDimXpertPart)
    res = {
        "ok": True,
        "file": os.path.abspath(args.file),
        "config": cfg,
        "schema": dm.SchemaName,
        "features": part.GetFeatureCount(),
        "annotations": part.GetAnnotationCount(),
    }
    if args.autodim:
        opt = part.GetAutoDimSchemeOption()
        r = part.AutoDimensionScheme(opt)
        md.EditRebuild3()
        res["autodim"] = {
            "return": r,
            "features_after": part.GetFeatureCount(),
            "annotations_after": part.GetAnnotationCount(),
            "saved_bytes": None,
        }
        md.Save3(1, 0, 0)
        res["autodim"]["saved_bytes"] = os.path.getsize(args.file)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def cmd_flow(args):
    """Flow Simulation：status = 看能不能拿到 IApplication；project = 真建一个工程。

    实测链路（§569-572）：
      EFDLauncher.RunProduct() → IApplication
        .SetSilent() / .GetCAD() → ICADApplication.OpenDoc(path) → ICADDocument
        .GetDocument(cadoc) → IDocument → CreateProject(None) → IProject
    """
    _add_vendor()
    from comtypes.client import CreateObject
    sw, _, srv, _ = _ct()
    app_sw = CreateObject(sw.SldWorks)
    out = {"ok": True}
    try:
        out["sw_revision"] = app_sw.RevisionNumber()
        launcher = CreateObject(srv.EFDLauncher)
        out["cad_versions"] = list(launcher.GetAvailableCADVersions())
        fapp = launcher.RunProduct()
        out["application"] = type(fapp).__name__
        fapp.SetSilent()
        out["silent"] = bool(fapp.IsSilentMode())
        cad = fapp.GetCAD()
        out["cad"] = {"version": cad.GetVersionString(), "revision": cad.RevisionNumber()}
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:200]}, ensure_ascii=False, indent=1))
        return 1
    if args.action == "project":
        if not args.file:
            print(json.dumps({"ok": False, "reason": "project 需要 --file"}, ensure_ascii=False))
            return 2
        try:
            app_sw.CloseAllDocuments(True)
        except Exception:
            pass
        doc = app_sw.OpenDoc(os.path.abspath(args.file), 1)
        md = doc.QueryInterface(sw.IModelDoc2)
        cadoc = cad.OpenDoc(os.path.abspath(args.file))
        fdoc = fapp.GetDocument(cadoc)
        out["doc"] = {"title": _safe(lambda: fdoc.GetTitle()),
                      "projects_before": _safe(lambda: fdoc.GetProjectsCount())}
        proj = fdoc.CreateProject(None)
        cfg = str(md.ConfigurationManager.ActiveConfiguration.Name)
        added = None
        try:
            added = fdoc.AddProject(proj, cfg)      # 实测：这一步才把工程真正加入文档
        except Exception as e:
            added = "ERR %s" % (str(e)[:80],)
        out["project"] = {
            "added": added,
            "config": cfg,
            "name": proj.GetName(),
            "has_settings": proj.GetGeneralSettings() is not None,
            "has_features": proj.GetFeatures() is not None,
            "has_solver": proj.GetSolver() is not None,
            "has_results": proj.GetResults() is not None,
            "projects_after": _safe(lambda: fdoc.GetProjectsCount()),
        }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="SolidWorks \u5269\u4f59\u80fd\u529b\u8865\u9f50\u5de5\u5177")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("props", help="\u5355\u6587\u4ef6\u5c5e\u6027")
    p1.add_argument("file")
    p1.set_defaults(func=cmd_props)

    p2 = sub.add_parser("scan", help="\u4e00\u4e2a\u4f1a\u8bdd\u626b\u76ee\u5f55")
    p2.add_argument("dir")
    p2.add_argument("--pattern", default=None)
    p2.add_argument("--out", default=None)
    p2.add_argument("--verbose", action="store_true")
    p2.set_defaults(func=cmd_scan)

    p3 = sub.add_parser("sim", help="Simulation \u52a0\u8f7d\u9879\u81ea\u68c0")
    p3.add_argument("action", choices=["status"])
    p3.add_argument("--exe", default=r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe")
    p3.set_defaults(func=cmd_sim)

    p4 = sub.add_parser("dxp", help="DimXpert 方案/数量")
    p4.add_argument("action", choices=["info"])
    p4.add_argument("file")
    p4.add_argument("--config", default="默认")
    p4.add_argument("--autodim", action="store_true", help="跑自动尺寸方案（会修改并保存文件！）")
    p4.set_defaults(func=cmd_dxp)

    p5 = sub.add_parser("flow", help="Flow Simulation 自检/建工程")
    p5.add_argument("action", choices=["status", "project"])
    p5.add_argument("--file", default=None)
    p5.set_defaults(func=cmd_flow)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

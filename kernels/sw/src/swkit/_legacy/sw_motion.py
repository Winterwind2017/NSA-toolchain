# -*- coding: utf-8 -*-
"""sw_motion.py \u2014 SolidWorks Motion \u7ed3\u679c\u8bfb\u53d6\u5de5\u5177

\u8bbe\u8ba1\u524d\u63d0\uff08\u5168\u90e8\u5b9e\u6d4b\u8fc7\uff09\uff1a
  * \u52a0\u9a6c\u8fbe\u3001\u70b9\u201c\u8ba1\u7b97\u201d\u5fc5\u987b\u5728\u754c\u9762\u5b8c\u6210\uff08CreateDefinition \u6052\u8fd4 None\uff0c
    Calculate \u662f\u5c5e\u6027\u4e14\u8c03\u7528\u4f1a\u5c06\u7ed3\u679c\u6807\u8bb0\u4e3a\u8fc7\u671f\uff09\u3002
  * \u771f\u6b63\u7684\u7ed3\u679c\u96c6\u662f GetResults(4)\uff1b1/2 \u662f\u7a7a\u58f3\uff08IsOutOfDate=True\u3001\u503c\u6052 0\uff09\u3002
  * \u4f4d\u79fb\u4e0d\u80fd\u7528 GetCMPosition\uff08\u8fd4\u56de\u7ec4\u4ef6\u81ea\u8eab\u5750\u6807\u7cfb\uff0c\u5e73\u79fb\u65f6\u6052\u5b9a\uff09\uff0c
    \u8981\u7528 comp.Transform2.ArrayData \u7684 tr[9..11]\u3002
  * GetLinearVelocity / GetAngularVelocity / GetLinearAcceleration \u53c2\u6570\u987a\u5e8f\u662f (Time, Component)\u3002

\u7528\u6cd5\uff1a
  python sw_motion.py list
  python sw_motion.py status
  python sw_motion.py read --samples 11 --out result.json --csv result.csv
  python sw_motion.py read --component "\u8f74\u627f\u5ea7-1" --study "\u8fd0\u52a8\u7b97\u4f8b 2"
"""
import argparse
import csv
import json
import os
import sys
import types

VENDOR = os.environ.get("SWKIT_VENDOR") or ""
if os.path.isdir(VENDOR) and VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)

SW_DIR = r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
RESULT_INDEX_ORDER = (4, 2, 1, 0, 3, 5)


# ---------------------------------------------------------------- \u57fa\u7840
def _pyw():
    import win32com.client.dynamic as d
    return d


def _com():
    from comtypes.client import GetModule, CreateObject
    sw = GetModule(os.path.join(SW_DIR, "sldworks.tlb"))
    ms = GetModule(os.path.join(SW_DIR, "swmotionstudy.tlb"))
    return sw, ms, CreateObject


def _mc(v):
    """\u517c\u5bb9\u65b9\u6cd5\u4e0e\u5c5e\u6027\u4e24\u79cd\u8bbf\u95ee\u5f62\u5f0f\u3002"""
    if isinstance(v, (types.MethodType, types.BuiltinMethodType)):
        return v()
    return v


def _active_doc(open_path=None):
    """\u8fd4\u56de (pywin32 doc wrapper, comtypes IModelDoc2)\u3002"""
    d = _pyw()
    app_w = d.Dispatch("SldWorks.Application")
    if open_path:
        import pythoncom
        e = d.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0) if hasattr(d, "VARIANT") else None
        import win32com.client
        err = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warn = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        ext = os.path.splitext(open_path)[1].lower()
        typ = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}.get(ext, 2)
        doc_w = app_w.OpenDoc6(os.path.abspath(open_path), typ, 3, "", err, warn)
        if doc_w is None:
            raise SystemExit("  \u6253\u4e0d\u5f00\uff1a%s (err=%s)" % (open_path, err.value))
    else:
        doc_w = app_w.ActiveDoc
        if doc_w is None:
            raise SystemExit("  \u5f53\u524d\u6ca1\u6709\u6253\u5f00\u7684\u6587\u6863")
    doc_w = d.Dispatch(doc_w)

    sw, ms, CreateObject = _com()
    app = CreateObject(sw.SldWorks)
    md = app.ActiveDoc.QueryInterface(sw.IModelDoc2)
    return doc_w, md, sw, ms


def _study(md, name=None):
    mgr = md.Extension.GetMotionStudyManager()
    names = list(mgr.GetMotionStudyNames)
    if not names:
        raise SystemExit("  \u8be5\u6587\u6863\u6ca1\u6709\u8fd0\u52a8\u7b97\u4f8b")
    if name:
        hit = [n for n in names if n == name] or [n for n in names if n.startswith(name)]
        if not hit:
            raise SystemExit("  \u627e\u4e0d\u5230\u7b97\u4f8b\uff1a%s\uff08\u53ef\u7528\uff1a%s\uff09"
                             % (name, ", ".join(names)))
        name = hit[0]
    else:
        name = names[0]
    return mgr, mgr.GetMotionStudy(name), name, names


def _components(doc_w):
    """\u9876\u5c42\u7ec4\u4ef6\u5217\u8868 [(name, fixed)]\u3002"""
    out = []
    arr = _mc(doc_w.GetComponents(False))
    for c in (list(arr) if arr else []):
        cc = _pyw().Dispatch(c)
        try:
            out.append((str(_mc(cc.Name2)), bool(_mc(cc.IsFixed))))
        except Exception:
            continue
    return out


def _motor_target(doc_w, study_w):
    """\u4ece\u7b2c\u4e00\u4e2a\u9a6c\u8fbe\u7684 Location \u53d6\u76ee\u6807\u7ec4\u4ef6\u540d\u4e0e\u9a6c\u8fbe\u4fe1\u606f\u3002"""
    d = _pyw()
    arr = _mc(study_w.GetMotionFeatures)
    for f in (list(arr) if arr else []):
        fd = d.Dispatch(f)
        try:
            name = str(_mc(fd.Name))
            typ = str(_mc(fd.GetTypeName2))
        except Exception:
            continue
        info = {"name": name, "type": typ}
        try:
            dfn = d.Dispatch(_mc(fd.GetDefinition))
            info["magnitude"] = _mc(dfn.Magnitude)
            loc = d.Dispatch(_mc(dfn.Location))
            comp = d.Dispatch(_mc(loc.GetComponent))
            info["component"] = str(_mc(comp.Name2))
        except Exception:
            pass
        return info
    return None


def _resolve_component(md, name, comps):
    """\u6309\u540d\u6216\u524d\u7f00\u9009\u4e2d\u7ec4\u4ef6\uff0c\u8fd4\u56de IComponent2\u3002"""
    cand = None
    if name:
        hit = [c for c, _ in comps if c == name] or [c for c, _ in comps if c.startswith(name)]
        if not hit:
            raise SystemExit("  \u627e\u4e0d\u5230\u7ec4\u4ef6\uff1a%s" % name)
        cand = hit[0]
    if cand is None:
        floating = [c for c, f in comps if not f]
        cand = floating[0] if floating else (comps[0][0] if comps else None)
    if cand is None:
        raise SystemExit("  \u6ca1\u6709\u53ef\u7528\u7ec4\u4ef6")
    md.Extension.SelectByID2(cand, "COMPONENT", 0, 0, 0, False, 0, None, 0)
    sel = md.SelectionManager.GetSelectedObject6(1, -1)
    if sel is None:
        raise SystemExit("  \u9009\u4e2d\u7ec4\u4ef6\u5931\u8d25\uff1a%s" % cand)
    sw, _, _ = _com()
    return cand, sel.QueryInterface(sw.IComponent2)


def _valid_results(study, ms):
    """\u6309\u4f18\u5148\u7ea7\u627e\u5230 IsOutOfDate=False \u7684\u7ed3\u679c\u96c6\u3002"""
    for idx in RESULT_INDEX_ORDER:
        try:
            r = study.GetResults(idx)
        except Exception:
            continue
        if r is None:
            continue
        try:
            t = r.QueryInterface(ms.IMotionStudyResults)
        except Exception:
            continue
        try:
            if not t.IsOutOfDate():
                return idx, t
        except Exception:
            continue
    return None, None


# ---------------------------------------------------------------- \u547d\u4ee4
def cmd_list(args):
    doc_w, md, sw, ms = _active_doc(args.open)
    print("  \u6587\u6863 =", _mc(md.GetTitle()))
    comps = _components(doc_w)
    print("  \u9876\u5c42\u7ec4\u4ef6 = %d\uff08\u56fa\u5b9a %d\uff09"
          % (len(comps), sum(1 for _, f in comps if f)))
    mgr = md.Extension.GetMotionStudyManager()
    names = list(mgr.GetMotionStudyNames)
    if not names:
        print("  \u65e0\u8fd0\u52a8\u7b97\u4f8b")
        return 0
    mgr_w = _pyw().Dispatch(doc_w).Extension.GetMotionStudyManager
    for nm in names:
        st = mgr_w.GetMotionStudy(nm)
        n = _mc(st.GetMotionFeaturesCount)
        dur = _mc(st.GetDuration)
        print("")
        print("  [\u7b97\u4f8b] %s  \u8981\u7d20=%d  \u65f6\u957f=%ss" % (nm, n, dur))
        arr = _mc(st.GetMotionFeatures)
        for f in (list(arr) if arr else []):
            fd = _pyw().Dispatch(f)
            try:
                print("     - %-18s %-22s" % (_mc(fd.Name), _mc(fd.GetTypeName2)))
            except Exception:
                continue
            try:
                dfn = _pyw().Dispatch(_mc(fd.GetDefinition))
                loc = _pyw().Dispatch(_mc(dfn.Location))
                comp = _pyw().Dispatch(_mc(loc.GetComponent))
                print("       \u76ee\u6807\u7ec4\u4ef6 = %s | \u5e45\u503c = %s"
                      % (_mc(comp.Name2), _mc(dfn.Magnitude)))
            except Exception:
                pass
    return 0


def cmd_status(args):
    doc_w, md, sw, ms = _active_doc(args.open)
    mgr, study, name, _ = _study(md, args.study)
    print("  \u6587\u6863 =", _mc(md.GetTitle()))
    print("  \u7b97\u4f8b = %s | \u8981\u7d20 = %s | \u65f6\u957f = %s"
          % (name, _mc(study.GetMotionFeaturesCount), _mc(study.GetDuration)))
    study_w = _pyw().Dispatch(doc_w).Extension.GetMotionStudyManager.GetMotionStudy(name)
    motor = _motor_target(doc_w, study_w)
    if motor:
        print("  \u9a6c\u8fbe = %s (%s) | \u5e45\u503c = %s | \u76ee\u6807 = %s"
              % (motor.get("name"), motor.get("type"),
                 motor.get("magnitude"), motor.get("component")))
    print("")
    print("  index  IsOutOfDate  \u53ef\u7528")
    found = None
    for idx in RESULT_INDEX_ORDER:
        try:
            r = study.GetResults(idx)
        except Exception as e:
            print("  %-6d %-12s -- %s" % (idx, "-", str(e)[:40]))
            continue
        if r is None:
            print("  %-6d %-12s None" % (idx, "-"))
            continue
        try:
            t = r.QueryInterface(ms.IMotionStudyResults)
            bad = t.IsOutOfDate()
        except Exception:
            print("  %-6d %-12s QI \u5931\u8d25" % (idx, "-"))
            continue
        print("  %-6d %-12s %s" % (idx, bad, "\u5426" if bad else "\u662f \u2190 \u7528\u8fd9\u4e2a"))
        if not bad and found is None:
            found = idx
    print("")
    if found is None:
        print("  \u7ed3\u8bba\uff1a\u6ca1\u6709\u6709\u6548\u7ed3\u679c\u3002\u8bf7\u5728\u754c\u9762\u70b9\u201c\u8ba1\u7b97\u201d\uff08\u7b97\u4f8b\u7c7b\u578b\u5fc5\u987b\u662f\u57fa\u672c\u8fd0\u52a8/Motion \u5206\u6790\uff09\u3002")
        return 2
    print("  \u7ed3\u8bba\uff1a\u4f7f\u7528 GetResults(%d) \u8bfb\u53d6\u3002" % found)
    return 0


def cmd_read(args):
    doc_w, md, sw, ms = _active_doc(args.open)
    mgr, study, name, _ = _study(md, args.study)
    comps = _components(doc_w)
    study_w = _pyw().Dispatch(doc_w).Extension.GetMotionStudyManager.GetMotionStudy(name)
    motor = _motor_target(doc_w, study_w)
    target = args.component or (motor or {}).get("component")
    comp_name, comp = _resolve_component(md, target, comps)
    print("  \u6587\u6863 =", _mc(md.GetTitle()))
    print("  \u7b97\u4f8b = %s | \u76ee\u6807\u7ec4\u4ef6 = %s" % (name, comp_name))
    if motor:
        print("  \u9a6c\u8fbe = %s (%s) | \u5e45\u503c = %s"
              % (motor.get("name"), motor.get("type"), motor.get("magnitude")))

    idx, res = _valid_results(study, ms)
    if res is None:
        print("")
        print("  \u6ca1\u6709\u6709\u6548\u7ed3\u679c\u96c6\uff08\u6240\u6709 index \u7684 IsOutOfDate \u5747\u4e3a True\uff09\u3002")
        print("  \u2192 \u8bf7\u5728\u754c\u9762\u70b9\u4e00\u6b21\u201c\u8ba1\u7b97\u201d\u540e\u91cd\u8bd5\u3002")
        return 2
    print("  \u7ed3\u679c\u96c6 = GetResults(%d)  IsOutOfDate=False" % idx)

    duration = _mc(study.GetDuration) or 5.0
    n = max(2, args.samples)
    rows = []
    for i in range(n):
        t = round(duration * i / (n - 1.0), 4)
        study.SetTime(t)
        tr = comp.Transform2.ArrayData
        row = {"t": t, "x_mm": tr[9] * 1000, "y_mm": tr[10] * 1000, "z_mm": tr[11] * 1000}
        for key, fn in (("v", "GetLinearVelocity"), ("a", "GetLinearAcceleration"),
                        ("w", "GetAngularVelocity")):
            try:
                row[key] = list(getattr(res, fn)(t, comp).ArrayData)
            except Exception:
                row[key] = None
        rows.append(row)

    p0 = rows[0]
    for r in rows:
        r["disp_mm"] = ((r["x_mm"] - p0["x_mm"]) ** 2 + (r["y_mm"] - p0["y_mm"]) ** 2
                        + (r["z_mm"] - p0["z_mm"]) ** 2) ** 0.5
        r["speed_mm_s"] = ((sum(x * x for x in r["v"])) ** 0.5 * 1000) if r["v"] else 0.0
        r["acc_mm_s2"] = ((sum(x * x for x in r["a"])) ** 0.5 * 1000) if r["a"] else 0.0

    print("")
    print("  t(s)     X(mm)      Y(mm)      Z(mm)    \u4f4d\u79fb(mm)  V(mm/s)  A(mm/s^2)")
    for r in rows:
        print("  %-6.3f %9.2f %9.2f %9.2f  %9.2f  %7.2f  %7.2f"
              % (r["t"], r["x_mm"], r["y_mm"], r["z_mm"],
                 r["disp_mm"], r["speed_mm_s"], r["acc_mm_s2"]))

    payload = {"document": _mc(md.GetTitle()), "study": name, "results_index": idx,
               "component": comp_name, "duration": duration, "motor": motor, "rows": rows}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print("")
        print("  JSON \u2192", args.out, "(%d B)" % os.path.getsize(args.out))
    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["t_s", "x_mm", "y_mm", "z_mm", "disp_mm", "speed_mm_s", "acc_mm_s2",
                        "vx", "vy", "vz", "ax", "ay", "az"])
            for r in rows:
                v = r.get("v") or ["", "", ""]
                a = r.get("a") or ["", "", ""]
                w.writerow([r["t"], "%.4f" % r["x_mm"], "%.4f" % r["y_mm"], "%.4f" % r["z_mm"],
                            "%.4f" % r["disp_mm"], "%.4f" % r["speed_mm_s"],
                            "%.4f" % r["acc_mm_s2"]] + list(v) + list(a))
        print("  CSV  \u2192", args.csv, "(%d B)" % os.path.getsize(args.csv))
    return 0


# ---------------------------------------------------------------- \u5165\u53e3
def main():
    ap = argparse.ArgumentParser(description="SolidWorks Motion \u7ed3\u679c\u8bfb\u53d6\u5de5\u5177")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name, fn, helptext in (("list", cmd_list, "\u5217\u51fa\u6587\u6863/\u7b97\u4f8b/\u9a6c\u8fbe"),
                               ("status", cmd_status, "\u8bca\u65ad\u54ea\u4e2a\u7ed3\u679c\u96c6\u53ef\u7528")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--open", help="\u5148\u6253\u5f00\u8be5\u88c5\u914d\uff08\u53ea\u8bfb\uff09")
        p.add_argument("--study", help="\u7b97\u4f8b\u540d\uff08\u9ed8\u8ba4\u7b2c\u4e00\u4e2a\uff09")
        p.set_defaults(func=fn)

    p = sub.add_parser("read", help="\u8bfb\u53d6\u4f4d\u79fb/\u901f\u5ea6/\u52a0\u901f\u5ea6")
    p.add_argument("--open", help="\u5148\u6253\u5f00\u8be5\u88c5\u914d\uff08\u53ea\u8bfb\uff09")
    p.add_argument("--study", help="\u7b97\u4f8b\u540d\uff08\u9ed8\u8ba4\u7b2c\u4e00\u4e2a\uff09")
    p.add_argument("--component", help="\u76ee\u6807\u7ec4\u4ef6\u540d\u6216\u524d\u7f00\uff08\u9ed8\u8ba4\uff1a\u9a6c\u8fbe\u76ee\u6807\uff09")
    p.add_argument("--samples", type=int, default=11, help="\u91c7\u6837\u70b9\u6570\uff08\u9ed8\u8ba4 11\uff09")
    p.add_argument("--out", help="JSON \u8f93\u51fa\u8def\u5f84")
    p.add_argument("--csv", help="CSV \u8f93\u51fa\u8def\u5f84")
    p.set_defaults(func=cmd_read)

    args = ap.parse_args()
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        print("  \u9519\u8bef\uff1a%s" % str(e)[:200])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""swdm_lite.py \u2014 \u79c1\u4eba\u7248 "DocumentMgr"\uff08\u5c5e\u6027 + BOM + \u56fe\u7eb8\u8868\u683c\uff0c\u5168\u90e8\u843d\u7f13\u5b58\uff09

\u4e3a\u4ec0\u4e48\u4e0d\u80fd\u4ece\u96f6\u5199\u6587\u4ef6\u8bfb\u53d6\u5668\uff08\u5b9e\u6d4b\uff09
--------------------------------------
  \u2022 .sldprt/.sldasm/.slddrw \u4e0d\u662f OLE \u590d\u5408\u6587\u6863\uff08olefile \u76f4\u63a5\u62d2\u7edd\uff09
  \u2022 \u5df2\u77e5\u5c5e\u6027\u540d/\u503c\u5728\u539f\u59cb\u5b57\u8282\u91cc 0 \u547d\u4e2d\uff1bzlib/gzip \u5747\u4e3a\u5047\u9633\u6027
  \u2022 \u5168\u6587\u4ec5 73 \u6bb5\u65e0\u610f\u4e49 ASCII \u7247\u6bb5
  \u21d2 \u8f7d\u8377\u4e13\u6709\u538b\u7f29/\u6df7\u6dc6\uff0c\u6ca1\u6709\u7801\u5178\u89e3\u4e0d\u5f00\uff1b\u672c\u5de5\u5177\u4e0d\u7834\u89e3\u8bb8\u53ef\uff0c\u53ea\u505a\u80fd\u529b\u7b49\u4ef7\u91cd\u5efa\u3002

\u505a\u6cd5
----
  sync  \u2192 \u7528**\u4e00\u4e2a**\u65e0\u5934 SolidWorks \u4f1a\u8bdd\u8bfb\uff1a\u5c5e\u6027/\u914d\u7f6e\uff08\u96f6\u4ef6\u4e0e\u88c5\u914d\uff09\u3001\u88c5\u914d\u7ec4\u4ef6\u6811\uff08BOM\uff09\u3001\u56fe\u7eb8\u89c6\u56fe\u4e0e\u8868\u683c
  query/bom/tables/show/stats/export \u2192 \u53ea\u8bfb SQLite\uff0c**\u4e0d\u542f\u52a8 SolidWorks**
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import types

import pythoncom
import win32com.client
import win32com.client.dynamic

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

def _default_db():
    env = os.environ.get("SWKIT_DM_DB")
    if env:
        return env
    legacy = os.environ.get("SWKIT_LEGACY_DB") or r"D:\bililive\mcp-patches\swdm_lite.db"
    if os.path.exists(legacy):
        return legacy
    home = os.path.join(os.path.expanduser("~"), ".swkit")
    os.makedirs(home, exist_ok=True)
    return os.path.join(home, "swdm_lite.db")


DB = _default_db()
EXTS = (".sldprt", ".sldasm", ".slddrw")
SKIP = {".git", "node_modules", "__pycache__", ".venv"}
MAX_DEPTH = 10
MAX_COMPS = 5000
MAX_TABLE_ROWS = 60
MAX_TABLE_COLS = 14

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY, ext TEXT, size INTEGER, mtime REAL,
  configs TEXT, props TEXT, scanned_at REAL, ok INTEGER, note TEXT
);
CREATE TABLE IF NOT EXISTS components (
  asm_path TEXT, parent TEXT, depth INTEGER, name TEXT, child_path TEXT,
  config TEXT, suppressed INTEGER, visible INTEGER
);
CREATE TABLE IF NOT EXISTS drawing_views (
  drw_path TEXT, view_index INTEGER, view_name TEXT, table_count INTEGER
);
CREATE TABLE IF NOT EXISTS drawing_tables (
  drw_path TEXT, view_name TEXT, table_index INTEGER,
  rows INTEGER, cols INTEGER, title TEXT, cells TEXT
);
CREATE INDEX IF NOT EXISTS idx_comp ON components(asm_path);
CREATE INDEX IF NOT EXISTS idx_dtbl ON drawing_tables(drw_path);
CREATE INDEX IF NOT EXISTS idx_dview ON drawing_views(drw_path);
"""


# ------------------------------------------------------------------ \u5e2e\u624b
def db():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    return conn


def maybe_call(v):
    """\u5b9e\u6d4b\u5751\uff1aCDispatch \u81ea\u8eab callable\uff0c\u7528 callable() \u4f1a\u628a\u5bf9\u8c61\u5f53\u65b9\u6cd5\u8c03\u3002"""
    if isinstance(v, (types.MethodType, types.BuiltinMethodType)):
        return v()
    return v


def wrap_all(v, depth=0):
    """\u5b9e\u6d4b\u5751\uff1aGetViews / GetTableAnnotations \u8fd4\u56de\u5d4c\u5957\u5143\u7ec4 + \u539f\u59cb PyIDispatch\u3002"""
    out = []
    if v is None or depth > 4:
        return out
    if isinstance(v, (tuple, list)):
        for x in v:
            out.extend(wrap_all(x, depth + 1))
        return out
    try:
        out.append(win32com.client.dynamic.Dispatch(v))
    except Exception:
        out.append(v)
    return out


def open_ro(app, path):
    t = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}[os.path.splitext(path)[1].lower()]
    e = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    w = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    return app.OpenDoc6(path, t, 3, "", e, w), e.value, w.value


def walk(root):
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [x for x in dns if x not in SKIP]
        for fn in fns:
            if fn.startswith("~$"):
                continue
            if fn.lower().endswith(EXTS):
                out.append(os.path.join(dp, fn))
    return sorted(out)


# ------------------------------------------------------- \u88c5\u914d\u7ec4\u4ef6\u6811
def read_components(asm):
    """\u9012\u5f52\u8bfb\u7ec4\u4ef6\u6811\uff1b\u8fd4\u56de\u884c\u5217\u8868 + \u7edf\u8ba1\u3002"""
    rows = []
    stats = {"max_depth": 0, "truncated": False}

    def rec(comp, parent, depth):
        if len(rows) >= MAX_COMPS or depth > MAX_DEPTH:
            stats["truncated"] = True
            return
        try:
            name = str(maybe_call(comp.Name2))
        except Exception:
            name = ""
        try:
            cpath = str(maybe_call(comp.GetPathName))
        except Exception:
            cpath = ""
        try:
            cfg = str(maybe_call(comp.ReferencedConfiguration))
        except Exception:
            cfg = ""
        try:
            sup = 1 if maybe_call(comp.IsSuppressed) else 0
        except Exception:
            sup = 0
        try:
            vis = int(maybe_call(comp.Visible))
        except Exception:
            vis = -1
        rows.append({"parent": parent, "depth": depth, "name": name,
                     "child_path": cpath, "config": cfg,
                     "suppressed": sup, "visible": vis})
        stats["max_depth"] = max(stats["max_depth"], depth)
        if sup:
            return                       # \u538b\u7f29\u7684\u4e0d\u5f80\u4e0b\u8d70
        try:
            kids = wrap_all(maybe_call(comp.GetChildren))
        except Exception:
            kids = []
        for k in kids:
            rec(k, name, depth + 1)

    try:
        top = wrap_all(maybe_call(asm.GetComponents(False)))
    except Exception as e:
        return [], {"error": str(e)[:100]}
    for c in top:
        rec(c, "", 0)
    return rows, stats


# ------------------------------------------------------------ \u5de5\u7a0b\u56fe\u8868\u683c
def read_drawing(drw):
    rows_v, rows_t = [], []
    try:
        views = wrap_all(maybe_call(drw.GetViews))
    except Exception as e:
        return [], [], {"error": str(e)[:100]}
    for i, v in enumerate(views):
        try:
            vname = str(maybe_call(v.Name))
        except Exception:
            vname = ""
        try:
            tabs = wrap_all(maybe_call(v.GetTableAnnotations))
        except Exception:
            tabs = []
        rows_v.append({"view_index": i, "view_name": vname, "table_count": len(tabs)})
        for k, t in enumerate(tabs):
            try:
                rc = maybe_call(t.RowCount)
                cc = maybe_call(t.ColumnCount)
            except Exception:
                continue
            rc = rc if isinstance(rc, int) else 0
            cc = cc if isinstance(cc, int) else 0
            try:
                title = str(maybe_call(t.Title))
            except Exception:
                title = ""
            cells = []
            for r in range(min(rc, MAX_TABLE_ROWS)):
                row = []
                for c in range(min(cc, MAX_TABLE_COLS)):
                    val = ""
                    for access in (lambda: t.Text(r, c),
                                   lambda: t.Text[r, c],
                                   lambda: t.GetText(r, c)):
                        try:
                            val = str(maybe_call(access()))
                            break
                        except Exception:
                            continue
                    row.append(val)
                cells.append(row)
            rows_t.append({"view_name": vname, "table_index": k,
                           "rows": rc, "cols": cc, "title": title,
                           "cells": cells,
                           "truncated": rc > MAX_TABLE_ROWS or cc > MAX_TABLE_COLS})
    return rows_v, rows_t, {}


# ------------------------------------------------------------------ sync
def cmd_sync(args):
    from sw_adv import connect, configs_of, read_props, _val
    conn = db()
    files = walk(args.dir)

    gone = [r[0] for r in conn.execute("SELECT path FROM files")
            if not os.path.exists(r[0])]
    for g in gone:
        conn.execute("DELETE FROM files WHERE path=?", (g,))
        conn.execute("DELETE FROM components WHERE asm_path=?", (g,))
        conn.execute("DELETE FROM drawing_views WHERE drw_path=?", (g,))
        conn.execute("DELETE FROM drawing_tables WHERE drw_path=?", (g,))
    if gone:
        conn.commit()
        print("  cleaned stale rows = %d" % len(gone), flush=True)

    refresh_ext = ("." + args.refresh_ext.lstrip(".")) if getattr(args, "refresh_ext", None) else None
    cached = {r[0]: (r[1], r[2]) for r in
              conn.execute("SELECT path, size, mtime FROM files WHERE ok=1")}
    if getattr(args, "refresh", False) or refresh_ext:
        cached = {k: v for k, v in cached.items()
                  if refresh_ext and not k.lower().endswith(refresh_ext)}
    todo = []
    for p in files:
        st = os.stat(p)
        old = cached.get(p)
        if old and old[0] == st.st_size and abs(old[1] - st.st_mtime) < 1.0:
            continue
        todo.append((p, st.st_size, st.st_mtime))
    print("  \u76ee\u5f55\u6587\u4ef6 = %d\uff0c\u7f13\u5b58\u547d\u4e2d = %d\uff0c\u9700\u8bfb = %d"
          % (len(files), len(files) - len(todo), len(todo)), flush=True)
    if not todo:
        print("  \u5168\u90e8\u5df2\u7f13\u5b58\uff0c\u65e0\u9700\u542f\u52a8 SolidWorks")
        return 0

    app = connect()
    okc = 0
    ncomp = ntbl = 0
    t0 = time.time()
    for i, (p, size, mtime) in enumerate(todo, 1):
        ext = os.path.splitext(p)[1].lower()
        row = {"configs": None, "props": None, "ok": 0, "note": ""}
        for attempt in (0, 1):
            try:
                doc, err, warn = open_ro(app, p)
                if doc is None:
                    row["note"] = "open_err=%s" % err
                    break
                row["configs"] = configs_of(doc)
                row["props"] = read_props(doc)
                row["ok"] = 1
                row["note"] = ""
                if ext == ".sldasm":
                    comps, st = read_components(doc)
                    conn.execute("DELETE FROM components WHERE asm_path=?", (p,))
                    for c in comps:
                        conn.execute(
                            "INSERT INTO components(asm_path,parent,depth,name,child_path,"
                            "config,suppressed,visible) VALUES(?,?,?,?,?,?,?,?)",
                            (p, c["parent"], c["depth"], c["name"], c["child_path"],
                             c["config"], c["suppressed"], c["visible"]))
                    ncomp += len(comps)
                    if st.get("error"):
                        row["note"] = "components: %s" % st["error"]
                elif ext == ".slddrw":
                    rv, rt, st = read_drawing(doc)
                    conn.execute("DELETE FROM drawing_views WHERE drw_path=?", (p,))
                    conn.execute("DELETE FROM drawing_tables WHERE drw_path=?", (p,))
                    for v in rv:
                        conn.execute(
                            "INSERT INTO drawing_views(drw_path,view_index,view_name,table_count)"
                            " VALUES(?,?,?,?)",
                            (p, v["view_index"], v["view_name"], v["table_count"]))
                    for t in rt:
                        conn.execute(
                            "INSERT INTO drawing_tables(drw_path,view_name,table_index,"
                            "rows,cols,title,cells) VALUES(?,?,?,?,?,?,?)",
                            (p, t["view_name"], t["table_index"], t["rows"], t["cols"],
                             t["title"], json.dumps(t["cells"], ensure_ascii=False)))
                    ntbl += len(rt)
                    if st.get("error"):
                        row["note"] = "drawing: %s" % st["error"]
                okc += 1
                try:
                    app.CloseDoc(_val(doc, "GetTitle"))
                except Exception:
                    pass
                break
            except Exception as e:
                msg = repr(e)
                row["note"] = msg[:120]
                if attempt == 0 and ("RPC" in msg or "-2147023174" in msg or "-2147023170" in msg):
                    print("     ! SW \u4f1a\u8bdd\u6389\u7ebf\uff0c\u91cd\u5efa\u540e\u91cd\u8bd5\uff1a%s"
                          % os.path.basename(p), flush=True)
                    try:
                        app = connect()
                    except Exception as e2:
                        row["note"] = "reconnect_failed %r" % (e2,)
                        break
                    continue
                break
        conn.execute(
            "INSERT INTO files(path,ext,size,mtime,configs,props,scanned_at,ok,note)"
            " VALUES(?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(path) DO UPDATE SET ext=excluded.ext,size=excluded.size,"
            " mtime=excluded.mtime,configs=excluded.configs,props=excluded.props,"
            " scanned_at=excluded.scanned_at,ok=excluded.ok,note=excluded.note",
            (p, ext, size, mtime,
             json.dumps(row["configs"], ensure_ascii=False),
             json.dumps(row["props"], ensure_ascii=False),
             time.time(), row["ok"], row["note"]))
        if i % 25 == 0 or i == len(todo):
            conn.commit()
            print("     [%d/%d] \u6210\u529f %d  \u7ec4\u4ef6 %d  \u8868\u683c %d  %.0fs"
                  % (i, len(todo), okc, ncomp, ntbl, time.time() - t0), flush=True)
        if i % 40 == 0:
            try:
                app.CloseAllDocuments(True)
            except Exception:
                pass
    conn.commit()
    print("  \u5b8c\u6210\uff1a\u8bfb %d\uff0c\u6210\u529f %d\uff0c\u7ec4\u4ef6 %d\uff0c\u8868\u683c %d\uff0c%.1fs"
          % (len(todo), okc, ncomp, ntbl, time.time() - t0))
    return 0


# ------------------------------------------------------------- \u67e5\u8be2\u7c7b
def _flat_props(props_j):
    out = {}
    try:
        d = json.loads(props_j) if props_j else {}
    except Exception:
        return out
    for cfg, bag in (d or {}).items():
        if isinstance(bag, dict):
            for k, v in bag.items():
                if k != "_error":
                    out.setdefault(k, v)
    return out


def cmd_query(args):
    conn = db()
    hits = []
    for path, ext, size, props_j in conn.execute(
            "SELECT path,ext,size,props FROM files WHERE ok=1"):
        if args.dir and not path.lower().startswith(os.path.abspath(args.dir).lower()):
            continue
        if args.ext and ext != ("." + args.ext.lstrip(".")):
            continue
        flat = _flat_props(props_j)
        if args.prop:
            key, _, want = args.prop.partition("=")
            if key not in flat:
                continue
            if want and str(flat.get(key)) != want:
                continue
        hits.append({"path": path, "size": size, "props": flat})
        if args.limit and len(hits) >= args.limit:
            break
    if args.csv:
        import csv
        keys = sorted({k for h in hits for k in h["props"]})
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["path", "size"] + keys)
            for h in hits:
                w.writerow([h["path"], h["size"]] + [h["props"].get(k, "") for k in keys])
        print("  \u5df2\u5bfc\u51fa %d \u884c \u2192 %s" % (len(hits), args.csv))
        return 0
    print(json.dumps(hits[: args.print], ensure_ascii=False, indent=1))
    print("  \u5339\u914d %d \u4e2a\uff08\u5df2\u6253\u5370 %d\uff09" % (len(hits), min(len(hits), args.print)))
    return 0


def cmd_bom(args):
    """\u8bfb\u7f13\u5b58\u91cc\u7684\u88c5\u914d\u7ec4\u4ef6\u6811\uff08BOM \u5c55\u5f00\uff09\u3002"""
    conn = db()
    asm = os.path.abspath(args.file)
    rows = conn.execute(
        "SELECT parent,depth,name,child_path,config,suppressed,visible"
        " FROM components WHERE asm_path=? ORDER BY rowid", (asm,)).fetchall()
    if not rows:
        print("  \u7f13\u5b58\u91cc\u6ca1\u6709\u4e0e %s \u5173\u8054\u7684\u7ec4\u4ef6\u6811\uff08\u662f\u5426\u6ca1 sync\uff1f\uff09" % os.path.basename(asm))
        return 2
    if args.json:
        print(json.dumps([{"parent": r[0], "depth": r[1], "name": r[2],
                           "path": r[3], "config": r[4],
                           "suppressed": bool(r[5]), "visible": r[6]}
                          for r in rows], ensure_ascii=False, indent=1))
        return 0
    for r in rows[: args.limit]:
        print("  %s%-40s cfg=%-8s %s%s" % (
            "  " * r[1], str(r[2])[:40], str(r[4])[:8],
            "" if not r[5] else "[\u538b\u7f29] ",
            os.path.basename(str(r[3]))[:36]))
    print("  \u7ec4\u4ef6\u603b\u6570 = %d\uff08\u5df2\u6253\u5370 %d\uff09" % (len(rows), min(len(rows), args.limit)))
    return 0


def cmd_tables(args):
    """\u8bfb\u7f13\u5b58\u91cc\u7684\u5de5\u7a0b\u56fe\u89c6\u56fe/\u8868\u683c\u3002"""
    conn = db()
    drw = os.path.abspath(args.file)
    views = conn.execute("SELECT view_index,view_name,table_count FROM drawing_views"
                         " WHERE drw_path=? ORDER BY view_index", (drw,)).fetchall()
    tabs = conn.execute("SELECT view_name,table_index,rows,cols,title,cells"
                        " FROM drawing_tables WHERE drw_path=? ORDER BY rowid", (drw,)).fetchall()
    if not views and not tabs:
        print("  \u7f13\u5b58\u91cc\u6ca1\u6709 %s \u7684\u56fe\u7eb8\u6570\u636e" % os.path.basename(drw))
        return 2
    print("  \u89c6\u56fe\u6570 = %d" % len(views))
    for i, nm, n in views:
        print("     [%d] %-24s tables=%d" % (i, str(nm)[:24], n))
    print("  \u8868\u683c\u6570 = %d" % len(tabs))
    for vn, ti, rc, cc, title, cells_j in tabs[: args.limit]:
        print("  \u2605 \u89c6\u56fe %r \u8868[%d]  %dx%d  title=%r" % (str(vn)[:18], ti, rc, cc, str(title)[:28]))
        try:
            cells = json.loads(cells_j)
        except Exception:
            cells = []
        for r in cells[: args.rows]:
            print("     " + " | ".join(str(c)[:16] for c in r))
    return 0


def cmd_show(args):
    conn = db()
    r = conn.execute("SELECT path,size,mtime,configs,props,ok,note FROM files WHERE path=?",
                     (os.path.abspath(args.file),)).fetchone()
    if not r:
        print("  \u7f13\u5b58\u91cc\u6ca1\u6709\uff1a%s" % args.file)
        return 2
    print(json.dumps({"path": r[0], "size": r[1], "mtime": r[2],
                      "configs": json.loads(r[3]) if r[3] else None,
                      "props": json.loads(r[4]) if r[4] else None,
                      "ok": r[5], "note": r[6]}, ensure_ascii=False, indent=1))
    return 0


def cmd_stats(args):
    conn = db()
    total, okc = conn.execute("SELECT COUNT(*), SUM(ok) FROM files").fetchone()
    print("  \u7f13\u5b58\uff1a%s\uff08%d B\uff09" % (DB, os.path.getsize(DB) if os.path.exists(DB) else 0))
    print("  \u6587\u4ef6\u6570 = %d\uff0c\u6210\u529f = %d" % (total or 0, okc or 0))
    for ext, n in conn.execute("SELECT ext, COUNT(*) FROM files GROUP BY ext ORDER BY 2 DESC"):
        print("     %-8s %d" % (ext, n))
    nprops = sum(len(_flat_props(pj)) for (pj,) in
                 conn.execute("SELECT props FROM files WHERE props IS NOT NULL"))
    nc, na = conn.execute("SELECT COUNT(*), COUNT(DISTINCT asm_path) FROM components").fetchone()
    nt, nd = conn.execute("SELECT COUNT(*), COUNT(DISTINCT drw_path) FROM drawing_tables").fetchone()
    nv = conn.execute("SELECT COUNT(*) FROM drawing_views").fetchone()[0]
    print("  \u5c5e\u6027\u6761\u76ee = %d" % nprops)
    print("  \u7ec4\u4ef6\u884c = %d\uff08\u6765\u81ea %d \u4e2a\u88c5\u914d\uff09" % (nc or 0, na or 0))
    print("  \u5de5\u7a0b\u56fe\u89c6\u56fe\u884c = %d\uff0c\u8868\u683c = %d\uff08\u6765\u81ea %d \u5f20\u56fe\uff09"
          % (nv or 0, nt or 0, nd or 0))
    return 0


def cmd_export(args):
    args.prop = None
    args.ext = None
    args.dir = None
    args.limit = None
    args.csv = args.csv_path
    args.print = 0
    return cmd_query(args)


def main(argv=None):
    ap = argparse.ArgumentParser(description="\u79c1\u4eba\u7248 DocumentMgr\uff08\u5c5e\u6027+BOM+\u56fe\u7eb8\u8868\u683c\uff09")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sync")
    p.add_argument("dir")
    p.add_argument("--refresh", action="store_true", help="忽略缓存全量重读")
    p.add_argument("--refresh-ext", default=None, help="只重读某类，如 slddrw")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("query")
    p.add_argument("--prop", default=None)
    p.add_argument("--dir", default=None)
    p.add_argument("--ext", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--print", dest="print", type=int, default=8)
    p.add_argument("--csv", default=None)
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("bom")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_bom)

    p = sub.add_parser("tables")
    p.add_argument("file")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--rows", type=int, default=8)
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser("show")
    p.add_argument("file")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stats")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("export")
    p.add_argument("csv_path")
    p.set_defaults(func=cmd_export)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

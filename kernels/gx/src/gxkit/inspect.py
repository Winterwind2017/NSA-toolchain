"""离线读 `.gx3`：程序源码、步信息、编译 IL、软元件模板、标签。

这一层完全不碰界面，纯 ZIP + SQLite，因此可以作为"动作层"的独立判据。

实测（GX Works3 1.117 / FX5U）：
  - `*_STDB.db` 的 `StBlocks(id, pos, data)`：`data` **就是 ST 源码原文**（含 \\r\\n）
  - `*_StepInfo.db`：`T_Block` / `T_Step` / `T_SourcePos(Row=,Col=,StrLen=)`
    → 每个 MIL 步对应源码里的一段
  - `*_MilDB.db` 的 `MIL(id, pos, data, ConvTarget)`：编译后的 IL 文本（`op=...`）
  - `*_DC.db` 的 `DEVICE_DATA`：FX5U 的**系统软元件模板**（2935 行，各工程相同）
  - `LabelData.db`：标签表（LabelTbl / RowTbl / ColumnDataTbl）
"""

from __future__ import annotations

import pathlib
import re
import sqlite3
import tempfile
import zipfile

__all__ = [
    "unpack", "read_config", "read_progress", "read_st_blocks", "read_steps",
    "read_mil", "read_devices", "read_labels", "st_source", "st_sources",
    "steps_with_source", "program_names",
]

_TMP: dict[str, tuple[tuple[int, int], pathlib.Path]] = {}


def _materials(gx3: str | pathlib.Path) -> pathlib.Path:
    """把 .gx3 里的 .db 解到临时目录。

    缓存键带上 (mtime_ns, size)：工程被重新保存后必须重新解，否则读到旧数据
    （踩过：导入标签后读 LabelData 还是导入前的 54 行）。
    """
    p = pathlib.Path(gx3).resolve()
    st = p.stat()
    key = str(p)
    stamp = (st.st_mtime_ns, st.st_size)
    if key in _TMP and _TMP[key][0] == stamp and _TMP[key][1].exists():
        return _TMP[key][1]
    d = pathlib.Path(tempfile.mkdtemp(prefix="gxkit_unpack_"))
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            if n.endswith(".db") or n.endswith(".xml") or n.endswith(".txt"):
                target = d / n.replace("/", "__")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(n))
    _TMP[key] = (stamp, d)
    return d


def _db(gx3, suffix: str) -> sqlite3.Connection | None:
    dbs = _dbs(gx3, suffix)
    return dbs[0] if dbs else None


def _dbs(gx3, suffix: str) -> list[sqlite3.Connection]:
    """每个程序一套 STDB/StepInfo/MilDB —— 必须全部读，不能只读第一个。

    实测：新建工程只有 ProgPou 一套；导入 XML 建出 PrgGen 后多出一套
    （`22bade8c81709adb_STDB.db` 里就是导入程序的源码）。
    """
    d = _materials(gx3)
    out: list[sqlite3.Connection] = []
    for hit in sorted(d.glob("*" + suffix)):
        try:
            out.append(sqlite3.connect(str(hit)))
        except sqlite3.Error:
            continue
    return out


def _as_text(value) -> str:
    """SQLite 里可能是 TEXT，也可能是 BLOB（XML 导入的程序常见 UTF-16LE）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raw = bytes(value)
    for enc in ("utf-16-le", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


def unpack(gx3: str | pathlib.Path) -> dict:
    p = pathlib.Path(gx3)
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        return {"path": str(p), "bytes": p.stat().st_size, "entries": len(names),
                "names": names}


def read_config(gx3: str | pathlib.Path) -> dict:
    """`!!Config.xml` → Unit / UnitId / Title。"""
    p = pathlib.Path(gx3)
    out: dict = {}
    if not p.exists():
        return out
    with zipfile.ZipFile(p) as z:
        raw = z.read("!!Config.xml").decode("utf-8-sig", "replace")
    for attr in ("Unit", "UnitId", "Title", "SecurityVersion"):
        m = re.search(r'%s="([^"]*)"' % attr, raw)
        if m:
            out[attr] = m.group(1)
    return out


def read_progress(gx3: str | pathlib.Path) -> dict:
    """`ConvertData/Progress.txt` → 总错误/警告 + 逐阶段 + 失败阶段。"""
    p = pathlib.Path(gx3)
    out = {"found": False, "errors": None, "warnings": None, "stages": [],
           "failed_stages": [], "raw": ""}
    if not p.exists():
        return out
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.endswith("Progress.txt")]
        if not names:
            return out
        text = z.read(names[0]).decode("utf-8", "replace")
    out["found"] = True
    out["raw"] = text[-2000:]
    stages = re.findall(r"^(.*?)\.\.\.\r?\nError:(\d+),Warning:(\d+)", text, re.M)
    out["stages"] = [{"stage": s.strip(), "errors": int(e), "warnings": int(w)}
                     for s, e, w in stages]
    out["failed_stages"] = [x["stage"] for x in out["stages"] if x["errors"] > 0]
    m = re.search(r"错误：(\d+)、警告：(\d+)", text)
    if m:
        out["errors"], out["warnings"] = int(m.group(1)), int(m.group(2))
    return out


def read_st_blocks(gx3: str | pathlib.Path) -> list[dict]:
    """全部程序的 ST 源码块。**每个程序一套 `*_STDB.db`**，必须逐个读。

    返回项：`{id, pos, text, db}`，`db` 是该 STDB 的文件名（用来区分程序）。
    """
    out: list[dict] = []
    for path in sorted(_materials(gx3).glob("*_STDB.db")):
        try:
            con = sqlite3.connect(str(path))
            rows = con.execute(
                "select id, pos, data from StBlocks order by pos").fetchall()
        except sqlite3.Error:
            continue
        finally:
            try:
                con.close()          # type: ignore[possibly-undefined]
            except Exception:
                pass
        for r in rows:
            out.append({"id": r[0], "pos": r[1], "text": _as_text(r[2]),
                        "db": path.name})
    return out


def st_sources(gx3: str | pathlib.Path) -> dict[str, str]:
    """按 STDB 文件分组的源码：`{db_name: text}`（每个程序一条）。"""
    out: dict[str, str] = {}
    for b in read_st_blocks(gx3):
        out.setdefault(b["db"], "")
        out[b["db"]] += b["text"]
    return out


def st_source(gx3: str | pathlib.Path) -> str:
    """全部程序的源码拼成一份（多程序时用于"包含在某处"的判断）。"""
    return "\n".join(t for t in st_sources(gx3).values() if t.strip())


def flat(text: str) -> str:
    """去掉全部空白（导入会改写换行/空行，比较时用这个口径）。"""
    return "".join(str(text).split())


def label_names(gx3: str | pathlib.Path, column_id: int = 2) -> list[str]:
    """标签名（默认取 ColumnDataTbl.ColumnID=2，实测名称就在这一列）。"""
    return [r["value"] for r in read_labels(gx3)
            if r.get("column_id") == column_id
            and isinstance(r.get("value"), str) and r["value"]]


def source_matches(gx3: str | pathlib.Path, code: str) -> bool:
    """工程里是否存在内容等于 code 的程序正文（忽略空白差异）。"""
    want = flat(code)
    return any(flat(v) == want for v in st_sources(gx3).values() if v.strip())


def program_names(gx3: str | pathlib.Path) -> list[str]:
    """程序名：从编译日志的阶段名里取（软件自己列出来的）。"""
    names = []
    for st in read_progress(gx3).get("stages", []):
        m = re.match(r"程序\((.+?)\)", st["stage"])
        if m and m.group(1) not in names:
            names.append(m.group(1))
    return names


def read_steps(gx3: str | pathlib.Path) -> list[dict]:
    """步信息：每步的 MIL 号、大小，以及源码坐标 Row/Col/StrLen（每个程序一套）。"""
    steps: list[dict] = []
    for path in sorted(_materials(gx3).glob("*_StepInfo.db")):
        try:
            con = sqlite3.connect(str(path))
            src: dict[tuple[str, int], dict] = {}
            for block, mil, pos in con.execute(
                    "select BlockID, MilID, SourcePosition from T_SourcePos"):
                m = re.match(r"Row=(\d+),Col=(\d+),StrLen=(\d+)", pos or "")
                src[(block, mil)] = ({"row": int(m.group(1)), "col": int(m.group(2)),
                                      "strlen": int(m.group(3))} if m else {})
            for pos, macro, block, mil, size in con.execute(
                    "select Pos, ElementIDMacroFB, BlockID, MilID, StepSize from T_Step "
                    "order by MilID"):
                info = {"block": block, "mil": mil, "step_size": size, "pos": pos,
                        "db": path.name}
                info.update(src.get((block, mil), {}))
                steps.append(info)
        except sqlite3.Error:
            continue
        finally:
            try:
                con.close()          # type: ignore[possibly-undefined]
            except Exception:
                pass
    return steps


def _block_key(block_id: str) -> str:
    """`_guid/xxxx`（STDB）与 `{XXXX}`（StepInfo）归一化后可比。"""
    b = (block_id or "").strip()
    if b.lower().startswith("_guid/"):
        b = b[6:]
    return b.strip("{}").lower()


def steps_with_source(gx3: str | pathlib.Path) -> list[dict]:
    """步 + 该步对应的源码片段（按 Row/Col/StrLen 切，按块 id 找到对应程序）。"""
    texts: dict[str, str] = {}
    for b in read_st_blocks(gx3):
        texts[_block_key(b["id"])] = b["text"]
    out = []
    for st in read_steps(gx3):
        row, col, ln = st.get("row"), st.get("col"), st.get("strlen")
        text = texts.get(_block_key(st.get("block", "")), "")
        lines = text.splitlines()
        snippet = ""
        if row and col and ln and 1 <= row <= len(lines):
            line = lines[row - 1]
            snippet = line[col - 1: col - 1 + ln]
        item = dict(st)
        item["snippet"] = snippet
        out.append(item)
    return out


def program_list(gx3: str | pathlib.Path) -> dict:
    """列出工程里的每个程序：步数、源码行数、正文与所属块。

    数据来源：
      * 程序名 —— Progress.txt 的 程序(xxx) 阶段
      * 正文   —— 每个程序一套 *_STDB.db 的 StBlocks
      * 步数   —— 每个程序一套 *_StepInfo.db 的 T_Step
    名字与正文的对应关系在文件里没有显式记录（块 id 是 GUID），所以按
    "步数最多的块 → 程序数" 不猜；这里给出 sources 与 locks 两个清单，
    并把能确认的对应关系写成 y_steps（同一块 id 同时出现在 StepInfo 与 STDB）。
    """
    names = program_names(gx3)
    blocks = read_st_blocks(gx3)
    steps: dict[str, int] = {}
    for st in read_steps(gx3):
        key = _block_key(st.get("block", ""))
        steps[key] = steps.get(key, 0) + 1
    sources = []
    for b in blocks:
        key = _block_key(b["id"])
        text = b["text"]
        sources.append({"block": b["id"], "key": key,
                        "chars": len(text),
                        "lines": len([ln for ln in text.splitlines() if ln.strip()]),
                        "steps": steps.get(key, 0),
                        "text": text})
    matched = [s for s in sources if s["steps"] > 0]
    return {"programs": names,
            "program_count": len(names),
            "sources": sources,
            "source_count": len(sources),
            "matched_blocks": len(matched),
            "total_steps": sum(steps.values())}


def project_diff(a: str | pathlib.Path, b: str | pathlib.Path) -> dict:
    """两个 .gx3 的源码级差异（按程序名配对，找不到名字就按块 id 配对）。"""
    import difflib

    pa, pb = program_list(a), program_list(b)
    na, nb = set(pa["programs"]), set(pb["programs"])
    src_a = {s["key"]: s for s in pa["sources"]}
    src_b = {s["key"]: s for s in pb["sources"]}

    changed = []
    for key in src_a.keys() & src_b.keys():
        ta = _norm_lines(src_a[key]["text"])
        tb = _norm_lines(src_b[key]["text"])
        if ta == tb:
            continue
        diff = list(difflib.unified_diff(ta, tb, lineterm="", n=0))
        added = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
        removed = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
        changed.append({"key": key, "added": added, "removed": removed,
                        "diff": diff[:40]})
    return {"programs_a": pa["programs"], "programs_b": pb["programs"],
            "programs_added": sorted(nb - na), "programs_removed": sorted(na - nb),
            "blocks_added": len(src_b.keys() - src_a.keys()),
            "blocks_removed": len(src_a.keys() - src_b.keys()),
            "blocks_changed": len(changed),
            "changed": changed,
            "identical": (not changed and not (nb - na) and not (na - nb)
                          and src_a.keys() == src_b.keys())}


def _norm_lines(text: str) -> list[str]:
    """比较口径：去空白与空行（导入会改写换行/空行）。"""
    return [ln.rstrip() for ln in (text or "").replace("\r\n", "\n").split("\n")
            if ln.strip()]


def read_mil(gx3: str | pathlib.Path) -> list[dict]:
    """编译后的 IL 文本（每个程序一套 `*_MilDB.db`）。"""
    out: list[dict] = []
    for path in sorted(_materials(gx3).glob("*_MilDB.db")):
        try:
            con = sqlite3.connect(str(path))
            rows = con.execute(
                "select id, pos, data, ConvTarget from MIL").fetchall()
        except sqlite3.Error:
            continue
        finally:
            try:
                con.close()          # type: ignore[possibly-undefined]
            except Exception:
                pass
        for r in rows:
            out.append({"id": r[0], "pos": r[1], "data": _as_text(r[2]),
                        "target": r[3], "db": path.name})
    return out


def read_devices(gx3: str | pathlib.Path, limit: int = 50) -> dict:
    """FX5U 的系统软元件模板（不是"程序用了哪些"）。"""
    con = _db(gx3, "_DC.db")
    if con is None:
        return {"rows": 0, "types": [], "commented": 0, "sample": []}
    try:
        total = con.execute("select count(*) from DEVICE_DATA").fetchone()[0]
        types = [r[0] for r in con.execute(
            "select distinct DevCode from DEVICE_DATA order by 1")]
        commented = con.execute(
            "select count(*) from COMMENT_DATA where CmtData is not null and CmtData<>''"
        ).fetchone()[0]
        sample = con.execute(
            "select d.SEQ, d.DevCode, d.DevNoLow, c.CmtData from DEVICE_DATA d "
            "left join COMMENT_DATA c on c.SEQ = d.SEQ "
            "where c.CmtData is not null and c.CmtData<>'' limit ?", (limit,)).fetchall()
    except sqlite3.Error:
        return {"rows": 0, "types": [], "commented": 0, "sample": []}
    finally:
        con.close()
    return {"rows": total, "types": types, "commented": commented,
            "sample": [{"seq": s, "dev_code": t, "no": n, "comment": c}
                       for s, t, n, c in sample]}


def read_labels(gx3: str | pathlib.Path) -> list[dict]:
    """标签：名字取自 ColumnDataTbl，类型取自 LabelTbl。"""
    con = _db(gx3, "LabelData.db")
    if con is None:
        return []
    out: list[dict] = []
    try:
        rows = con.execute(
            "select l.LabelID, l.LabelTypeID, r.RowID, r.RowNo, c.ColumnID, "
            "c.ColumnStrValue, c.ColumnIntValue from LabelTbl l "
            "join RowTbl r on r.LabelID = l.LabelID "
            "left join ColumnDataTbl c on c.LabelID = l.LabelID and c.RowID = r.RowID"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    for label_id, type_id, row_id, row_no, col_id, sval, ival in rows:
        out.append({"label_id": str(label_id), "type_id": type_id, "row_id": row_id,
                    "row_no": row_no, "column_id": col_id,
                    "value": sval if sval is not None else ival})
    return out

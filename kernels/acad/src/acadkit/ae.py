"""AutoCAD Electrical 数据层（**只读、不启动 AutoCAD**）。

Electrical 的元件库是 Access 数据库，装在 `~/Documents/Acade 2025/AeData`：

    AeData/zh-CN/Catalogs/*.mdb   7 个常驻库（default_cat / footprint_lookup /
                                  schematic_lookup / wd_lang1 / wd_picklist /
                                  ace_electrical_standards）
    AeData/zh-CN/Plc/ace_plc.mdb  PLC 模块库（1196 张表）

连接串固定 `Mode=Read`（ACE OLEDB 12.0 实测可用）；所有读操作前后对文件做
SHA-256，用来证明"只读没改文件"。路径可用环境变量 `DSH_AE_AEDATA` 覆盖。
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional, Sequence

ENV_AEDATA = "DSH_AE_AEDATA"


class AeUnavailable(RuntimeError):
    """没有 AeData 或没有 ACE OLEDB 提供者。"""


def aedata_dir() -> Optional[str]:
    env = os.environ.get(ENV_AEDATA)
    if env and os.path.isdir(env):
        return env
    default = os.path.join(os.path.expanduser("~"), "Documents", "Acade 2025",
                           "AeData")
    return default if os.path.isdir(default) else None


def catalog_dir(root: Optional[str] = None) -> Optional[str]:
    root = root or aedata_dir()
    if not root:
        return None
    p = os.path.join(root, "zh-CN", "Catalogs")
    return p if os.path.isdir(p) else None


def catalog_dbs(root: Optional[str] = None) -> List[str]:
    d = catalog_dir(root)
    if not d:
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d)
                  if f.lower().endswith((".mdb", ".accdb")))


def plc_db(root: Optional[str] = None) -> Optional[str]:
    root = root or aedata_dir()
    if not root:
        return None
    p = os.path.join(root, "zh-CN", "Plc", "ace_plc.mdb")
    return p if os.path.isfile(p) else None


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dispatch() -> Any:
    try:
        import win32com.client as w
    except Exception as exc:                        # noqa: BLE001
        raise AeUnavailable("需要 pywin32（Windows）：%s" % exc)
    return w.Dispatch("ADODB.Connection")


def connect(path: str) -> Any:
    """只读打开一个 Access 库。"""
    conn = _dispatch()
    cs = ("Provider=Microsoft.ACE.OLEDB.12.0;Data Source=%s;Mode=Read;"
          "Persist Security Info=False;" % path)
    try:
        conn.Open(cs)
    except Exception as exc:                        # noqa: BLE001
        raise AeUnavailable("打开 %s 失败：%s: %s"
                            % (os.path.basename(path), type(exc).__name__, exc))
    return conn


def tables(conn: Any) -> List[str]:
    out: List[str] = []
    schema = conn.OpenSchema(20)                     # adSchemaTables
    while not schema.EOF:
        try:
            if str(schema.Fields("TABLE_TYPE").Value) == "TABLE":
                out.append(str(schema.Fields("TABLE_NAME").Value))
        finally:
            schema.MoveNext()
    return out


def records(conn: Any, sql: str) -> List[Dict[str, Any]]:
    """执行 SELECT，返回行字典列表（列名原样保留，含空格/括号）。"""
    rs = conn.Execute(sql)[0]
    names = [str(rs.Fields(i).Name) for i in range(rs.Fields.Count)]
    rows: List[Dict[str, Any]] = []
    while not rs.EOF:
        rows.append({n: rs.Fields(n).Value for n in names})
        rs.MoveNext()
    return rows


def count(conn: Any, table: str) -> int:
    rows = records(conn, "SELECT COUNT(*) AS n FROM [%s]" % table)
    return int(rows[0]["n"]) if rows else 0


def close(conn: Any) -> None:
    try:
        conn.Close()
    except Exception:                               # noqa: BLE001
        pass


def module_spec(root: Optional[str] = None,
                table: Optional[str] = None) -> Dict[str, Any]:
    """从 `ace_plc.mdb` 取一条 PLC 模块规格（CODE/POINTS/TYPE/DESCRIPTION…）。"""
    path = plc_db(root)
    if not path:
        raise AeUnavailable("没有 ace_plc.mdb")
    conn = connect(path)
    try:
        names = tables(conn)
        chosen = table if table in names else None
        if not chosen:
            for n in names:
                if n.endswith("_Advanced_IO") or n.endswith("_IO"):
                    chosen = n
                    break
        if not chosen:
            chosen = names[0] if names else None
        if not chosen:
            raise AeUnavailable("ace_plc.mdb 没有表")
        rows = records(conn, "SELECT TOP 1 * FROM [%s]" % chosen)
        spec = dict(rows[0]) if rows else {}
        spec["_table"] = chosen
        spec["_db"] = path
        return spec
    finally:
        close(conn)

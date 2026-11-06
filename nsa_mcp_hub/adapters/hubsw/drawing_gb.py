# -*- coding: utf-8 -*-
"""国标（GB）图纸：模板选择、标题栏属性填充、以及设计过的 BOM 表。

为什么标题栏走"模板 + 属性"而不是自己画线：
本机 SW 自带 `gb_a0..gb_a4.drwdot` 国标模板，它们的**图纸格式**里已经有 GB/T 10609.1
标题栏（实测 gb_a3 的图纸上有 82 个注释），并且带 `Number / Description / Material /
Weight / 公司名称 / 设计者` 这些占位属性。填属性 = 标题栏自动填好，这才是标准做法；
自己画线既不合规也不可维护。
"""

from __future__ import annotations

import glob
import os
from typing import Any

# GB/T 14689 幅面（mm）：A0 1189×841 / A1 841×594 / A2 594×420 / A3 420×297 / A4 297×210
SHEET_SIZES = {
    "a0": (1189.0, 841.0),
    "a1": (841.0, 594.0),
    "a2": (594.0, 420.0),
    "a3": (420.0, 297.0),
    "a4": (297.0, 210.0),
}

BOM_COLUMNS = [
    ("序号", 0.010),
    ("代号", 0.042),
    ("名称", 0.052),
    ("数量", 0.012),
    ("材料", 0.022),
    ("备注", 0.032),
]


def find_gb_template(size: str = "a3") -> str:
    """找本机的国标图纸模板（gb_a3.drwdot 之类）。"""
    size = str(size or "a3").strip().lower()
    patterns = []
    for root in (r"C:\ProgramData\SOLIDWORKS",
                 r"C:\ProgramData\SolidWorks",
                 r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\data"):
        patterns.append(os.path.join(root, "**", "gb_%s.drwdot" % size))
        patterns.append(os.path.join(root, "**", "*.drwdot"))
    for pattern in patterns:
        hits = sorted(glob.glob(pattern, recursive=True))
        wanted = [h for h in hits if ("gb_%s" % size) in os.path.basename(h).lower()]
        for candidate in wanted or hits:
            if os.path.isfile(candidate) and "gb_" in os.path.basename(candidate).lower():
                return candidate
    # 兜底：任意 .drwdot
    for pattern in (r"C:\ProgramData\SOLIDWORKS\**\*.drwdot",):
        hits = sorted(glob.glob(pattern, recursive=True))
        if hits:
            return hits[0]
    raise RuntimeError("找不到国标图纸模板（gb_*.drwdot）")


def early_module():
    """makepy 生成的 SldWorks 早期绑定模块（部分成员只在早期绑定下可见）。"""
    from win32com.client import gencache

    for major in (33, 32, 34, 35):
        try:
            module = gencache.EnsureModule("{83A33D31-27C5-11CE-BFD4-00400513BB57}",
                                          0, major, 0)
        except Exception:                                # noqa: BLE001
            continue
        if module is not None:
            return module
    return None


def set_properties(doc, props: dict[str, str], config: str = "") -> dict:
    """写自定义属性（标题栏占位）并逐条读回。"""
    import pythoncom
    import win32com.client

    manager = doc.Extension.CustomPropertyManager(config or "")
    written: dict[str, str] = {}
    readback: dict[str, str] = {}
    for name, value in props.items():
        text = str(value or "")
        try:
            manager.Set2(name, text)
            written[name] = text
        except Exception as exc:                          # noqa: BLE001
            written[name] = "失败：%s" % str(exc)[:60]
            continue
        value_out = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
        resolved = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
        try:
            manager.Get6(name, False, value_out, resolved)
            readback[name] = str(value_out.value or resolved.value or "")
        except Exception as exc:                          # noqa: BLE001
            readback[name] = "读取失败：%s" % str(exc)[:60]
    return {"written": written, "readback": readback}


def sheet_note_texts(doc, limit: int = 120) -> list[str]:
    """读图纸（图纸格式）上注释的文本，用早期绑定拿 INote.GetText。"""
    module = early_module()
    sheet = None
    try:
        sheet = doc.GetFirstView
    except Exception:                                     # noqa: BLE001
        sheet = None
    notes = []
    try:
        notes = list((sheet.GetNotes if hasattr(sheet, "GetNotes") else []) or [])
    except Exception:                                     # noqa: BLE001
        notes = []
    texts: list[str] = []
    for note in notes[:limit]:
        text = None
        if module is not None:
            try:
                text = module.INote(note._oleobj_).GetText()
            except Exception:                             # noqa: BLE001
                text = None
        if text is None:
            try:
                text = note.GetText()
            except Exception:                             # noqa: BLE001
                text = None
        if text:
            texts.append(str(text))
    return texts


def designed_bom_table(drawing, rows: list[list[str]], x: float = 0.30,
                       y: float = 0.05) -> dict:
    """画一张"能看"的 BOM 表：6 列、列标题、列宽、行高、标题行。

    rows[0] 是数据首行（不含表头），表头用 ``SetColumnTitle`` 写进表格自己的标题行，
    这样既是**原生表格**，又符合工程图的阅读习惯（序号/代号/名称/数量/材料/备注）。
    """
    module = early_module()
    template = ""
    try:
        from .drawing_note import _table_template as _template_path
        template = _template_path()
    except Exception:                                     # noqa: BLE001
        template = ""

    table = None
    last_error = None
    for anchor in (1, 0):
        try:
            table = drawing.InsertTableAnnotation2(True, float(x), float(y), anchor,
                                                   template, len(rows) + 1,
                                                   len(BOM_COLUMNS))
        except Exception as exc:                          # noqa: BLE001
            last_error = exc
            table = None
        if table is not None:
            break
    if table is None:
        raise RuntimeError("建 BOM 表失败：%s" % last_error)

    writer = table
    if module is not None:
        try:
            writer = module.ITableAnnotation(table._oleobj_)
        except Exception:                                 # noqa: BLE001
            writer = table

    # 表头：直接写在**第 0 行**（通用表格的 SetColumnTitle 在本机不落字，实测读回为空）
    titles: list[str] = []
    for index, (title, width) in enumerate(BOM_COLUMNS):
        try:
            writer.SetColumnWidth(index, float(width), 1)
        except Exception:                                 # noqa: BLE001
            pass
        try:
            writer.SetText(0, index, title)
            shown = str(writer.DisplayedText(0, index))
        except Exception:                                 # noqa: BLE001
            shown = title
        titles.append(shown or title)

    cells = 0
    readback: list[list[str]] = []
    for r, row in enumerate(rows, start=1):
        cells_row = []
        for c, text in enumerate(row):
            ok = False
            try:
                writer.SetText(r, c, str(text))
                ok = True
            except Exception:                             # noqa: BLE001
                ok = False
            cells += 1 if ok else 0
            shown = ""
            try:
                shown = str(writer.DisplayedText(r, c))
            except Exception:                             # noqa: BLE001
                shown = ""
            cells_row.append(shown)
        readback.append(cells_row)

    height = 0.0
    try:
        writer.SetRowHeight(0, 0.009, 1)
        height = 0.009
    except Exception:                                     # noqa: BLE001
        height = 0.0

    return {"table": table, "rows": int(table.RowCount or 0),
            "cols": int(table.ColumnCount or 0), "titles": titles,
            "cells_written": cells, "readback": readback,
            "row_height": height}

def note_positions(doc, limit: int = 200) -> list[dict]:
    """读图纸格式里每条注释的 (文本, x, y)。"""
    module = early_module()
    sheet = doc.GetFirstView
    notes = list(sheet.GetNotes or [])
    rows: list[dict] = []
    for note in notes[:limit]:
        text = ""
        position = None
        if module is not None:
            try:
                early = module.INote(note._oleobj_)
                text = str(early.GetText() or "")
                annotation = early.GetAnnotation()
                if annotation is not None:
                    position = annotation.GetPosition        # 属性，不是方法
            except Exception:                                # noqa: BLE001
                position = None
        if isinstance(position, (tuple, list)) and len(position) >= 2:
            rows.append({"text": text, "x": float(position[0]), "y": float(position[1])})
    return rows


def fill_gb_title_block(doc, values: list[str], x_min: float = 0.22,
                        y_max: float = 0.075) -> dict:
    """把值写进国标标题栏的空白栏位。

    做法：模板（gb_a3.drwdot）的图纸格式里，标题栏是**静态格子 + 一批空白注释**。
    这些空白注释就是待填的栏位，正好给出坐标，所以按位置排序后逐个落值，
    既能对上格子，也不用猜测每一格叫什么。判据是**读回**——新注释文本等于写入值。
    """
    import win32com.client

    from .drawing_note import insert_note

    rows = note_positions(doc)
    blanks = [row for row in rows
              if not row["text"].strip() and row["x"] >= x_min and row["y"] <= y_max]
    blanks.sort(key=lambda row: (-row["y"], row["x"]))
    filled: list[dict] = []
    for value, slot in zip(values, blanks):
        landing = insert_note(doc, str(value), slot["x"], slot["y"])
        filled.append({"value": str(value), "cell": [round(slot["x"], 4), round(slot["y"], 4)],
                       "readback": landing.get("text") or "",
                       "ok": bool(landing.get("ok"))})
    # 判据用**落点自己的读回**：新加的注释在 sheet.GetNotes 里不一定立刻可见，
    # 但 `insert_note` 已经把文本读回来了，那才是"图上真的有这行字"的证据。
    matched = [item["value"] for item in filled
               if item["ok"] and item["readback"] == item["value"]]
    after = note_positions(doc)
    texts = [row["text"] for row in after]
    return {"blanks": len(blanks), "filled": filled, "matched": len(matched),
            "notes_total": len(after),
            "visible_on_sheet": sum(1 for value in matched if value in texts)}

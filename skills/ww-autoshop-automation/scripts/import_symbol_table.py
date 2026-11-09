#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 CSV 符号表批量写进 AutoShop 工程 —— 走符号表自带的「导入Excel」。

为什么不是逐格写：符号表网格默认只有 **19 个数据行**，`add_symbol(row=n)` 在 n>=19 时
不会建行，点击越界会**折回第 1 行反复改写**（返回值仍为 True）。见 references/pitfalls.md。

实测（2026-10-26，H3U 工程）：74 符号 -> 导入 -> 保存 -> 读 VarList.gdt，
74/74 命中，缺 0 多 0。

用法::

    python scripts/import_symbol_table.py --csv out\\symbols.csv --hcp D:\\work\\demo\\demo.hcp
    python scripts/import_symbol_table.py --csv s.csv --hcp p.hcp --no-save    # 只看结果

CSV 需含列：名称(符号) / 地址 / 注释。名称超过 8 字符会被 AutoShop 截断，本脚本先规范化
（截断 + 去重）并打印改名清单。

判据（脚本自己报）：
  * `symbols(source="file")` 行数与 CSV 一致、逐条存在
  * 可选 `--compile-check SYM1,SYM2` 再写一段引用这些符号的程序并编译
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import autoshopkit.app as A

NAME_MAX = 8
CMD_EXPORT_XLS = 33182
CMD_IMPORT_XLS = 33183
# 「另存为」的文件名框是 1001，「打开」是 1148；两者都藏在 ComboBoxEx32 → ComboBox → Edit 里
FILENAME_EDITS = (1001, 1148)


def load_csv(path: str) -> list[tuple[str, str, str]]:
    with open(path, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        out = []
        for row in reader:
            name = (row.get("名称") or row.get("符号") or row.get("symbol") or "").strip()
            addr = (row.get("地址") or row.get("address") or "").strip()
            note = (row.get("注释") or row.get("note") or "").strip()
            if name and addr:
                out.append((name, addr, note))
    return out


def normalise(rows: list[tuple[str, str, str]]) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """截到 8 字符并去重；返回 (rows, renamed)。"""
    used: set[str] = set()
    out: list[tuple[str, str, str]] = []
    renamed: list[tuple[str, str]] = []
    for name, addr, note in rows:
        old = name
        name = name[:NAME_MAX]
        k = 1
        base = name
        while name in used:
            k += 1
            name = base[: NAME_MAX - len(str(k))] + str(k)
        used.add(name)
        if name != old:
            renamed.append((old, name))
        out.append((name, addr, note))
    return out, renamed


def build_xls(rows: list[tuple[str, str, str]], path: str) -> None:
    import xlwt  # 延迟导入：只有导出/导入这条路径才需要

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Sheet1")
    for col, head in enumerate(("", "符号", "地址", "注释")):
        ws.write(0, col, head)
    for i, (name, addr, note) in enumerate(rows, 1):
        ws.write(i, 0, i)
        ws.write(i, 1, name)
        ws.write(i, 2, addr)
        ws.write(i, 3, note)
    wb.save(path)


def find_filename_edit(app, root) -> object | None:
    """递归找文件名输入框（cid 1001 / 1148）。"""
    best = None
    for c in app.dialog_controls(root):
        if c.cls == "Edit" and c.cid in FILENAME_EDITS:
            best = c
        try:
            sub = find_filename_edit(app, c.hwnd)
            if sub is not None:
                best = sub
        except Exception:  # noqa: BLE001 - 枚举失败就当没有
            pass
    return best


def type_path(app, dlg, path: str, wait: float = 5.0) -> bool:
    from autoshopkit import input as inp

    edit = None
    deadline = time.time() + wait
    while time.time() < deadline:
        edit = find_filename_edit(app, dlg)
        if edit is not None:
            break
        time.sleep(0.4)
    if edit is None:
        return False
    app.focus_window(edit.hwnd)
    time.sleep(0.3)
    inp.chord(["ctrl"], "a")
    time.sleep(0.2)
    inp.set_clipboard(path)
    time.sleep(0.3)
    inp.chord(["ctrl"], "v")
    time.sleep(0.7)
    inp.key("enter")
    return True


def accept_confirm(app, rounds: int = 4) -> None:
    """点掉「确定/是」类确认框。"""
    for _ in range(rounds):
        dialogs = app.dialogs()
        if not dialogs:
            return
        clicked = False
        for h in dialogs:
            for c in app.dialog_controls(h):
                if c.cls == "Button" and (c.text or "").startswith(("是", "确定", "OK")):
                    A.w.post(c.hwnd, A.w.BM_CLICK, 0, 0)
                    clicked = True
                    break
        if not clicked:
            return
        time.sleep(1.2)


def cancel_all(app) -> None:
    for h in app.dialogs():
        for c in app.dialog_controls(h):
            if c.cls == "Button" and (c.text or "").startswith("取消"):
                A.w.post(c.hwnd, A.w.BM_CLICK, 0, 0)
    time.sleep(0.5)


def main() -> int:
    ap = argparse.ArgumentParser(description="通过「导入Excel」批量写 AutoShop 符号表")
    ap.add_argument("--csv", required=True, help="符号表 CSV（名称/地址/注释）")
    ap.add_argument("--hcp", required=True, help="目标工程 .hcp（建议用副本）")
    ap.add_argument("--xls", default="", help="中间文件路径（默认放 CSV 同目录）")
    ap.add_argument("--no-save", action="store_true", help="导入后不保存工程")
    ap.add_argument("--compile-check", default="", help="逗号分隔的符号名，用它们写程序并编译")
    args = ap.parse_args()

    rows = load_csv(args.csv)
    if not rows:
        print("CSV 里没有有效行（需要 名称 + 地址）", file=sys.stderr)
        return 2
    rows, renamed = normalise(rows)
    print(f"待写入 {len(rows)} 条；改名 {len(renamed)} 条")
    for old, new in renamed[:10]:
        print(f"  {old} -> {new}")

    xls = args.xls or os.path.join(os.path.dirname(os.path.abspath(args.csv)), "sym_import.xls")
    build_xls(rows, xls)
    print(f"中间文件 {xls} ({os.path.getsize(xls)} B)")

    from autoshopkit import AutoShop

    existing = AutoShop.attach()
    if existing:
        existing.close(save=False)
        time.sleep(2.0)
    app = AutoShop.launch(project=args.hcp, wait=120.0)
    try:
        app.tree_open("符号表")
        time.sleep(1.5)
        grid = app.symbol_grid()
        app.activate()
        if grid:
            app.focus_window(grid.hwnd)
        time.sleep(0.4)

        A.w.post(app.frame, A.w.WM_COMMAND, CMD_IMPORT_XLS)
        time.sleep(2.2)
        dialogs = app.dialogs()
        if not dialogs:
            print("「导入Excel」没有弹出文件对话框", file=sys.stderr)
            return 3
        if not type_path(app, dialogs[0], xls):
            cancel_all(app)
            print("找不到文件名输入框(cid 1001/1148)，已取消", file=sys.stderr)
            return 4
        time.sleep(3.0)
        accept_confirm(app)
        if app.dialogs():
            cancel_all(app)
            print("导入未完成：对话框仍在", file=sys.stderr)
            return 5

        if not args.no_save:
            app.cmd("save_project")
            time.sleep(3.5)

        got = app.symbols(source="file")
        pairs = [(str(r.get("symbol", "")).strip(), str(r.get("address", "")).strip()) for r in got]
        expected = [(n, a) for n, a, _ in rows]
        missing = [p for p in expected if p not in pairs]
        extra = [p for p in pairs if p not in expected]
        print(f"回读 {len(pairs)} 行；缺 {len(missing)}，多 {len(extra)}")
        for p in missing[:5]:
            print("  缺:", p)

        ok = not missing and not extra
        if ok and args.compile_check:
            syms = [s.strip() for s in args.compile_check.split(",") if s.strip()]
            if len(syms) >= 2:
                body = "LD %s\nAND %s\nOUT Y0\n" % (syms[0], syms[1])
                app.activate()
                time.sleep(0.3)
                app.activate_document("MAIN")
                time.sleep(0.6)
                try:
                    app.set_program_il(body)
                    app.view_ladder()
                    time.sleep(0.7)
                    compiled, lines = app.compile()
                    stats = [l for l in lines if "统计" in l]
                    print("编译:", compiled, stats[-1:] or lines[-1:])
                    ok = ok and bool(compiled)
                except Exception as exc:  # noqa: BLE001
                    print("编译检查失败:", type(exc).__name__, exc, file=sys.stderr)
                    ok = False
        return 0 if ok else 1
    finally:
        app.close(save=False)


if __name__ == "__main__":
    sys.exit(main())

import pathlib

p = pathlib.Path(r"D:\bililive\gxkit\docs\VERIFY.md")
t = p.read_text(encoding="utf-8")
t = t.replace("25 条能力全过", "25 条能力全过")
anchor = "| 2026-10-23 | **23/23（v0.10，同一份代码第二次）** | 3060.8 s |"
add = ("\n| 2026-10-23 | **25/25（v0.11，含 inspect.programs / project.diff）** | 3272.6 s |")
if anchor in t and "25/25（v0.11，含" not in t:
    t = t.replace(anchor, anchor + add, 1)
section = """

## v0.11 收尾四件事

| 项 | 结果 |
|---|---|
| 模板依赖 | 首次复制到 `%LOCALAPPDATA%/gxkit/skeleton.xml` 并记 sha256，指纹变化自动重建；`GXKIT_TEMPLATE` 可绕开安装目录 |
| 手写骨架 | `templates/base.xml` 能导入程序/标签/全局结构体；**局部标签不落地**（已排除 5 个因素），记入 UNSUPPORTED |
| 一条命令 | `gxkit apply --xml x.xml [--dry]`：预检 → 导入 → 编译 → 存盘 → 报告（实测 142.7 s 通过） |
| 待办 | `docs/EXPAND_BACKLOG.md`：往外扩按预估用时降序排好（LAD 8–16h → iQ-R 4–8h → …） |
"""
if "## v0.11 收尾四件事" not in t:
    t = t.rstrip("\n") + section
p.write_text(t, encoding="utf-8")
print("VERIFY updated")

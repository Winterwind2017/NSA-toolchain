import pathlib

p = pathlib.Path(r"D:\bililive\gxkit\docs\STATUS.md")
t = p.read_text(encoding="utf-8")
t = t.replace("`apply` 会打印并写出 `apply_report.json`：", "`apply` 会打印并写出报告文件 apply_report.json：")
p.write_text(t, encoding="utf-8")
print("fixed")

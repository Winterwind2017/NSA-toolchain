import pathlib

p = pathlib.Path(r"D:\bililive\ww-gxworks-automation\SKILL.md")
t = p.read_text(encoding="utf-8")
t = t.replace("`apply_report.json`", "apply_report.json")
p.write_text(t, encoding="utf-8")
print("unquoted:", "`apply_report.json`" not in t)

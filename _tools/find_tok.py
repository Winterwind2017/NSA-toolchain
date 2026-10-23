import pathlib
import re

t = pathlib.Path(r"D:\bililive\gxkit\docs\STATUS.md").read_text(encoding="utf-8")
tokens = re.findall(r"`([a-z][a-z0-9_.]*)`", t)
print("tokens:", tokens)
i = t.find("apply_report")
print("ctx:", t[max(0, i - 100):i + 60].replace("\n", " | "))

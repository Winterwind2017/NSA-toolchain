"""真机链路验证：采基线 → 制造漂移 → 检出 → 还原 → 干净退出。

只改一个无害的系统变量（MEASUREMENT，单位制），改完立刻还原。
不写图形、不存盘。
"""

import json
import subprocess
import sys

PY = r"D:\bililive\Solidworks-MCP-Server\.venv\Scripts\python.exe"
ENV = {"PYTHONPATH": r"D:\bililive\acadkit\src", "PYTHONIOENCODING": "utf-8"}


def run(*args):
    p = subprocess.run([PY, "-m", "acadkit.cli.main", *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**__import__("os").environ, **ENV})
    return p.returncode, (p.stdout or "") + (p.stderr or "")


print("=== 1) 采基线 ===")
rc, out = run("env-baseline")
print(out.strip().splitlines()[0] if out.strip() else "(no output)")
print("rc =", rc)

print("\n=== 2) 基线后 status（应 与基线一致 OK）===")
rc, out = run("status")
for line in out.splitlines():
    if "基线" in line or "结论" in line:
        print("   ", line.strip())
print("rc =", rc)

print("\n=== 3) 制造漂移：MEASUREMENT 1→0 ===")
from win32com.client import dynamic
app = dynamic.Dispatch("AutoCAD.Application")   # 已在运行，这里只是附加
doc = app.ActiveDocument
old = doc.GetVariable("MEASUREMENT")
doc.SetVariable("MEASUREMENT", 0)
print("   MEASUREMENT: %s → %s" % (old, doc.GetVariable("MEASUREMENT")))

print("\n=== 4) env-check（应检出 1 项漂移，rc=5）===")
rc, out = run("env-check")
print("   " + "\n   ".join(out.strip().splitlines()[:4]))
print("rc =", rc)

print("\n=== 5) 还原 ===")
doc.SetVariable("MEASUREMENT", old)
print("   MEASUREMENT 还原为", doc.GetVariable("MEASUREMENT"))

print("\n=== 6) env-check 再跑（应干净，rc=0）===")
rc, out = run("env-check")
print("   " + out.strip().splitlines()[0] if out.strip() else "   (none)")
print("rc =", rc)

print("\n=== 7) 干净退出 ===")
sys.path.insert(0, r"D:\bililive\acadkit\src")
from acadkit.core import com
res = com.clean_quit(app)
print("   clean_quit:", json.dumps(res, ensure_ascii=False))

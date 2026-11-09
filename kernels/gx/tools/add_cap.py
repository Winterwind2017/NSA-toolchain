"""安全新增一条能力：动作函数 + ACTIONS 键 + Cap 条目，并硬检查 cap id 唯一。

用法：python tools/add_cap.py spec.json

spec.json：
{
  "action_key": "project_check",
  "func_name": "project_check",
  "func_file": "snippet.py",
  "cap": "    Cap(\"project.check\", \"project\", \"工程校验\", \"project_check\", \"L1\", params={}, expect={...}),\n"
}
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "src" / "gxkit" / "actions.py"
CAPS = ROOT / "src" / "gxkit" / "caps.py"
FUNC_ANCHOR = "\nACTIONS = {"
DICT_ANCHOR = "ACTIONS = {\n"
CAPS_ANCHOR = "CAPS: tuple[Cap, ...] = (\n"


def main(path: str) -> int:
    spec = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    key, fname = spec["action_key"], spec["func_name"]
    func_src = pathlib.Path(spec["func_file"]).read_text(encoding="utf-8")
    cap_src = spec["cap"]
    if not cap_src.endswith("\n"):
        cap_src += "\n"
    if not func_src.lstrip().startswith("def "):
        raise SystemExit("func_file 必须是纯函数源码（以 def 开头）")

    m = re.search(r'Cap\(\s*"([^"]+)"', cap_src)
    if not m:
        raise SystemExit('cap 片段里找不到 Cap("<id>", ...)')
    cid = m.group(1)
    if not re.match(r"^[a-z][a-z0-9_.]*$", cid):
        raise SystemExit("cap id 格式不对（应是小写点分）：%s" % cid)
    caps_now = CAPS.read_text(encoding="utf-8")
    if 'Cap("%s"' % cid in caps_now:
        raise SystemExit("cap id 已存在，拒绝重复登记：%s" % cid)

    t = ACTIONS.read_text(encoding="utf-8")
    if "def %s(" % fname in t:
        raise SystemExit("动作函数已存在：%s" % fname)
    if '"%s":' % key in t:
        raise SystemExit("ACTIONS 键已存在：%s" % key)
    if FUNC_ANCHOR not in t or DICT_ANCHOR not in t:
        raise SystemExit("找不到 ACTIONS 锚点，拒绝修改")
    body = func_src if func_src.endswith("\n\n") else func_src.rstrip("\n") + "\n\n"
    t = t.replace(FUNC_ANCHOR, "\n" + body + "ACTIONS = {", 1)
    t = t.replace(DICT_ANCHOR, DICT_ANCHOR + '    "%s": %s,\n' % (key, fname), 1)
    ACTIONS.write_text(t, encoding="utf-8")

    s = caps_now
    if CAPS_ANCHOR not in s:
        raise SystemExit("找不到 CAPS 锚点，拒绝修改")
    s = s.replace(CAPS_ANCHOR, CAPS_ANCHOR + cap_src, 1)
    if s.count('Cap("%s"' % cid) != 1:
        raise SystemExit("写入后 cap id 不唯一：%s" % cid)
    CAPS.write_text(s, encoding="utf-8")

    py = sys.executable
    for cmd in ([py, "-m", "py_compile", str(ACTIONS)],
                [py, "-m", "gxkit", "selftest"]):
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print(r.stdout.strip())
        if r.returncode != 0:
            print(r.stderr.strip()[-600:])
            print("失败：请检查 spec（代码已写入，需手工回滚）")
            return r.returncode
    print("已新增：%s -> %s()" % (key, fname))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

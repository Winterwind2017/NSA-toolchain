"""安全地新增一条能力（动作函数 + ACTIONS 键 + Cap 条目）。

背景：本项目历史上 5 次因为"从函数开头删到下一个 def / 删到文件尾"把 ACTIONS
字典整段吞掉，导致全会话 0 条。这个工具用**固定锚点**插入，避免再犯：

- 函数体插到 `\\nACTIONS = {` 之前
- 字典键插到 `ACTIONS = {\\n` 之后
- Cap 条目插到 `CAPS: tuple[Cap, ...] = (\\n` 之后

用法：
    python tools/add_cap.py spec.json

spec.json：
{
  "action_key": "surface_through_curves",
  "func_name": "surface_through_curves",
  "func_file": "snippet.py",            # 只含 def ... 的纯函数源码
  "cap": "    Cap(\"surface.through_curves\", ...),\n"
}
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "src" / "nxkit" / "runtime" / "actions.py"
CAPS = ROOT / "src" / "nxkit" / "caps.py"
FUNC_ANCHOR = "\nACTIONS = {"
DICT_ANCHOR = "ACTIONS = {\n"
CAPS_ANCHOR = "CAPS: tuple[Cap, ...] = (\n"


def main(path: str) -> int:
    spec = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    key = spec["action_key"]
    fname = spec["func_name"]
    func_src = pathlib.Path(spec["func_file"]).read_text(encoding="utf-8")
    cap_src = spec["cap"]
    if not cap_src.endswith("\n"):
        cap_src += "\n"

    if not func_src.lstrip().startswith("def "):
        raise SystemExit("func_file 必须是纯函数源码（以 def 开头）")

    t = ACTIONS.read_text(encoding="utf-8")
    if f"def {fname}(" in t:
        raise SystemExit(f"动作函数已存在：{fname}")
    if f'"{key}":' in t:
        raise SystemExit(f"ACTIONS 键已存在：{key}")
    if FUNC_ANCHOR not in t or DICT_ANCHOR not in t:
        raise SystemExit("找不到 ACTIONS 锚点，拒绝修改")
    body = func_src if func_src.endswith("\n\n") else func_src.rstrip("\n") + "\n\n"
    t = t.replace(FUNC_ANCHOR, "\n" + body + "ACTIONS = {", 1)
    t = t.replace(DICT_ANCHOR, DICT_ANCHOR + f'    "{key}": {fname},\n', 1)
    ACTIONS.write_text(t, encoding="utf-8")

    s = CAPS.read_text(encoding="utf-8")
    if CAPS_ANCHOR not in s:
        raise SystemExit("找不到 CAPS 锚点，拒绝修改")
    s = s.replace(CAPS_ANCHOR, CAPS_ANCHOR + cap_src, 1)
    CAPS.write_text(s, encoding="utf-8")

    py = sys.executable
    for cmd in ([py, "-m", "py_compile", str(ACTIONS)],
                [py, "-m", "nxkit", "selftest"]):
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print(r.stdout.strip())
        if r.returncode != 0:
            print(r.stderr.strip()[-800:])
            print("失败：请检查 spec（代码已写入，需手工回滚）")
            return r.returncode
    print(f"已新增：{key} -> {fname}()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

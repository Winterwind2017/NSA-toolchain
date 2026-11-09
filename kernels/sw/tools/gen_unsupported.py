"""从 registry 重新生成 docs/UNSUPPORTED.md 的三个状态章节。

为什么要有这个脚本：`UNSUPPORTED.md` 曾出现"和 registry 脱节"的问题——
里面还列着早已转正的 `sw_revolve` / `sw_chamfer` / `sw_fillet`，
而文档的目的恰恰是"别重复试"。手工维护必然漂移，所以改成生成。

用法：

    python tools/gen_unsupported.py          # 重写文档
    python tools/gen_unsupported.py --check  # 只校验数字是否一致（CI 用）

章节结构：

* `## broken`      —— registry 里 status=broken
* `## unstable`    —— registry 里 status=unstable
* `## unverified`  —— registry 里 status=unverified

每条形如：

    ### `sw_xxx`（category）
    - API：`...`
    - 结论：<registry 里的 note>

文件头（判定口径、指向 SILENT_FAILURES 的那段）与尾部"勘误"章节保持人工撰写，
本脚本只替换三个状态章节。
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from swkit.registry import REGISTRY  # noqa: E402

DOC = os.path.join(ROOT, "docs", "UNSUPPORTED.md")

HEADER = """# UNSUPPORTED —— 用不了的东西，以及为什么

> 这个文件的存在意义：**避免下一轮再去试同一件事**。
> 每条都写了"试过什么、结果是什么、为什么判定不行"。

判定口径：

- `broken` —— 有明确证伪依据（类型库无该方法 / 参数横扫全失败）
- `unstable` —— 曾成功，但会挂起/崩溃，或不具备可构造的判据

> 「调用返回成功、几何量却不动」这一类（最危险，容易被误判成成功）统一收录在
> [`SILENT_FAILURES.md`](SILENT_FAILURES.md)：逐项证据、共性教训、以及将来可用来复核的测试清单。

> **本文件的三个状态章节由 `tools/gen_unsupported.py` 从 `src/swkit/registry.py` 生成，
> 请勿手改**；改结论请改 registry 的 note，再重跑该脚本。
> `tests/test_offline.py::test_unsupported_doc_matches_registry` 会校验两者一致。

---
"""

ORDER = ("broken", "unstable", "unverified")
TITLES = {
    "broken": "broken —— 有明确证伪依据",
    "unstable": "unstable —— 不进自动回归",
    "unverified": "unverified —— 已登记但没打通",
}


def _entries(status: str) -> list:
    return sorted((e for e in REGISTRY.values() if e.status == status),
                  key=lambda e: e.name)


def render() -> str:
    parts = [HEADER]
    for status in ORDER:
        items = _entries(status)
        parts.append("\n## %s（%d 条）\n" % (TITLES[status], len(items)))
        if not items:
            parts.append("\n_（无）_\n")
            continue
        for e in items:
            note = (e.note or "").strip() or "（registry 未写结论）"
            parts.append("\n### `%s`（%s）\n\n- API：`%s`\n- 结论：%s\n"
                         % (e.name, e.group, e.api or "—", note))
    parts.append("\n---\n\n## 计数校验\n\n")
    counts = {s: len(_entries(s)) for s in ORDER}
    parts.append("| 状态 | 条数 |\n|---|---|\n")
    for s in ORDER:
        parts.append("| `%s` | %d |\n" % (s, counts[s]))
    parts.append("\n> 与 `swkit.registry.summary()` 一致；不一致时离线测试会失败。\n")
    # 人工维护的补充笔记（不随 registry 生成）
    notes = os.path.join(ROOT, "docs", "UNSUPPORTED.notes.md")
    if os.path.isfile(notes):
        with open(notes, encoding="utf-8") as fh:
            parts.append("\n---\n\n" + fh.read().strip() + "\n")
    return "".join(parts)


def main() -> int:
    check = "--check" in sys.argv
    text = render()
    old = ""
    if os.path.isfile(DOC):
        with open(DOC, encoding="utf-8") as fh:
            old = fh.read()
    counts = {s: len(_entries(s)) for s in ORDER}
    if check:
        ok = old.strip() == text.strip()
        print("registry:", counts)
        print("文档一致:" , ok)
        return 0 if ok else 4
    with open(DOC, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    print("已重写 %s" % DOC)
    print("registry:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

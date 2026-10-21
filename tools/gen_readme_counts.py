"""从 registry / audit / 代码结构重新生成 README 里的数字块。

为什么要有这个脚本：README 里的数字曾出现**多处漂移**——
`53 条 verified 配方`、`2 条不稳`、`23 条超出上游`、`111/27/44`
全是旧值，而代码早就变成 150 verified / 3 unstable / 125 covered。

数据来源（都是单一真相）：

* `swkit.registry.summary()` —— verified / unstable / unverified / broken / implemented
* `docs/UPSTREAM_AUDIT.md`   —— 上游 188 条的去向表（由 `tools/audit_upstream.py` 生成）
* 代码结构                   —— MCP 工具数、CLI 子命令数、回归套件数

用法：

    python tools/gen_readme_counts.py          # 重写 README 的数字块
    python tools/gen_readme_counts.py --check  # 只校验（CI / 测试用）

README 里用 HTML 注释标记区块：

    <!-- gen:tier_a:BEGIN -->   ... <!-- gen:tier_a:END -->
    <!-- gen:recipes:BEGIN -->  ... <!-- gen:recipes:END -->
    <!-- gen:unstable:BEGIN --> ... <!-- gen:unstable:END -->
    <!-- gen:upstream:BEGIN --> ... <!-- gen:upstream:END -->
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from swkit.registry import REGISTRY, summary  # noqa: E402

README = os.path.join(ROOT, "README.md")
AUDIT = os.path.join(ROOT, "docs", "UPSTREAM_AUDIT.md")


# ── 数据采集 ────────────────────────────────────────────────────────
def _audit_counts() -> dict:
    """从 UPSTREAM_AUDIT.md 的汇总表里读上游 188 条的去向。"""
    with open(AUDIT, encoding="utf-8") as fh:
        text = fh.read()
    out = {}
    labels = {
        "已覆盖": "covered",
        "已判死": "dead",
        "已知不稳": "unstable",
        "未达可用": "unusable",
        "未复核": "unchecked",
    }
    for label, key in labels.items():
        m = re.search(r"\|\s*%s[^|]*\|\s*(\d+)\s*\|" % label, text)
        if m:
            out[key] = int(m.group(1))
    m = re.search(r"本仓库超出上游的能力（(\d+)\s*条）", text)
    if m:
        out["beyond"] = int(m.group(1))
    return out


def _code_counts() -> dict:
    import swkit.mcp.server as M
    from swkit.cli.main import build_parser
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from run_all import _suites

    return {
        "mcp": len([n for n in dir(M) if n.startswith("sw_")]),
        "cli": len([a for a in build_parser()._actions
                    if getattr(a, "choices", None)][0].choices),
        "suites": len(_suites()),
    }


# ── 渲染 ────────────────────────────────────────────────────────────
def render_fragments() -> dict:
    s = summary()
    code = _code_counts()
    audit = _audit_counts()
    verified_non_meta = len([e for e in REGISTRY.values()
                             if e.status == "verified" and e.group != "meta"])
    unstable_names = sorted(e.name for e in REGISTRY.values()
                            if e.status == "unstable")
    own = s["verified"] - audit.get("covered", 0)

    tier_a = (
        "> **本仓库已编码、现在就能经 CLI/MCP 调**。当前 **%d 已验证 / %d 已知不稳 / "
        "%d 已登记未打通**。\n"
        "> 用 `swkit registry --implemented` 只看能直接用的那批"
        "（implemented %d vs verified %d，%s）。"
        % (s["verified"], s["unstable"], s["unverified"],
           s["implemented"], s["verified"],
           "相等" if s["implemented"] == s["verified"] else "不等")
    )

    recipes = (
        "外加 registry 里 **%d 条 verified 配方**（不含元数据类；"
        "特征 / 草图 / 出图 / 装配 / 仿真 / 元数据），\n"
        "每条都带 API 名与"
        "\u201c用什么数字证明它成了\u201d。\n"
        "> 另有 MCP **%d** 工具、CLI **%d** 子命令、**%d** 个回归套件。"
        % (verified_non_meta, code["mcp"], code["cli"], code["suites"])
    )

    unstable = (
        "另有 %d 条**不稳**（%s），\n不进自动回归。"
        "详见 [`docs/UNSUPPORTED.md`](docs/UNSUPPORTED.md)。"
        % (s["unstable"],
           "、".join("`%s`" % n for n in unstable_names) or "无")
    )

    table = [
        "| 归宿 | 数量 |",
        "|---|---|",
        "| 已覆盖（本仓库有实现 + 真机判据） | %d |" % audit.get("covered", 0),
        "| 已判死（调用不存在/废弃 API，或实测不可用） | %d |" % audit.get("dead", 0),
        "| 已知不稳（不进回归） | %d |" % audit.get("unstable", 0),
        "| 未达可用（已登记但没打通） | %d |" % audit.get("unusable", 0),
        "| **未复核（待办）** | %d |" % audit.get("unchecked", 0),
        "",
        "外加本仓库**超出上游**的 %d 条（仿真/运动/元数据、以及上游根本没有的 "
        "`sw_cut_extrude`）。" % audit.get("beyond", 0),
        "",
        "> **两层数字别混淆**：",
        "> * **上游 188 条** → 已覆盖 **%d** / 未达可用 **%d** / 未复核 **%d**"
        "（其余判死 %d、不稳 %d）"
        % (audit.get("covered", 0), audit.get("unusable", 0),
           audit.get("unchecked", 0), audit.get("dead", 0),
           audit.get("unstable", 0)),
        "> * **registry 的 verified %d** = 上游同名 **%d** + 本仓库自有 **%d**"
        "（另有 %d 项已知不稳）"
        % (s["verified"], audit.get("covered", 0), own, s["unstable"]),
        ">",
        "> 逐条\u201c卡在哪里\u201d见 [`docs/UNSUPPORTED.md`](docs/UNSUPPORTED.md) "
        "的 unverified 分类表",
        "> （参数未定 / 假成功 / 夹具造不出 / 枚举不存在 / 方程接口 / 破坏性不主动做）。",
        "",
        "未复核的 %d 条已按能力族登记在审计表里，后续按族继续复核。"
        % audit.get("unchecked", 0),
    ]
    upstream = "\n".join(table) + "\n"
    return {"tier_a": tier_a, "recipes": recipes,
            "unstable": unstable, "upstream": upstream}


def apply(text: str, frags: dict) -> str:
    for key, body in frags.items():
        begin = "<!-- gen:%s:BEGIN -->" % key
        end = "<!-- gen:%s:END -->" % key
        i, j = text.find(begin), text.find(end)
        if i < 0 or j < 0:
            raise SystemExit("README 缺少标记 %s / %s" % (begin, end))
        text = text[:i] + begin + "\n" + body.rstrip() + "\n" + text[j:]
    return text


def main() -> int:
    check = "--check" in sys.argv
    with open(README, encoding="utf-8") as fh:
        text = fh.read()
    frags = render_fragments()
    new = apply(text, frags)
    if check:
        same = new.strip() == text.strip()
        print("README 一致:", same)
        if not same:
            print("（跑 python tools/gen_readme_counts.py 重生成）")
        return 0 if same else 4
    with open(README, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    print("已重写 README 数字块")
    for k in frags:
        print("  ", k, "->", frags[k].splitlines()[0][:70])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

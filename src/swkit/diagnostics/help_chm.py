"""swkit.diagnostics.help_chm —— 官方帮助检索（先查文档，再猜参数）

`SldWorks` 的 COM 帮助（`sldworksapi.chm`）里有**全部官方示例**，以及每个方法 Remarks
里那张"选择标记"表 —— 本项目最后两个硬骨头就是靠它 10 分钟解决的，而此前已经瞎试两轮。

用法：

    python -m swkit.diagnostics.help_chm decompile        # 解包到默认目录（一次性）
    python -m swkit.diagnostics.help_chm read Mirror_Components_II_Example_VB
    python -m swkit.diagnostics.help_chm read IFeatureManager~FeatureLinearPattern5

默认解包目录：`%LOCALAPPDATA%\\swkit\\chm`（可用 `SWKIT_CHM_DIR` 覆盖）。
CHM 自带路径可用 `SWKIT_CHM` 覆盖；一般用 SW 安装目录自带的 `sldworksapi.chm`。
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import sys
from typing import List, Optional

__all__ = ["default_chm", "default_out", "decompile", "read_topics", "search_titles"]

_DEFAULT_CHM_CANDIDATES = (
    r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworksapi.chm",
)


def default_chm() -> str:
    env = os.environ.get("SWKIT_CHM")
    if env:
        return env
    for cand in _DEFAULT_CHM_CANDIDATES:
        if os.path.exists(cand):
            return cand
    return _DEFAULT_CHM_CANDIDATES[0]


def default_out() -> str:
    env = os.environ.get("SWKIT_CHM_DIR")
    if env:
        return env
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "swkit", "chm")


def decompile(chm: Optional[str] = None, out_dir: Optional[str] = None) -> str:
    """用 `hh.exe -decompile` 解包；返回输出目录。已解包过则直接返回。"""
    chm = chm or default_chm()
    out_dir = out_dir or default_out()
    if not os.path.exists(chm):
        raise FileNotFoundError("找不到 CHM：%s（设 SWKIT_CHM 指向它）" % chm)
    os.makedirs(out_dir, exist_ok=True)
    existing = [n for n in os.listdir(out_dir) if n.lower().endswith(".htm")]
    if len(existing) > 100:
        return out_dir
    hh = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "hh.exe")
    subprocess.run([hh, "-decompile", out_dir, chm], check=True,
                   stdin=subprocess.DEVNULL)
    return out_dir


def _strip_html(path: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8", "gbk", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            if text.count("\ufffd") < 50:
                break
        except Exception:
            continue
    else:
        text = raw.decode("utf-8", "replace")
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|tr|li|h[1-6]|pre|table)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out: List[str] = []
    for ln in lines:
        if ln:
            out.append(ln)
        elif out and out[-1] != "":
            out.append("")
    return "\n".join(out)


def search_titles(*fragments: str, out_dir: Optional[str] = None) -> List[str]:
    """按文件名片段（不区分大小写、多段取交集）找帮助页。"""
    out_dir = out_dir or default_out()
    keys = [f.lower() for f in fragments]
    names = []
    for name in os.listdir(out_dir):
        if not name.lower().endswith((".htm", ".html")):
            continue
        if all(k in name.lower() for k in keys):
            names.append(name)
    return sorted(names)


def read_topics(*fragments: str, out_dir: Optional[str] = None,
                limit: int = 3) -> str:
    """读取匹配的帮助页正文（最多 `limit` 页，避免刷屏）。"""
    out_dir = out_dir or default_out()
    names = search_titles(*fragments, out_dir=out_dir)[:limit]
    if not names:
        return "没有匹配的帮助页（先跑 decompile，或换关键词）"
    chunks = []
    for name in names:
        chunks.append("=" * 90)
        chunks.append("## " + name)
        chunks.append("=" * 90)
        chunks.append(_strip_html(os.path.join(out_dir, name)))
    return "\n".join(chunks)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "decompile":
        print(decompile())
        return 0
    if cmd == "read":
        print(read_topics(*rest))
        return 0
    if cmd == "find":
        for name in search_titles(*rest):
            print(name)
        return 0
    print("未知子命令：%s" % cmd)
    return 2


if __name__ == "__main__":      # pragma: no cover
    raise SystemExit(main())

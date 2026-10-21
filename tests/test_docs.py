#!/usr/bin/env python3
"""文档一致性：README 计数 / UNSUPPORTED / 能力表 / registry 自检。

这些检查不需要 AutoCAD，但能防止"代码改了、文档没改"的漂移。
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from acadkit import caps, registry                        # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))


def test_registry_valid() -> None:
    assert not registry.validate(registry.load())


def test_caps_cover_most_of_registry() -> None:
    known = {c["id"] for c in registry.load()["capabilities"]}
    covered = {c.id for c in caps.CAPS} & known
    # 内核必须覆盖所有 verified 的能力（负例不在 registry 里）
    verified = {c["id"] for c in registry.load()["capabilities"]
                if c["status"] == "verified"}
    missing = sorted(verified - covered)
    assert not missing, "verified 但内核没实现：%r" % missing


def test_readme_counts_block_is_fresh() -> None:
    import gen_readme_counts as gen

    readme = os.path.join(ROOT, "README.md")
    with open(readme, encoding="utf-8") as fh:
        text = fh.read()
    assert gen.BEGIN in text and gen.END in text, "README 缺少生成标记"
    assert gen.counts_block() in text, "README 计数块过期（跑 tools/gen_readme_counts.py）"


def test_capabilities_doc_is_fresh() -> None:
    import gen_readme_counts as gen

    path = os.path.join(ROOT, "docs", "CAPABILITIES.md")
    assert os.path.isfile(path), "缺 docs/CAPABILITIES.md"
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == gen.caps_doc(), "CAPABILITIES.md 过期"


def test_unsupported_doc_is_fresh() -> None:
    import gen_unsupported as gen

    path = os.path.join(ROOT, "docs", "UNSUPPORTED.md")
    assert os.path.isfile(path), "缺 docs/UNSUPPORTED.md"
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == gen.render(), "UNSUPPORTED.md 过期"


def test_dead_and_external_have_reasons() -> None:
    for c in registry.load()["capabilities"]:
        if c["status"] in ("dead", "external"):
            assert str(c.get("judge") or "").strip(), \
                "%s 是 %s 但没写原因" % (c["id"], c["status"])


def test_every_cap_has_a_level_and_family() -> None:
    for cap in caps.CAPS:
        assert cap.level, "%s 缺 level" % cap.id
        assert cap.family, "%s 缺 family" % cap.id
        assert callable(cap.build) and callable(cap.judge)

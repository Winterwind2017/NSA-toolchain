#!/usr/bin/env python3
"""新增三份报表的一致性检查（不需要 AutoCAD）。

    docs/PARITY.md      必须与 gen_parity.render() 完全一致
    docs/GAPS.md        必须与 gen_gaps.render() 完全一致
    docs/ALPHA_GATE.md  是"某次真机运行"的记录，不比对内容，只查结构：
                        5 条工作流 id 都在、有结果表、有复跑命令
    docs/registry.yaml  不能有"字符数组 backend / 双重引号"这两类损坏
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gen_backlog                                 # noqa: E402
import gen_cadcraft_mine                           # noqa: E402
import gen_gaps                                    # noqa: E402
import gen_parity                                  # noqa: E402
import fix_registry_quoting as fixq                # noqa: E402


def test_parity_doc_is_fresh() -> None:
    path = os.path.join(ROOT, "docs", "PARITY.md")
    assert os.path.isfile(path), "缺 docs/PARITY.md（跑 tools/gen_parity.py）"
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == gen_parity.render(), "PARITY.md 过期"


def test_gaps_doc_is_fresh() -> None:
    path = os.path.join(ROOT, "docs", "GAPS.md")
    assert os.path.isfile(path), "缺 docs/GAPS.md（跑 tools/gen_gaps.py）"
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == gen_gaps.render(), "GAPS.md 过期"


def test_gaps_meta_covers_every_dead_cap() -> None:
    """registry 的每条 dead 都必须进缺口账本（漏了就排不进预算）。"""
    rows = gen_gaps.build_rows()
    ids = {r["id"] for r in rows if r["kind"] == "dead"}
    from acadkit import registry
    dead = {c["id"] for c in registry.load()["capabilities"] if c["status"] == "dead"}
    assert dead == ids, "dead 与 gaps_meta 不一致：%r" % (dead ^ ids)


def test_gaps_scores_in_range() -> None:
    for r in gen_gaps.build_rows():
        assert 1 <= r["impact"] <= 5, "%s 的影响分越界：%r" % (r["id"], r["impact"])
        assert r["hours"] >= 0, "%s 的工时是负数" % r["id"]
        assert str(r["unblock"]).strip(), "%s 没写解锁条件" % r["id"]


def test_alpha_gate_doc_structure() -> None:
    path = os.path.join(ROOT, "docs", "ALPHA_GATE.md")
    assert os.path.isfile(path), "缺 docs/ALPHA_GATE.md（跑 tools/alpha_gate.py）"
    import alpha_gate
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for wf in alpha_gate.WORKFLOWS:
        assert "| %s |" % wf["id"] in text, "ALPHA_GATE.md 缺工作流 %s" % wf["id"]
    assert "通过" in text, "ALPHA_GATE.md 缺结果汇总"
    assert "python tools/alpha_gate.py" in text, "ALPHA_GATE.md 缺复跑命令"


def test_registry_has_no_writer_damage() -> None:
    """防止再次被写坏：字符数组 backend / 双重引号。"""
    path = os.path.join(ROOT, "docs", "registry.yaml")
    with open(path, encoding="utf-8") as fh:
        bad_backend, bad_quoted = fixq.count_damage(fh.read())
    assert bad_backend == 0, "registry.yaml 出现 %d 处 backend 字符数组" % bad_backend
    assert bad_quoted == 0, "registry.yaml 出现 %d 处双重引号" % bad_quoted


def test_backlog_doc_is_fresh() -> None:
    path = os.path.join(ROOT, "docs", "BACKLOG.md")
    assert os.path.isfile(path), "缺 docs/BACKLOG.md（跑 tools/gen_backlog.py）"
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == gen_backlog.render(), "BACKLOG.md 过期"


def test_backlog_matches_gaps_hours() -> None:
    """同一 id 在两份账里工时必须一致（防止两份预算对不上）。"""
    built = gen_backlog.build()
    gaps = built["gaps"]
    for it in built["items"]:
        if it["id"] in gaps:
            assert it["hours"] == gaps[it["id"]], \
                "%s 工时不一致：backlog=%s gaps=%s" % (it["id"], it["hours"], gaps[it["id"]])


def test_backlog_never_lists_verified_caps() -> None:
    """已 verified 的能力不该再出现在待挖清单里（防虚报进度）。"""
    from acadkit import registry
    verified = {c["id"] for c in registry.load()["capabilities"]
                if c.get("status") == "verified"}
    items = {i["id"] for i in gen_backlog.build()["items"]}
    overlap = sorted(verified & items)
    assert not overlap, "这些已经 verified 却还在 backlog：%r" % overlap


def test_cadcraft_mine_doc_is_fresh() -> None:
    path = os.path.join(ROOT, "docs", "CADCRAFT_MINE.md")
    assert os.path.isfile(path), "缺 docs/CADCRAFT_MINE.md（跑 tools/gen_cadcraft_mine.py）"
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == gen_cadcraft_mine.render(), "CADCRAFT_MINE.md 过期"


def test_cadcraft_mine_fields_complete() -> None:
    built = gen_cadcraft_mine.build()
    for it in built["items"]:
        assert it.get("src"), "%s 没写源路径" % it["id"]
        assert 1 <= it["value"] <= 5, "%s 价值分越界" % it["id"]
        assert it["hours"] > 0, "%s 工时应为正" % it["id"]

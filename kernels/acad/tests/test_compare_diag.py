"""图纸比对与错误分类的离线测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from acadkit.core.diag import classify, hint_for, summarize                 # noqa: E402
from acadkit.dxf.compare import compare                                     # noqa: E402
from acadkit.dxf.document import (Entity, add_entity, make_circle,           # noqa: E402
                                  make_line, new_document)


# ── 图纸比对 ────────────────────────────────────────────────────────
def _doc_with(entities) -> object:
    doc = new_document()
    for e in entities:
        add_entity(doc, e)
    return doc


def test_identical_documents() -> None:
    a = _doc_with([make_line((0, 0), (10, 0), handle="1")])
    b = _doc_with([make_line((0, 0), (10, 0), handle="1")])
    rep = compare(a, b)
    assert rep.identical, rep.to_text()
    assert rep.counts == {"old": 1, "new": 1}


def test_added_and_removed() -> None:
    a = _doc_with([make_line((0, 0), (10, 0), handle="1")])
    b = _doc_with([make_line((0, 0), (10, 0), handle="1"),
                   make_circle((0, 0), 5, handle="2")])
    rep = compare(a, b)
    assert rep.added == ["2"] and rep.removed == []
    rep2 = compare(b, a)
    assert rep2.removed == ["2"]


def test_geometry_change_reports_fields() -> None:
    a = _doc_with([make_circle((0, 0), 5, handle="1")])
    b = _doc_with([make_circle((0, 0), 6, handle="1")])
    rep = compare(a, b)
    assert not rep.identical
    assert rep.changed[0].key == "1"
    assert "c40" in rep.changed[0].fields, rep.changed[0].fields
    assert "~ 1(CIRCLE)" in rep.to_text()


def test_layer_change_detected() -> None:
    a = _doc_with([make_line((0, 0), (10, 0), layer="A", handle="1")])
    b = _doc_with([make_line((0, 0), (10, 0), layer="B", handle="1")])
    rep = compare(a, b)
    assert rep.changed[0].fields == ["layer"]


def test_within_tolerance_is_not_change() -> None:
    a = _doc_with([make_circle((0, 0), 5.0, handle="1")])
    b = _doc_with([make_circle((0, 0), 5.0000001, handle="1")])
    assert compare(a, b).identical, "1e-7 的差不应算改图"


def test_entities_without_handle_use_placeholder() -> None:
    a = _doc_with([Entity("POINT", [(0, "POINT"), (10, "1"), (20, "2")])])
    b = _doc_with([Entity("POINT", [(0, "POINT"), (10, "1"), (20, "3")])])
    rep = compare(a, b)
    assert rep.changed and rep.changed[0].key == "POINT#0"


# ── 错误分类 ────────────────────────────────────────────────────────
def test_classify_busy_is_retryable() -> None:
    exc = OSError("(-2147418111, 'Call was rejected by callee.')")
    d = classify(exc)
    assert d.kind in ("busy", "rejected") and d.retryable


def test_classify_modal_not_retryable() -> None:
    d = classify(RuntimeError("弹出了模态对话框，等待用户输入"))
    assert d.kind == "modal" and not d.retryable
    assert "对话框" in d.hint


def test_classify_unknown_command() -> None:
    d = classify(ValueError("未知命令「ACADKITVERSION」"))
    assert d.kind == "not_found"
    assert "插件" in d.hint


def test_classify_readonly_property() -> None:
    d = classify(AttributeError("Property 'AddDimRotated.ExtLine2Point' can not be set"))
    assert d.kind == "readonly"


def test_classify_permission() -> None:
    d = classify(PermissionError("拒绝访问：C:/Program Files/x"))
    assert d.kind == "permission" and not d.retryable


def test_summarize_has_kind_and_retry_flag() -> None:
    text = summarize(TimeoutError("timeout after 60s"))
    assert "[timeout" in text and "不可重试" not in text


def test_hint_for_unknown_kind() -> None:
    assert "未归类" in hint_for("no_such_kind")

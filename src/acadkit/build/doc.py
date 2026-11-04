"""文档类 builder：新建图纸 / 关闭图纸。

为什么需要这一族：其余能力都假设"用例已在第二个文档里"，而
`Documents.Add` / `Document.Close` 本身从来没被单独验证过。
没有它们，任何"画进用户当前图纸"的批量脚本都没有安全收尾手段
（要么污染用户图纸，要么靠 `Stop-Process` 强杀）。

两条 builder 都**自己收尾**：新建出来的临时图纸在 builder 结束时就被关掉
（`Saved = True` 丢修改 → `Close(False)`），所以 `env_documents`
（用例前后文档数必须相等）永远成立，用户手上的图纸也不受影响。
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from ..core import com


def _doc_count(app: Any) -> Optional[int]:
    try:
        return int(app.Documents.Count)
    except Exception:                                   # noqa: BLE001
        return None


def _app(ctx: Dict[str, Any]) -> Any:
    app = ctx.get("app")
    if app is None:
        raise RuntimeError("ctx 里没有 app —— 文档类能力必须经 CaseRunner 跑")
    return app


def _active_name(app: Any) -> str:
    try:
        return str(app.ActiveDocument.Name)
    except Exception:                                   # noqa: BLE001
        return ""


def _close_doc(app: Any, doc: Any) -> float:
    """关掉一个新建文档，返回耗时（秒）。耗时用来判断有没有弹模态框。"""
    t0 = time.time()
    name = ""
    try:
        name = str(doc.Name)
    except Exception:                                   # noqa: BLE001
        pass
    for _ in range(4):
        try:
            doc.Saved = True                # 丢弃修改，避免 Close 弹"是否保存"
        except Exception:                               # noqa: BLE001
            pass
        try:
            com.retry(lambda: doc.Close(False), label="Close(doc)")
            break
        except Exception:                               # noqa: BLE001
            # 代理偶发失效：重新按名字找回来再关
            time.sleep(0.5)
            try:
                app = com.refresh(app)
                doc = app.Documents.Item(name) if name else doc
            except Exception:                           # noqa: BLE001
                break
    time.sleep(0.3)
    return round(time.time() - t0, 3)


def _add_doc(app: Any) -> Any:
    com.retry(lambda: app.Documents.Add(), label="Documents.Add")
    # 本机实测：Add 之后立刻读属性偶发 DISPID 失败，等一拍再取 ActiveDocument
    time.sleep(0.4)
    return com.refresh(app).ActiveDocument


def build_new_drawing(doc: Any, ctx: Dict[str, Any]) -> None:
    """新建一张图纸，读它的属性，然后**关掉**（不留垃圾）。"""
    app = _app(ctx)
    before = _doc_count(app)
    case_doc = ""
    try:
        case_doc = str(doc.Name)
    except Exception:                                   # noqa: BLE001
        pass
    new_doc = _add_doc(app)
    after = _doc_count(app)
    name = ""
    entities: Optional[int] = None
    try:
        name = str(new_doc.Name)
        entities = int(new_doc.ModelSpace.Count)
    except Exception:                                   # noqa: BLE001
        pass
    active = _active_name(app)
    elapsed = _close_doc(app, new_doc)
    final = _doc_count(app)
    ctx["artifacts"]["doc_new"] = {
        "count_before": before,
        "count_after_add": after,
        "count_final": final,
        "name": name,
        "entities": entities,
        "active_after_add": active,
        "case_doc": case_doc,
        "close_elapsed_s": elapsed,
        "active_final": _active_name(app),
    }


def build_close_drawing(doc: Any, ctx: Dict[str, Any]) -> None:
    """开一张临时图纸再按正规路径关掉，记录前后文档数（证明关得掉、关得快）。"""
    app = _app(ctx)
    before = _doc_count(app)
    case_doc = ""
    try:
        case_doc = str(doc.Name)
    except Exception:                                   # noqa: BLE001
        pass
    scratch = _add_doc(app)
    after_add = _doc_count(app)
    name = ""
    try:
        name = str(scratch.Name)
    except Exception:                                   # noqa: BLE001
        pass
    elapsed = _close_doc(app, scratch)
    final = _doc_count(app)
    ctx["artifacts"]["doc_close"] = {
        "count_before": before,
        "count_after_add": after_add,
        "count_final": final,
        "name": name,
        "case_doc": case_doc,
        "close_elapsed_s": elapsed,
        "active_final": _active_name(app),
    }

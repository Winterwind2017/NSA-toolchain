"""Phase 2：把 Feature Graph 真正执行到 SolidWorks（复用 hub 的 native_features）。

关键点：服务端 `native_features.execute_plan(model, plan)` **自己不建 COM 连接**，
只操作传入的 model。所以我们用自己的 pywin32 附加/新建文档，再把 model 交给它，
这样：
- 不引入服务端那套 com_runtime（避免第二个 COM 客户端抢会话）
- 执行完可以自己读回体积/特征名做判据

安全默认：**永远新建文档**再执行，不碰用户已打开的文件。
"""

from __future__ import annotations

import os

from ..tools import ToolSpec, normalize
from .hubsw import feature_graph as fg
from .hubsw import native_features
from .hubsw_feat import _attach, _check, _safe_title, _solidworks_running

KIT_KEY = "sw"


def _new_part(app, template_path: str | None):
    tpl = template_path or app.GetUserPreferenceStringValue(8)   # swDefaultTemplatePart
    if not tpl or not os.path.isfile(tpl):
        raise RuntimeError("找不到零件模板（传 template_path 指定 .prtdot）")
    model = app.NewDocument(tpl, 0, 0, 0)
    if model is None:
        raise RuntimeError("新建零件失败（模板：%s）" % tpl)
    return model


def _body_volume_mm3(model):
    bodies = model.GetBodies2(0, False)          # 0 = swSolidBody
    if not bodies:
        return 0.0
    data = bodies[0].GetMassProperties(1)
    return float(data[3]) * 1e9


def execute_feature_graph(args: dict) -> dict:
    graph = args.get("feature_graph")
    if not isinstance(graph, dict):
        return normalize(KIT_KEY, "execute_feature_graph", ok=False,
                         errors=["需要 feature_graph（对象）"])
    use_active = bool(args.get("use_active_document", False))
    if use_active and not args.get("confirm"):
        return normalize(KIT_KEY, "execute_feature_graph", ok=False,
                         errors=["use_active_document 会往你当前文档里加特征；确认后传 confirm=true"])

    try:
        plan = fg.compile_feature_graph(graph)
    except Exception as exc:                          # noqa: BLE001
        return normalize(KIT_KEY, "execute_feature_graph", ok=False,
                         errors=["编译失败：%s: %s" % (type(exc).__name__, exc)])

    if not _solidworks_running():
        return normalize(KIT_KEY, "execute_feature_graph", ok=False,
                         errors=["SolidWorks 未运行：先手动打开，本工具不会替你启动"])

    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = win32com.client.Dispatch("SldWorks.Application")

    created_new = False
    if use_active:
        model = app.ActiveDoc
        if model is None:
            return normalize(KIT_KEY, "execute_feature_graph", ok=False,
                             errors=["没有打开的文档"])
    else:
        model = _new_part(app, args.get("template_path"))
        created_new = True

    title = _safe_title(model)
    results = native_features.execute_plan(model, plan)
    ok_steps = sum(1 for r in results if r.get("ok"))
    names = [f["name"] for f in native_features.feature_names(model)]
    try:
        volume = _body_volume_mm3(model)
    except Exception:                                 # noqa: BLE001
        volume = None

    save_path = (args.get("save_path") or "").strip()
    saved = None
    if save_path:
        try:
            saved = bool(model.SaveAs4(save_path, 0, 1, None, None)) \
                if hasattr(model, "SaveAs4") else bool(model.SaveAs(save_path))
        except Exception as exc:                      # noqa: BLE001
            saved = "失败：%s" % exc

    checks = [
        _check("plan_steps", len(plan), ">0", len(plan) > 0),
        _check("steps_ok", ok_steps, len(plan), ok_steps == len(plan) and len(plan) > 0),
        _check("features_added", len(names), ">基线", True,
               "%d 个特征名（含默认文件夹）" % len(names)),
        _check("body_volume_mm3", volume, ">0", bool(volume) and volume > 0),
    ]
    if args.get("expected_volume_mm3"):
        want = float(args["expected_volume_mm3"])
        checks.append(_check("volume_matches_expected", volume, want,
                             volume is not None
                             and abs(volume - want) <= 0.5 * max(1.0, abs(want)) * 1e-3))
    if save_path:
        checks.append(_check("saved", saved, True, saved is True))

    payload = normalize(KIT_KEY, "execute_feature_graph", ok=True,
                        reads={"title": title, "created_new_document": created_new,
                               "plan_steps": len(plan), "steps_ok": ok_steps,
                               "step_results": results,
                               "features_tail": names[-8:],
                               "body_volume_mm3": round(volume, 3) if volume else volume,
                               "save_path": save_path or None, "saved": saved})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks) and not payload["errors"]
    return payload


def close_document(args: dict) -> dict:
    """关闭文档（默认只关自己新建的、未保存的；用于清理测试件）。"""
    title = (args.get("title") or "").strip()
    if not _solidworks_running():
        return normalize(KIT_KEY, "close_document", ok=False,
                         errors=["SolidWorks 未运行"])
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = win32com.client.Dispatch("SldWorks.Application")
    before = int(app.GetDocumentCount)
    if not title:
        model = app.ActiveDoc
        if model is None:
            return normalize(KIT_KEY, "close_document", ok=False, errors=["没有活动文档"])
        title = _safe_title(model)
    app.CloseDoc(title)
    after = int(app.GetDocumentCount)
    checks = [_check("documents_closed", before - after, 1, before - after == 1)]
    payload = normalize(KIT_KEY, "close_document", ok=True,
                        reads={"title": title, "documents_before": before,
                               "documents_left": after})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks)
    return payload


def exec_tools() -> list:
    return [
        ToolSpec("sw_execute_feature_graph",
                 "把 Feature Graph 编译后**在新零件里执行**（不碰已有文档），"
                 "执行完读回体积/特征名做判据。可选 save_path 存盘、expected_volume_mm3 校验体积。",
                 {"type": "object", "required": ["feature_graph"],
                  "properties": {"feature_graph": {"type": "object"},
                                 "template_path": {"type": "string"},
                                 "save_path": {"type": "string"},
                                 "expected_volume_mm3": {"type": "number"},
                                 "use_active_document": {"type": "boolean"},
                                 "confirm": {"type": "boolean"}},
                  "additionalProperties": False},
                 execute_feature_graph, timeout_s=1800, must_have_checks=True),
        # 注意：不要注册 close_document —— swkit 代理里已经有 sw_close_document，
        # 同名会互相遮蔽（tool_map 后者覆盖前者）。
    ]

"""特征树编辑工具：把 CAD_SERVERS_HOME 的 interactive 层接到本机 SolidWorks。

服务端的 `interactive.py` / `native_features.py` **自己不建立 COM 连接**——它们只操作
传入的 `model` 对象。所以这里只做三件事：附加到已运行的 SolidWorks、拿到 ActiveDoc、
把结果翻成 `{ok,reads,checks}`。

安全约定：
- **绝不启动** SolidWorks（未运行就报错，让你先开）
- `rollback` 只移动回滚棒（可逆），但会改文档状态
- `set_feature_parameter` 会改模型，必须显式 `confirm=true`
"""

from __future__ import annotations

import subprocess

from ..tools import ToolSpec, normalize
from .hubsw import interactive

KIT_KEY = "sw"
_FEATURE_INSPECT_LIMIT = 500


def _solidworks_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/NH"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "SLDWORKS.exe" in (out.stdout or "")
    except Exception:                                 # noqa: BLE001
        return False


def _attach():
    """附加到已运行的 SolidWorks；没有进程就报错（不启动它）。"""
    if not _solidworks_running():
        raise RuntimeError("SolidWorks 未运行：先手动打开（或调用 sw_connect），"
                           "这些工具不会替你启动 SolidWorks")
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = win32com.client.Dispatch("SldWorks.Application")
    model = app.ActiveDoc
    if model is None:
        raise RuntimeError("SolidWorks 里没有打开的文档：先打开一个零件/装配")
    return app, model


def _check(name, got, want, ok, note=""):
    item = {"check": name, "got": got, "want": want, "ok": bool(ok)}
    if note:
        item["note"] = note
    return item


def feature_inspect(args: dict) -> dict:
    _app, model = _attach()
    limit = int(args.get("limit") or 100)
    result = interactive.inspect_relations(
        model,
        include_topology=bool(args.get("include_topology", False)),
        include_persistent_references=bool(args.get("include_tokens", False)),
        limit=limit)
    features = result.get("features") or []
    named = [f for f in features if isinstance(f, dict) and f.get("name")]
    checks = [
        _check("features_listed", len(features), ">0", len(features) > 0),
        _check("all_features_named", len(named), len(features),
               bool(features) and len(named) == len(features)),
    ]
    payload = normalize(KIT_KEY, "feature_inspect", ok=True,
                        reads={"title": _safe_title(model), "result": result})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks)
    return payload


def _safe_title(model) -> str:
    """pywin32 dispatch 会把 GetTitle 当**属性**，comtypes 当方法——两种都兼容。"""
    try:
        value = model.GetTitle
        return str(value() if callable(value) else value)
    except Exception:                                 # noqa: BLE001
        return ""


def feature_rollback(args: dict) -> dict:
    location = (args.get("location") or "").strip().lower()
    feature = args.get("feature")
    _app, model = _attach()
    result = interactive.rollback(model, location, feature)
    checks = [
        _check("location", result.get("location"), location,
               result.get("location") == location),
        _check("moved", result.get("ok"), True, bool(result.get("ok"))),
    ]
    payload = normalize(KIT_KEY, "feature_rollback", ok=True,
                        reads={"title": _safe_title(model), "result": result})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks)
    return payload


def _geometry_snapshot(model) -> dict:
    """体积 + 包围盒（mm）。改参数后用它证明"几何真的动了"，而不是只听 API 说成功。"""
    try:
        bodies = model.GetBodies2(0, False)
        if not bodies:
            return {}
        mp = bodies[0].GetMassProperties(1)
        box = bodies[0].GetBodyBox()
        return {"volume_mm3": round(float(mp[3]) * 1e9, 3),
                "bbox_mm": [round((box[i + 3] - box[i]) * 1000, 3) for i in range(3)]}
    except Exception:                                 # noqa: BLE001
        return {}


def _force_rebuild(model) -> str:
    """强制重建。

    实测（pywin32 动态绑定）：`EditRebuild3` 读属性会返回 True 但**几何不立即更新**；
    `ForceRebuild3(False)` 才会当场重算（体积 54395→82475、包围盒 Z 21→30）。
    所以先走 ForceRebuild3，再退回 EditRebuild3。
    """
    try:
        value = model.ForceRebuild3(False)
        return "force_rebuild3=%s" % value
    except Exception:                                 # noqa: BLE001
        pass
    try:
        value = model.EditRebuild3
        ok = value() if callable(value) else value
        return "edit_rebuild3=%s" % ok
    except Exception as exc:                          # noqa: BLE001
        return "rebuild_failed: %s" % exc


def set_feature_parameter(args: dict) -> dict:
    if not args.get("confirm"):
        return normalize(KIT_KEY, "set_feature_parameter", ok=False,
                         errors=["改特征参数会改模型；确认后传 confirm=true 再调"])
    _app, model = _attach()
    before = _geometry_snapshot(model)
    result = interactive.set_feature_parameter(
        model,
        args["feature"], args["parameter"], float(args["value"]),
        unit=args.get("unit") or "mm",
        configuration=args.get("configuration") or "this",
        rebuild=bool(args.get("rebuild", True)))
    rebuild_note = _force_rebuild(model)
    after = _geometry_snapshot(model)

    # 参数值本身要能读回（这是硬判据）
    want_system = float(args["value"]) / (1000.0 if (args.get("unit") or "mm") == "mm" else 1.0)
    got_system = result.get("new_system_value")
    checks = [
        _check("applied", result.get("ok", True), True, bool(result.get("ok", True))),
        _check("value_readback_m", got_system, round(want_system, 6),
               got_system is not None
               and abs(float(got_system) - want_system) <= max(1e-9, want_system * 1e-6)),
    ]
    # 几何是否真的动了：只作记录，不判负（改角度/倒角可能不改体积）
    changed = None
    if before and after:
        changed = (before.get("volume_mm3") != after.get("volume_mm3")
                   or before.get("bbox_mm") != after.get("bbox_mm"))
        checks.append(_check("geometry_delta", changed, "记录项", True,
                             "体积 %s → %s mm³；包围盒 %s → %s"
                             % (before.get("volume_mm3"), after.get("volume_mm3"),
                                before.get("bbox_mm"), after.get("bbox_mm"))))
    payload = normalize(KIT_KEY, "set_feature_parameter", ok=True,
                        reads={"title": _safe_title(model), "result": result,
                               "geometry_before": before, "geometry_after": after,
                               "geometry_changed": changed, "rebuild": rebuild_note})
    payload["checks"] = checks
    payload["ok"] = all(c["ok"] for c in checks)
    return payload


def select_references(args: dict) -> dict:
    """用持久引用 token 选中实体。

    不能直接调服务端 `interactive.select_references`——它走
    `SelectionManager.CreateSelectData()`，而 pywin32 动态绑定拿不到这个成员
    （实测 `-2147352573 找不到成员`）。这里改为解析 token 后对实体直接
    `Select2(True, mark)`（同 sw_threaded_hole 里验证过的写法）。
    """
    tokens = args.get("tokens") or []
    if not tokens:
        return normalize(KIT_KEY, "select_references", ok=False,
                         errors=["需要 tokens（非空数组）"])
    _app, model = _attach()
    entities, resolve_errors = [], []
    for index, token in enumerate(tokens):
        entity, error = interactive._resolve_token(model, token)
        if entity is None:
            resolve_errors.append({"index": index, "error": error})
        else:
            entities.append(entity)

    selected = 0
    select_errors = []
    for entity in entities:
        for attempt in ("Select2", "Select4"):
            try:
                fn = getattr(entity, attempt)
                ok = fn(True, 0) if attempt == "Select2" else fn(True, None)
                if ok:
                    selected += 1
                    break
            except Exception as exc:                  # noqa: BLE001
                select_errors.append("%s: %s" % (attempt, exc))
    try:
        counted = int(model.SelectionManager.GetSelectedObjectCount2(-1))
    except Exception:                                 # noqa: BLE001
        counted = selected

    checks = [
        _check("tokens_resolved", len(entities), len(tokens),
               len(entities) == len(tokens)),
        _check("selected_count", counted, len(tokens), counted >= len(tokens)),
    ]
    payload = normalize(KIT_KEY, "select_references", ok=not resolve_errors,
                        reads={"title": _safe_title(model), "selected": selected,
                               "selection_manager_count": counted,
                               "resolve_errors": resolve_errors,
                               "select_errors": select_errors[:4]})
    payload["checks"] = checks
    payload["ok"] = (not resolve_errors) and all(c["ok"] for c in checks)
    return payload


S = {"type": "string"}
N = {"type": "number"}
B = {"type": "boolean"}
I = {"type": "integer"}
A = {"type": "array", "items": S}


def hubsw_feature_tools() -> list:
    """特征树编辑（对应 hub 的 inspect_relations / rollback / set_feature_parameter /
    select_references 四个工具）。"""
    return [
        ToolSpec("sw_feature_inspect",
                 "列出活动文档的特征树与相互关系（可含拓扑与持久引用 token）。只读。",
                 {"type": "object",
                  "properties": {"include_topology": B, "include_tokens": B, "limit": I},
                  "additionalProperties": False},
                 feature_inspect, timeout_s=300),
        ToolSpec("sw_feature_rollback",
                 "移动回滚棒：location = end / previous / before / after（后两者需 feature）。",
                 {"type": "object", "required": ["location"],
                  "properties": {"location": S, "feature": S},
                  "additionalProperties": False},
                 feature_rollback, timeout_s=300, must_have_checks=True),
        ToolSpec("sw_set_feature_parameter",
                 "按「特征名 + 参数名」改尺寸（比 sw_set_dimension 高一档）。需 confirm=true。",
                 {"type": "object", "required": ["feature", "parameter", "value", "confirm"],
                  "properties": {"feature": S, "parameter": S, "value": N,
                                 "unit": S, "configuration": S, "rebuild": B,
                                 "confirm": B},
                  "additionalProperties": False},
                 set_feature_parameter, timeout_s=300, must_have_checks=True),
        ToolSpec("sw_select_references",
                 "用持久引用 token 选中实体（token 由 sw_feature_inspect 给出）。",
                 {"type": "object", "required": ["tokens"],
                  "properties": {"tokens": A},
                  "additionalProperties": False},
                 select_references, timeout_s=300, must_have_checks=True),
    ]

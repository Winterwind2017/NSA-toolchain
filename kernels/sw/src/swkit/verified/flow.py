"""swkit.verified.flow —— SOLIDWORKS Flow Simulation API（自检 / 建工程）

## 为什么之前"找不到 API"

`FloWorks.App` / `FloXpress.FloXpress` 这两个 ProgID 指向
`FloXpress\\bin\\fw03_fxp.dll`，它们的 `App` 只实现 **`IApp`**，方法全是
`TB_on_SolveCB` / `TB_NewProject` 这类**工具栏按钮回调**，不是脚本 API。

真正的 Flow Simulation API 在自己的一套类型库里：

| 文件 | 作用 |
|---|---|
| `<安装>\\SOLIDWORKS Flow Simulation\\binCFW\\EFDApiSrv.tlb` | `EFDLauncher`（`IEFDLauncher`） |
| `<安装>\\SOLIDWORKS Flow Simulation\\binCFW\\EFDApi.tlb` | `IApplication` / `IDocument` / `IProject` … |

调用顺序（实测）：

    launcher = CreateObject("EFDApiSrv.EFDLauncher")
    app = launcher.Attach2RunningCADInstance(sw_pid)   # 传**运行中 SW 的进程号**
    app.SetSilent()                                    # 静默，避免弹窗
    doc = app.GetActiveDoc()                           # IDocument（Flow 侧文档）
    doc.GetProjectsCount() / doc.CreateProject(None)   # → IProject

判据：
* `status`：版本串非空（本机 `Flow Simulation 2025 SP3.0. Build: 6784`）、
  工程数是整数、拿到 `IDocument`；没有打开的 SW 文档时 `GetActiveDoc` 为 None。
* `project`：`CreateProject(None)` 返回 `IProject` 对象。

## 已知未打通

整轮求解要依次配边界条件/目标/网格，再 `GetCalculationControlOptions` +
`ApplyCalculationControlOptions`；本轮没有跑通，所以**不宣称能求解**。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ..core.com import pyw, val

__all__ = ["available", "status", "create_project", "FlowUnavailable"]

DEFAULT_ROOT = r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS Flow Simulation\binCFW"
SRV_TLB = "EFDApiSrv.tlb"
API_TLB = "EFDApi.tlb"


class FlowUnavailable(RuntimeError):
    """Flow Simulation 未安装或 API 服务器起不来。"""


def _paths(root: Optional[str] = None):
    r = root or os.environ.get("SWKIT_FLOW_DIR") or DEFAULT_ROOT
    srv = os.path.join(r, SRV_TLB)
    api = os.path.join(r, API_TLB)
    return srv, api


def available(root: Optional[str] = None) -> bool:
    srv, api = _paths(root)
    return os.path.isfile(srv) and os.path.isfile(api)


def _modules(root: Optional[str] = None):
    srv_p, api_p = _paths(root)
    if not (os.path.isfile(srv_p) and os.path.isfile(api_p)):
        raise FlowUnavailable("找不到 EFDApiSrv.tlb / EFDApi.tlb：%s" % os.path.dirname(srv_p))
    try:
        from comtypes.client import GetModule
    except ModuleNotFoundError:
        # comtypes 可能只在自带目录里；comtypes_bundle() 会按
        # SWKIT_VENDOR → ~/.swkit/vendor → <repo>/vendor 顺序注入 sys.path。
        from ..core import com as _com
        _com.comtypes_bundle()
        try:
            from comtypes.client import GetModule
        except Exception as exc:                    # noqa: BLE001
            raise FlowUnavailable("comtypes 不可用：%s" % exc)
    return GetModule(srv_p), GetModule(api_p)


def _attach(sw_pid: Optional[int] = None, root: Optional[str] = None):
    """附加到运行中的 SolidWorks，返回 (IApplication, IDocument)。"""
    srv, api = _modules(root)
    from comtypes.client import CreateObject

    if sw_pid is None:
        sw = pyw().Dispatch("SldWorks.Application")
        pid_attr = val(sw, "GetProcessID")
        sw_pid = int(pid_attr) if not callable(pid_attr) else int(pid_attr())
    launcher = CreateObject(srv.EFDLauncher)
    app = launcher.Attach2RunningCADInstance(int(sw_pid))
    try:
        app.SetSilent()
    except Exception:                               # noqa: BLE001
        pass
    return app, app.GetActiveDoc()


def _result(tool: str, api_name: str) -> Dict[str, Any]:
    return {"ok": False, "tool": tool, "api": api_name, "detail": {}, "checks": {}}


def status(sw_pid: Optional[int] = None, root: Optional[str] = None) -> Dict[str, Any]:
    """Flow Simulation 自检：版本、静默模式、Flow 文档、工程数。"""
    out = _result("sw_flow_check", "EFDApiSrv.EFDLauncher.Attach2RunningCADInstance + EFDApi.IApplication")
    try:
        app, doc = _attach(sw_pid, root)
    except FlowUnavailable as exc:
        out["detail"]["error"] = str(exc)
        return out
    except Exception as exc:                        # noqa: BLE001
        raw = "%s: %s" % (type(exc).__name__, exc)
        # `Attach2RunningCADInstance` 在 **Flow Simulation 插件未在当前
        # SolidWorks 会话里加载** 时会抛 E_FAIL(0x80004005, '未指定的错误')。
        # 这不是 API 用法问题，而是环境前置条件——给出可执行的提示，
        # 并标记 addin_loaded=False，避免被误读成"API 坏了"。
        out["detail"]["raw_error"] = raw
        out["detail"]["addin_loaded"] = False
        out["detail"]["error"] = (
            "Flow Simulation 插件未在当前 SolidWorks 会话中加载："
            "请在 SolidWorks 里 工具 → 插件 勾选「SOLIDWORKS Flow Simulation」，"
            "或重启 SolidWorks 后再调用。"
            "（原始错误：%s）" % raw)
        out["checks"] = {"addin_loaded": False}
        return out

    ver = _safe(app, "GetVersion")
    silent = _safe(app, "IsSilentMode")
    out["detail"].update({"version": ver, "silent": silent,
                          "flow_document": doc is not None})
    if doc is None:
        out["detail"]["error"] = "Flow 侧没有活动文档（先在 SolidWorks 里打开一个零件/装配）"
        out["checks"] = {"attached": True, "has_document": False}
        return out

    count = _safe(doc, "GetProjectsCount")
    active = _safe(doc, "GetActiveProject")
    title = _safe(doc, "GetTitle")
    cad_doc = _safe(doc, "GetCADModelDoc")
    out["detail"].update({
        "title": title, "projects_count": count,
        "active_project": (None if active is None else type(active).__name__),
        "cad_document": cad_doc is not None,
    })
    out["checks"] = {
        "attached": True,
        "has_document": True,
        "version_readable": isinstance(ver, str) and bool(ver),
        "projects_count_readable": isinstance(count, int) and count >= 0,
        "cad_document_available": cad_doc is not None,
    }
    out["ok"] = all(out["checks"].values())
    return out


def create_project(sw_pid: Optional[int] = None, root: Optional[str] = None) -> Dict[str, Any]:
    """建 Flow 工程（`IDocument.CreateProject(None)`），判据：拿到 `IProject`。"""
    out = _result("sw_flow_project", "EFDApi.IDocument.CreateProject")
    try:
        app, doc = _attach(sw_pid, root)
    except FlowUnavailable as exc:
        out["detail"]["error"] = str(exc)
        return out
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    if doc is None:
        out["detail"]["error"] = "没有 Flow 侧文档，无法建工程"
        return out
    before = _safe(doc, "GetProjectsCount")
    try:
        proj = doc.CreateProject(None)
    except Exception as exc:                        # noqa: BLE001
        out["detail"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    name = _safe(proj, "GetName") if proj is not None else None
    after = _safe(doc, "GetProjectsCount")
    out["detail"].update({"projects_before": before, "projects_after": after,
                          "project_name": name,
                          "project_object": None if proj is None else type(proj).__name__})
    out["checks"] = {"project_object_returned": proj is not None}
    out["ok"] = out["checks"]["project_object_returned"]
    return out


def _safe(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    try:
        node = getattr(obj, name)
    except Exception:
        return None
    try:
        return node() if callable(node) else node
    except Exception:
        return None

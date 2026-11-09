"""swkit.core.com —— pywin32 / comtypes 双栈桥接

本项目最贵的经验之一：SolidWorks 的 COM 有两套绑定，**各有各的坑**，必须分工：

* `GetComponents` / `GetBodies2` / `GetVisibleEntities2` 这类返回 VARIANT 数组的调用
  → 用 **pywin32**。comtypes 在这里会抛 `KeyError: 9`（VT_DISPATCH 数组解包失败）。
* 需要传强类型参数（`IFeature`、`IMathTransform`）或要出参的调用
  → 用 **comtypes**。pywin32 的动态分派拿不到具体接口。
* 给"属性"塞**对象数组**（`IMirrorComponentFeatureData.ComponentsTo...`）
  → 必须 pywin32 + 显式 `VARIANT(VT_ARRAY | VT_DISPATCH, [...])`。
  comtypes 会把 `tuple(POINTER(IComponent2))` **静默丢弃**（不报错、回读为 None）。
* 通用 `_Dispatch` 赋给 `VT_DISPATCH` 属性会 `DISP_E_UNKNOWNNAME (-2147352570)`
  → 先 `obj.QueryInterface(具体接口)` 再赋。
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence

__all__ = [
    "pyw", "dispatch", "none_dispatch", "var_dispatch_array", "var_i4_array",
    "var_variant_array", "comtypes_bundle", "qi", "val", "safe_call",
]


def pyw():
    """返回 pywin32 的 dynamic 模块（延迟导入，便于非 Windows 上 import 本包）。"""
    import win32com.client.dynamic as _d
    return _d


def dispatch(progid: str = "SldWorks.Application"):
    """连接到已运行的 SolidWorks（必要时由 COM 启动一个）。"""
    return pyw().Dispatch(progid)


def none_dispatch():
    """`SelectByID2` 等方法的 `Callout` 参数需要 VT_DISPATCH 的 NULL。"""
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def var_dispatch_array(objs: Iterable[Any]):
    """把一组 COM 对象包成 `VARIANT(VT_ARRAY|VT_DISPATCH)`。

    实测：这是唯一能让 `ComponentsToInstanceAlignToComponentOrigin` 真正接收到
    组件数组的形态（comtypes 的 tuple 会被丢掉）。
    """
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(objs))


def var_i4_array(values: Iterable[int]):
    """`VARIANT(VT_ARRAY|VT_I4)`，用于 `ComponentOrientations*` 之类整型数组。"""
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_I4, [int(v) for v in values])


def var_variant_array(values: Iterable[Any]):
    import pythoncom
    import win32com.client
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, list(values))


def comtypes_bundle(tlb_path: Optional[str] = None):
    """返回 `(sw_module, app)`：comtypes 生成的 sldworks 模块 + 已连接的 Application。

    `tlb_path` 默认取 `SW_TLB` 环境变量，再退到 SolidWorks 2025 的安装路径。
    """
    import os
    try:
        from comtypes.client import CreateObject, GetModule
    except ModuleNotFoundError:
        # comtypes 可能只存在于"自带目录"里（本机开发常见）。按顺序找候选：
        #   1) SWKIT_VENDOR
        #   2) ~/.swkit/vendor        ← 推荐的机器级位置（与代码解耦）
        #   3) <仓库>/vendor
        import os as _os
        import sys as _sys
        _here = _os.path.dirname(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))))
        _cands = [
            _os.environ.get("SWKIT_VENDOR") or "",
            _os.path.join(_os.path.expanduser("~"), ".swkit", "vendor"),
            _os.path.join(_here, "vendor"),
        ]
        for _cand in _cands:
            if _cand and _os.path.isdir(_cand) and _cand not in _sys.path:
                _sys.path.insert(0, _cand)
                try:
                    from comtypes.client import CreateObject, GetModule
                    break
                except ModuleNotFoundError:
                    _sys.path.remove(_cand)
        else:
            raise

    path = tlb_path or os.environ.get("SW_TLB") or \
        r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
    mod = GetModule(path)
    return mod, CreateObject(mod.SldWorks)


def qi(obj: Any, iface: Any) -> Any:
    """尽力 QueryInterface；失败则原样返回（调用方据此判断是否要报错）。"""
    if obj is None:
        return None
    try:
        out = obj.QueryInterface(iface)
        return out if out is not None else obj
    except Exception:
        return obj


def val(obj: Any, name: str, default: Any = None) -> Any:
    """属性/方法双形态安全取值。

    SolidWorks 的类型库在不同绑定、不同版本下，同一个成员可能是属性也可能是方法：
    `GetInterferenceCount`、`GetComponents`、`IsFixed`、`GetFirstView` 都踩过。
    """
    try:
        v = getattr(obj, name)
    except Exception:
        return default
    if not callable(v):
        return v
    try:
        return v()
    except Exception:
        # 关键：pywin32 下 `FirstFeature` / `GetNextFeature` 是**属性**，
        # 属性被当成"可调用"再一调用就抛 COM 错——此时应返回属性本身。
        return v


def safe_call(fn, *args, **kwargs):
    """调用并吞掉异常，返回 `(ok, result_or_exc_message)`——判据交给调用方。"""
    try:
        return True, fn(*args, **kwargs)
    except Exception as exc:          # noqa: BLE001 - 这里就是要兜住 COM 的千奇百怪
        return False, "%s: %s" % (type(exc).__name__, exc)

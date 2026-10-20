"""swkit.diagnostics.tlb —— 类型库反射（比猜方法名可靠得多）

用途：确认"某个方法到底存不存在"、"参数几个/什么类型"、"枚举值是多少"。

    from swkit.diagnostics.tlb import list_methods, dump_method, enum_values
    list_methods("IFeatureManager", "pattern")     # 看所有 pattern 相关方法
    dump_method("FeatureLinearPattern5")           # 打印 22 个参数名与类型
    enum_values("swMirrorType")                    # 从 swconst.tlb 读枚举值

TLB 路径：默认取 `SW_TLB` 环境变量，再退到 SW 2025 安装目录。
枚举值在 `swconst.tlb` 里，用 `swconst_values()` 或 `enum_values()`。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

_VT = {
    0: "VT_EMPTY", 1: "VT_NULL", 2: "VT_I2", 3: "VT_I4", 4: "VT_R4", 5: "VT_R8",
    6: "VT_CY", 7: "VT_DATE", 8: "VT_BSTR", 9: "VT_DISPATCH", 10: "VT_ERROR",
    11: "VT_BOOL", 12: "VT_VARIANT", 13: "VT_UNKNOWN", 16: "VT_I1", 17: "VT_UI1",
    18: "VT_UI2", 19: "VT_UI4", 20: "VT_I8", 21: "VT_UI8", 22: "VT_INT", 23: "VT_UINT",
    24: "VT_VOID", 25: "VT_HRESULT", 26: "VT_PTR", 27: "VT_SAFEARRAY", 28: "VT_CARRAY",
    29: "VT_USERDEFINED", 30: "VT_LPSTR", 31: "VT_LPWSTR", 36: "VT_RECORD",
    64: "VT_FILETIME", 66: "VT_BLOB", 67: "VT_STREAM", 68: "VT_STORAGE", 72: "VT_CLSID",
}
_KIND = {0: "ENUM", 1: "RECORD", 2: "MODULE", 3: "INTERFACE", 4: "DISPATCH",
         5: "COCLASS", 6: "ALIAS", 7: "UNION"}

__all__ = ["tlb_path", "swconst_path", "list_types", "list_methods",
           "dump_method", "enum_values"]


def tlb_path(explicit: Optional[str] = None) -> str:
    return explicit or os.environ.get("SW_TLB") or \
        r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"


def swconst_path(explicit: Optional[str] = None) -> str:
    return explicit or os.environ.get("SWCONST_TLB") or \
        r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb"


def _type_name(tlb: Any, index: int) -> str:
    try:
        return tlb.GetDocumentation(index)[0] or ("#%d" % index)
    except Exception:
        return "#%d" % index


def _arg_type(t: int) -> str:
    byref = "ByRef " if (t & 0x4000) else ""
    arr = "[]" if (t & 0x2000) else ""
    return byref + _VT.get(t & 0x0FFF, "VT_%d" % (t & 0x0FFF)) + arr


def _walk(tlb: Any):
    for i in range(tlb.GetTypeInfoCount()):
        try:
            ti = tlb.GetTypeInfo(i)
            ta = ti.GetTypeAttr()
        except Exception:
            continue
        yield _type_name(tlb, i), ti, ta


def list_types(pattern: str = "", path: Optional[str] = None) -> List[str]:
    """列出类型名（含 `pattern` 子串，不区分大小写）。"""
    import pythoncom
    tlb = pythoncom.LoadTypeLib(path or tlb_path())
    key = pattern.lower()
    return [name for name, _ti, _ta in _walk(tlb) if key in name.lower()]


def list_methods(type_name: str, pattern: str = "",
                 path: Optional[str] = None) -> List[Tuple[str, int]]:
    """列出某接口里名字含 `pattern` 的方法 → [(方法名, 参数个数)]。"""
    import pythoncom
    tlb = pythoncom.LoadTypeLib(path or tlb_path())
    key, want = pattern.lower(), type_name.lower()
    out: List[Tuple[str, int]] = []
    for name, ti, ta in _walk(tlb):
        if name.lower() != want:
            continue
        for j in range(getattr(ta, "cFuncs", 0) or 0):
            try:
                fd = ti.GetFuncDesc(j)
                names = [x for x in ti.GetNames(fd.memid) if x]
            except Exception:
                continue
            if names and (not key or key in names[0].lower()):
                out.append((names[0], len(fd.args)))
    return out


def dump_method(method_name: str, path: Optional[str] = None) -> List[Dict[str, Any]]:
    """打印某方法（所有重载）的参数名与类型。"""
    import pythoncom
    tlb = pythoncom.LoadTypeLib(path or tlb_path())
    want = method_name.lower()
    out: List[Dict[str, Any]] = []
    for tname, ti, ta in _walk(tlb):
        for j in range(getattr(ta, "cFuncs", 0) or 0):
            try:
                fd = ti.GetFuncDesc(j)
                names = [x for x in ti.GetNames(fd.memid) if x]
            except Exception:
                continue
            if not names or names[0].lower() != want:
                continue
            params = []
            for k, arg in enumerate(fd.args):
                pname = names[k + 1] if k + 1 < len(names) else "?"
                try:
                    ptype = _arg_type(arg[0])
                except Exception:
                    ptype = "?"
                params.append((pname, ptype))
            out.append({"interface": tname, "method": names[0],
                        "param_count": len(params), "params": params})
    return out


def enum_values(prefix: str, path: Optional[str] = None) -> Dict[str, int]:
    """从 `swconst.tlb` 读枚举常量（如 `swMirrorType`、`swFm`）。"""
    from comtypes.client import GetModule
    mod = GetModule(path or swconst_path())
    key = prefix.lower()
    return {n: int(getattr(mod, n)) for n in dir(mod) if n.lower().startswith(key)}

"""LISP 执行：在命令行里跑一段 `(progn …)`，**不加载 .lsp 文件**。

不加载文件的理由：`(load …)` 受 SECURELOAD / TRUSTEDPATHS 管控，而这两个变量
是**持久化**的 —— 探针忘还原就会污染用户的 VANILLA 配置（本项目踩过三次）。
`SendCommand` 直接执行内联 LISP 不需要任何信任设置。
"""

from __future__ import annotations

from typing import Any, Dict

from .helpers import send


def _p(ctx: Dict[str, Any], key: str, default):
    return (ctx.get("params") or {}).get(key, default)


def build_lisp_circle(doc: Any, ctx: Dict[str, Any]) -> None:
    x, y = _p(ctx, "center", (800.0, 0.0))
    radius = float(_p(ctx, "radius", 12.0))
    lisp = ('(progn (command "_.CIRCLE" (list %f %f 0.0) %f) (princ))'
            % (float(x), float(y), radius))
    send(doc, lisp, settle=0.6)
    ctx.setdefault("artifacts", {})["lisp"] = {"center": [x, y], "radius": radius}

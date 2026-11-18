"""错误分类与可操作建议（对照 CADCraft `apps/cadcraft/src/logging.rs` 的诊断思路）。

问题：现在失败只会抛一个 pywin32 的原始异常（`(-2147418111, '被调用方拒绝接收呼叫。')`），
人看了不知道该等、该关弹框、还是该改权限。这里把常见失败归成几类，给出**下一步做什么**，
并提供 `retryable` 让上层决定要不要重试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# 分类 → (是否可重试, 建议)
KINDS = {
    "busy": (True, "AutoCAD 正忙（出图/保存/重算）。等 0.3–1s 再试；连续忙说明有后台任务。"),
    "modal": (False, "有模态对话框挡着。先关掉（或用 dialogs 工具列出）再继续；"
                     "程序化路径要避免会弹框的命令。"),
    "rejected": (True, "COM 调用被拒（RPC_E_CALL_REJECTED）。这在 Plot/SetVariable 后很常见，"
                        "重试通常就好；连续失败要查是否卡在提示符。"),
    "permission": (False, "没有权限访问该路径/对象。换可写目录，或检查只读文件状态。"),
    "not_found": (False, "对象/命令不存在。核对名称；若是「未知命令」，说明插件/命令没加载。"),
    "readonly": (False, "属性只读（很多标注/表格属性都是）。改用重建或 .NET 通道。"),
    "unsupported": (False, "本机 AutoCAD 不支持该操作。查 docs/UNSUPPORTED.md 的替代方案。"),
    "timeout": (True, "超时。看是否停在提示符；必要时重启 AutoCAD 会话。"),
    "unknown": (False, "未归类的失败。保留原始异常与现场（工作目录）再分析。"),
}


@dataclass
class Diagnosis:
    kind: str
    retryable: bool
    hint: str
    raw: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "retryable": self.retryable,
                "hint": self.hint, "raw": self.raw}


_PATTERNS = [
    ("modal", r"modal|对话框|dialog|等待用户|user input"),
    ("busy", r"RPC_E_CALL_REJECTED|2147418111|被调用方拒绝|Server Busy|忙"),
    ("rejected", r"Call was rejected|拒绝接收呼叫|2147418111"),
    ("permission", r"PermissionError|拒绝访问|Access is denied|WinError 5\b"),
    ("not_found", r"未知命令|Unknown command|不在集合|KeyError|No such|找不到"),
    ("readonly", r"can not be set|read-only|只读|属性.*只读"),
    ("unsupported", r"不支持|not supported|Unsupported|没有可用|无效"),
    ("timeout", r"timeout|超时|timed out"),
]


def classify(exc: BaseException) -> Diagnosis:
    """把异常归到一类，并给出可操作建议。"""
    raw = "%s: %s" % (type(exc).__name__, str(exc))
    text = str(exc)
    # busy 与 rejected 是同一族，先按更具体的判
    for kind, pattern in _PATTERNS:
        if re.search(pattern, text, re.I):
            retry, hint = KINDS[kind]
            return Diagnosis(kind, retry, hint, raw)
    retry, hint = KINDS["unknown"]
    return Diagnosis("unknown", retry, hint, raw)


def hint_for(kind: str) -> str:
    return KINDS.get(kind, KINDS["unknown"])[1]


def summarize(exc: BaseException) -> str:
    """一行给人和 agent 看的结论。"""
    d = classify(exc)
    return "[%s%s] %s" % (d.kind, "" if d.retryable else "，不可重试", d.hint)

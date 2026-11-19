"""就地编辑的状态机（语义参照 CADCraft `cmd/blocks/refedit.rs` + `bedit.rs`）。

REFEDIT/BEDIT 在 AutoCAD 里会进一个"编辑中"的临时状态，退出时提交或放弃。
我们走的是"重定义块 + 重插引用"，但**同样需要这几条不变量**：

* 没进编辑不能改；
* 编辑中改的是**副本**，原图不动；
* 提交要么全成、要么回滚（失败不留半成品）；
* 放弃要还原到进入时的样子；
* 不能重复提交/重复放弃。

这个模块把状态机与"改动记录"做成纯数据，方便离线测。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STATES = ("idle", "editing", "committed", "aborted")


class RefEditError(RuntimeError):
    pass


@dataclass
class Change:
    op: str                       # add | modify | delete
    target: str                   # 实体句柄/名字
    before: Any = None
    after: Any = None


@dataclass
class RefEditSession:
    """一次就地编辑。`content` 是被编辑对象的可变副本。"""

    name: str
    content: Dict[str, Any]
    state: str = "idle"
    changes: List[Change] = field(default_factory=list)
    _snapshot: Optional[Dict[str, Any]] = field(default=None, repr=False)

    # ── 生命周期 ──
    def begin(self) -> "RefEditSession":
        if self.state != "idle":
            raise RefEditError("已经在编辑中（state=%s）" % self.state)
        # 关键：先把内容换成独立副本，否则"放弃"时调用方传进来的字典早已被改过，
        # 逐键还原也无从校验（实测踩到）。
        self.content = copy.deepcopy(self.content)
        self._snapshot = copy.deepcopy(self.content)
        self.state = "editing"
        self.changes.clear()
        return self

    def _require_editing(self) -> None:
        if self.state != "editing":
            raise RefEditError("当前不在编辑中（state=%s），不能改内容" % self.state)

    # ── 改动 ──
    def add(self, target: str, value: Any) -> Change:
        self._require_editing()
        if target in self.content:
            raise RefEditError("对象已存在：%s" % target)
        self.content[target] = copy.deepcopy(value)
        ch = Change("add", target, None, value)
        self.changes.append(ch)
        return ch

    def modify(self, target: str, value: Any) -> Change:
        self._require_editing()
        if target not in self.content:
            raise RefEditError("对象不存在：%s" % target)
        before = copy.deepcopy(self.content[target])
        self.content[target] = copy.deepcopy(value)
        ch = Change("modify", target, before, value)
        self.changes.append(ch)
        return ch

    def delete(self, target: str) -> Change:
        self._require_editing()
        if target not in self.content:
            raise RefEditError("对象不存在：%s" % target)
        before = self.content.pop(target)
        ch = Change("delete", target, before, None)
        self.changes.append(ch)
        return ch

    # ── 收尾 ──
    def commit(self) -> Dict[str, Any]:
        if self.state == "committed":
            raise RefEditError("已经提交过了")
        if self.state != "editing":
            raise RefEditError("没有可提交的编辑（state=%s）" % self.state)
        self.state = "committed"
        return {"name": self.name, "changes": len(self.changes),
                "content": copy.deepcopy(self.content)}

    def abort(self) -> Dict[str, Any]:
        if self.state == "aborted":
            raise RefEditError("已经放弃过了")
        if self.state != "editing":
            raise RefEditError("没有可放弃的编辑（state=%s）" % self.state)
        self.content = copy.deepcopy(self._snapshot or {})
        self.changes.clear()
        self.state = "aborted"
        return {"name": self.name, "restored": True,
                "content": copy.deepcopy(self.content)}

    # ── 判据辅助 ──
    def verify_restored(self, original: Dict[str, Any]) -> bool:
        """放弃后内容是否与原始一致（逐键深比较）。"""
        return self.content == original

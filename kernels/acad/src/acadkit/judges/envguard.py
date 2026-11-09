"""环境自检护栏（JUDGE_SPEC 第三节）：每条用例**前后各一次**，不一致即判失败。

这条是 AutoCAD 特有的，swkit 没有：最坏情况不是"模型没变"，而是
**"模型变了，本机 AutoCAD 配置也被改坏"**（profile 落到 `<<ACADE>>`、
`TRUSTEDPATHS` 残留、强杀留下 `.sv$` 导致每次启动弹"图形修复"）。

护栏把 §3 的六项检查落成布尔：

| 检查 | 判法 |
|---|---|
| `env_profile` | 前后都读到 `<<VANILLA>>`（读不到 = 失败，不是 SKIP） |
| `env_vars` | `TRACKED_VARS` 无漂移（含 TRUSTEDPATHS / SECURELOAD） |
| `env_documents` | 打开文档数回到用例前（自己开的都关了） |
| `env_sv` | `%TEMP%\\*.sv$` 数量不增加 |
| `env_process` | acad.exe 数量不变 |
| `env_single_instance` | 前后都是单实例（多实例 COM 会连错文档） |
| `env_no_modal` | 关文档耗时正常（>10 s 视为疑似弹了模态框；真卡死会挂住整轮） |
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from ..core import com, env


class EnvGuard:
    def __init__(self, app: Any, temp_dir: Optional[str] = None,
                 no_modal_limit_s: float = 10.0) -> None:
        self.app = app
        self.temp_dir = temp_dir
        self.no_modal_limit_s = no_modal_limit_s
        self.before_snap: Optional[Dict[str, Any]] = None
        self.case_id: Optional[str] = None

    def _snapshot(self) -> Dict[str, Any]:
        """采快照；代理失效时重新附加一次再采。

        `documents == -1` 是 `com.active_documents()` 的"读不到"标记，
        `running 但 variables 全空` 则是 ActiveDocument 代理坏了（我们一直
        留着基线文档，不可能真的没有变量）。这两种都不该被当成"环境漂移"，
        但重试后仍读不到就如实判失败（spec：读不到 != 合规）。
        """
        snap: Dict[str, Any] = {}
        for _ in range(4):
            snap = env.snapshot(self.app, self.temp_dir)
            bad = (snap.get("documents") == -1
                   or (snap.get("running") and not snap.get("variables")))
            if not bad:
                return snap
            time.sleep(0.5)
            self.app = com.refresh(self.app)
        return snap

    def before(self, case_id: str) -> Dict[str, Any]:
        self.case_id = case_id
        self.before_snap = self._snapshot()
        return self.before_snap

    def after(self, *, close_elapsed: Optional[float] = None
              ) -> Tuple[Dict[str, bool], Dict[str, Any]]:
        after = self._snapshot()
        before = self.before_snap or {}
        drift = env.diff(before, after)
        prof_before = env.profile_ok(before)
        prof_after = env.profile_ok(after)

        checks = {
            "env_profile": prof_before is True and prof_after is True,
            "env_vars": not drift,
            "env_documents": before.get("documents") == after.get("documents"),
            "env_sv": before.get("sv_count") == after.get("sv_count"),
            "env_process": before.get("process_count") == after.get("process_count"),
            "env_single_instance": before.get("process_count") == 1,
            "env_no_modal": (close_elapsed is None
                             or close_elapsed <= self.no_modal_limit_s),
        }
        detail = {
            "case": self.case_id,
            "profile_before": (before.get("variables") or {}).get("CPROFILE"),
            "profile_after": (after.get("variables") or {}).get("CPROFILE"),
            "documents_before": before.get("documents"),
            "documents_after": after.get("documents"),
            "sv_before": before.get("sv_count"),
            "sv_after": after.get("sv_count"),
            "process_before": before.get("process_count"),
            "process_after": after.get("process_count"),
            "drift": drift,
            "close_elapsed_s": (round(close_elapsed, 3)
                                if close_elapsed is not None else None),
            "no_modal_limit_s": self.no_modal_limit_s,
            "variables_after": after.get("variables"),
        }
        return checks, detail

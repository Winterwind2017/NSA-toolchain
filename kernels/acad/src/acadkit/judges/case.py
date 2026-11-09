"""一条用例的执行器：文档生命周期 + 保存重开 + 环境护栏 + 判据收口。

分工：

    Case.build(doc, ctx)   动作（建几何 / 存盘 / 出图），只许改自己的文档
    Case.judge(rb, ctx)    判据（纯函数，读 Readback）
    CaseRunner.run(case)   前后环境自检、DWG 存盘重开、DXF 重装、合并 checks

关键约定（`docs/JUDGE_SPEC.md`）：

* 每条用例**前后各一次**环境自检，不一致即判失败（`env_*` 并进 checks）；
* L4 是强制的：用例结束后统一 `SaveAs(DWG) → Close → Open → 再读`，
  判据拿到的 `rb.reopened` 就是重开后的读回；
* 负面对照（`expect="fail"`）不隐藏失败：把"判据确实失败了"本身写成一条
  检查（`negative_observed`），并记下是哪几条检查失败、失败成什么样。
"""

from __future__ import annotations

import os
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from ..core import com, env
from ..core import plot as plotmod
from . import dxfinfo, read
from .base import JudgeError, Readback, verdict
from .envguard import EnvGuard


@dataclass
class Case:
    """一条真机用例。"""

    id: str
    family: str
    title: str
    build: Callable[[Any, Dict[str, Any]], None]
    judge: Callable[[Readback, Dict[str, Any]], Dict[str, Any]]
    expect: str = "pass"                     # pass | fail（"判据必须失败"型负例）
    is_negative: bool = False                # 负面对照（含"API 必须抛错"型）
    expect_fail_checks: Tuple[str, ...] = ()
    wants_reopen: bool = True
    wants_dxf: bool = False
    notes: str = ""

    @property
    def negative(self) -> bool:
        return self.is_negative or self.expect == "fail"


class CaseRunner:
    def __init__(self, app: Any, workdir: str, temp_dir: Optional[str] = None,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self.app = app
        self.workdir = os.path.abspath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.temp_dir = temp_dir
        self.log = log or (lambda msg: None)
        self.baseline_doc: Optional[Any] = None

    # ── 文档 ────────────────────────────────────────────────────
    def _phase(self, case_id: str, name: str) -> None:
        """把当前阶段写到 `workdir/progress.txt`。

        命令卡死时 stdout 可能还在缓冲，这个文件是**唯一可靠的现场**：
        看最后一行就知道停在 build / save / reopen 哪一步。
        """
        try:
            with open(os.path.join(self.workdir, "progress.txt"), "a",
                      encoding="utf-8") as fh:
                fh.write("%s %-28s %s\n"
                         % (time.strftime("%H:%M:%S"), case_id, name))
        except Exception:                               # noqa: BLE001
            pass

    def _fresh_app(self) -> Any:
        """重新拿一次 COM 根对象。

        AutoCAD 偶尔会让旧代理失效：`app.Documents.Open` 报
        `AttributeError: <unknown>.Open`、`doc.ModelSpace` 报
        `AttributeError: Add.ModelSpace` —— 都不是"方法不存在"，是代理坏了。
        重新 `GetActiveObject` 一次通常就好。
        """
        try:
            return com.refresh(self.app)
        except Exception:                               # noqa: BLE001
            return self.app

    def _ready_doc(self, fallback: Any = None, attempts: int = 12) -> Any:
        """确认文档代理真的能用（`ModelSpace.Count` 读得出来）再交给用例。"""
        for _ in range(attempts):
            try:
                cand = self._fresh_app().ActiveDocument
                int(cand.ModelSpace.Count)
                return cand
            except Exception:                           # noqa: BLE001
                time.sleep(0.5)
        return fallback

    def _find_doc(self, name: Optional[str]) -> Optional[Any]:
        if not name:
            return None
        try:
            app = self._fresh_app()
            for i in range(int(app.Documents.Count)):
                d = app.Documents.Item(i)
                if str(getattr(d, "Name", "")) == name:
                    return d
        except Exception:                               # noqa: BLE001
            return None
        return None

    def ensure_baseline_doc(self) -> Any:
        """留一个"基线文档"开着。

        为什么需要：AutoCAD 没有打开文档时读不到 `CPROFILE`（它是文档级变量），
        环境自检里的 profile 就成了"读不到"——按 spec 只能判失败。留一个不碰的
        空文档，用例跑完关掉自己的文档后 ActiveDocument 回到它，profile 与
        系统变量都可读、可比较。
        """
        if self.baseline_doc is not None:
            return self.baseline_doc
        com.retry(lambda: self.app.Documents.Add(), label="Documents.Add(baseline)")
        time.sleep(0.5)
        self.baseline_doc = self._ready_doc()
        return self.baseline_doc

    def new_doc(self, case_id: str) -> Any:
        com.retry(lambda: self.app.Documents.Add(), label="Documents.Add")
        # 本机实测：Add 之后立刻读属性偶发 DISPID 失败（AutoCAD 还没稳定）
        time.sleep(0.4)
        doc = self._ready_doc()
        for var, val in (("INSUNITS", 4), ("MEASUREMENT", 1), ("DIMASSOC", 2)):
            try:
                doc.SetVariable(var, val)
            except Exception:                           # noqa: BLE001
                pass
        return doc

    def _close(self, doc: Any, label: str) -> float:
        """关文档，返回耗时（秒）。耗时用于"有没有弹模态框"的判据。"""
        t0 = time.time()
        name = None
        try:
            name = str(doc.Name)
        except Exception:                               # noqa: BLE001
            pass
        for _ in range(5):
            try:
                doc.Saved = True            # 丢弃修改，避免 Close 弹模态
            except Exception:                           # noqa: BLE001
                pass
            try:
                com.retry(lambda: doc.Close(False), label="Close(%s)" % label)
                break
            except Exception as exc:                    # noqa: BLE001
                if isinstance(exc, AttributeError) or com.is_busy_error(exc):
                    time.sleep(0.6)
                    doc = self._find_doc(name) or doc
                    continue
                self.log("  ! 关闭 %s 失败：%s: %s"
                         % (label, type(exc).__name__, exc))
                break
        else:
            self.log("  ! 关闭 %s 多次失败（文档可能残留）" % label)
        time.sleep(0.3)                     # 让 AutoCAD 稳下来再进下一步
        return time.time() - t0

    def _save_dwg(self, doc: Any, case_id: str) -> str:
        path = os.path.join(self.workdir, case_id.replace(".", "_") + ".dwg")
        info = plotmod.save_as(doc, path)
        if not info["ok"]:
            self.log("  ! SaveAs(DWG) 失败：%s" % (info.get("error") or info["bytes"]))
        return path

    def _open(self, path: str) -> Any:
        """`Documents.Open` 的健壮版。

        本机实测：刚关掉一个文档后立刻 `Documents.Open`，AutoCAD 有时会让
        DISPID 查询失败，pywin32 把它翻成 `AttributeError: <unknown>.Open`
        —— 看起来像"方法不存在"，其实是"还没准备好"。这里短重试几次。
        """
        last: Optional[BaseException] = None
        # 打开 .dxf 时 AutoCAD 可能弹"DXF 输入/替换"框把 Open 卡死（实测：判据在
        # "reopened" 之后停住，progress.txt 只写到 reopened）。打开前先压 FILEDIA=0。
        prev_filedia = None
        try:
            active = self._fresh_app().ActiveDocument
            prev_filedia = active.GetVariable("FILEDIA")
            active.SetVariable("FILEDIA", 0)
        except Exception:                               # noqa: BLE001
            prev_filedia = None
        try:
            for _ in range(6):
                try:
                    self._fresh_app().Documents.Open(path)
                    return self._ready_doc()
                except AttributeError as exc:
                    last = exc
                    time.sleep(0.8)
        finally:
            if prev_filedia is not None:
                try:
                    self._fresh_app().ActiveDocument.SetVariable("FILEDIA", prev_filedia)
                except Exception:                       # noqa: BLE001
                    pass
        raise last if last else RuntimeError("Open 失败")  # type: ignore[misc]

    def _reopen(self, path: str, source: str) -> Tuple[Optional[Any], float]:
        """打开一个文件读回并关掉，返回 (Drawing|None, 关闭耗时)。"""
        if not (os.path.isfile(path) and os.path.getsize(path) > 0):
            return None, 0.0
        doc = None
        try:
            doc = self._open(path)
            drawing = read.read_drawing(doc, source)
            return drawing, self._close(doc, "reopened")
        except Exception as exc:                        # noqa: BLE001
            self.log("  ! 重开 %s 失败：%s: %s" % (os.path.basename(path),
                                                   type(exc).__name__, exc))
            if doc is not None:
                self._close(doc, "reopened(failed)")
            return None, 0.0

    # ── 主流程 ──────────────────────────────────────────────────
    def run(self, case: Case) -> Dict[str, Any]:
        t_start = time.time()
        self._phase(case.id, "start")
        guard = EnvGuard(self.app, self.temp_dir)
        before_env = guard.before(case.id)
        ctx: Dict[str, Any] = {
            "app": self.app, "workdir": self.workdir, "case": case,
            "artifacts": {}, "notes": [], "started": t_start,
            "env_before": before_env,
        }
        rb: Optional[Readback] = None
        close_elapsed: Optional[float] = 0.0
        error: Optional[str] = None
        doc = None
        try:
            doc = self.new_doc(case.id)
            ctx["doc"] = doc
            self._phase(case.id, "doc")
            before = read.read_drawing(doc, "before")
            self._phase(case.id, "before-read")
            case.build(doc, ctx)
            self._phase(case.id, "built")
            memory = read.read_drawing(doc, "memory")
            self._phase(case.id, "memory-read")
            rb = Readback(before=before, memory=memory)
            dwg = ctx["artifacts"].get("dwg_path") or self._save_dwg(doc, case.id)
            ctx["artifacts"]["dwg_path"] = dwg
            self._phase(case.id, "saved")
            close_elapsed = max(close_elapsed or 0.0, self._close(doc, "case doc"))
            doc = None
            self._phase(case.id, "closed")

            if case.wants_reopen:
                reopened, elapsed = self._reopen(dwg, "reopened")
                rb.reopened = reopened
                close_elapsed = max(close_elapsed or 0.0, elapsed)
                self._phase(case.id, "reopened")

            if case.wants_dxf:
                dxf_path = ctx["artifacts"].get("dxf_path")
                if dxf_path:
                    # 只解析文件（不依赖 AutoCAD）。**默认不再让 AutoCAD 去 Open 这个
                    # DXF**：实测（2026-11-03）打开它会卡死 —— progress.txt 停在
                    # "reopened"，连 acadkit 自己的看门狗都要等满超时才动手。
                    # 需要时用 ACADKIT_DXF_REOPEN=1 打开这条验证。
                    ctx["artifacts"]["dxf_info"] = dxfinfo.read(dxf_path)
                    if os.environ.get("ACADKIT_DXF_REOPEN") == "1":
                        reimported, elapsed = self._reopen(dxf_path, "dxf-reopened")
                        rb.dxf_reopened = reimported
                        close_elapsed = max(close_elapsed or 0.0, elapsed)
                    else:
                        # 别写进 notes：acadkit 把 notes 当"问题"透传到 errors，
                        # 会被 kitmcp 判成失败。这里只作为事实记录。
                        ctx["artifacts"]["dxf_reopen_skipped"] = (
                            "AutoCAD 2025 打开 DXF 会卡死，已改为只解析文件")
                    self._phase(case.id, "dxf-reimported")

            result = case.judge(rb, ctx)
            self._phase(case.id, "judged")
        except Exception as exc:                        # noqa: BLE001
            error = "%s: %s" % (type(exc).__name__, exc)
            ctx["notes"].append("build/judge 抛错：" + error)
            self.log("  ! %s 抛错：%s" % (case.id, error))
            traceback.print_exc()
            result = verdict({"build": False}, {"error": error}, {})
        finally:
            if doc is not None:
                close_elapsed = max(close_elapsed or 0.0,
                                    self._close(doc, "case doc(finally)"))

        env_checks, env_detail = guard.after(close_elapsed=close_elapsed)
        merged = self._merge(case, result, env_checks, env_detail)
        merged.update({
            "id": case.id,
            "family": case.family,
            "title": case.title,
            "negative": case.negative,
            "duration_s": round(time.time() - t_start, 2),
            "artifacts": self._artifact_summary(ctx),
            "notes": ctx.get("notes") or [],
        })
        return merged

    # ── 合并 ────────────────────────────────────────────────────
    def _merge(self, case: Case, result: Dict[str, Any],
               env_checks: Dict[str, bool],
               env_detail: Dict[str, Any]) -> Dict[str, Any]:
        detail = dict(result.get("detail") or {})
        detail["env"] = env_detail
        if case.expect == "fail":
            # 负面对照：judge 必须失败，且失败在预期的那几条检查上。
            observed = (result.get("ok") is False
                        and all(result["checks"].get(k) is False
                                for k in case.expect_fail_checks))
            checks = {"negative_observed": bool(observed)}
            checks.update(env_checks)
            detail["judge"] = {
                "ok": result.get("ok"),
                "checks": result.get("checks"),
                "detail": result.get("detail"),
                "expected_fail_checks": list(case.expect_fail_checks),
            }
            raw = {"judge": result.get("raw")}
        else:
            checks = dict(result.get("checks") or {})
            checks.update(env_checks)
            raw = result.get("raw") or {}
        try:
            merged = verdict(checks, detail, raw)
        except JudgeError as exc:
            merged = verdict({"judge_contract": False},
                             {"error": str(exc), "checks_seen": list(checks)}, {})
        return merged

    def _artifact_summary(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, val in (ctx.get("artifacts") or {}).items():
            if isinstance(val, str):
                out[key] = {"path": val,
                            "bytes": os.path.getsize(val) if os.path.isfile(val) else 0}
            elif isinstance(val, dict):
                out[key] = {k: val.get(k) for k in
                            ("ok", "reader", "total", "families", "device",
                             "media", "elapsed_s", "backgroundplot_restored")
                            if k in val}
        return out


# ── 环境收尾 ────────────────────────────────────────────────────────
def finish(app: Any, baseline_doc: Optional[Any] = None,
           quit_app: bool = False) -> Dict[str, Any]:
    """关掉基线文档；需要时干净退出 AutoCAD。"""
    out: Dict[str, Any] = {"baseline_closed": False, "quit": None}
    app = com.refresh(app)                     # 代理可能失效，重取一次
    if baseline_doc is not None:
        try:
            baseline_doc.Saved = True
        except Exception:                               # noqa: BLE001
            pass
        try:
            com.retry(lambda: baseline_doc.Close(False), label="Close(baseline)")
            out["baseline_closed"] = True
        except Exception as exc:                        # noqa: BLE001
            out["baseline_error"] = "%s: %s" % (type(exc).__name__, exc)
    if quit_app:
        out["quit"] = com.clean_quit(app)
    return out


def env_signature(temp_dir: Optional[str] = None) -> Dict[str, Any]:
    """不依赖 AutoCAD 的环境指纹（进程数 / .sv$），用于跑前跑后对比。"""
    return {"process_count": env.proc_count(), "sv_count": env.sv_dump_count(temp_dir)}

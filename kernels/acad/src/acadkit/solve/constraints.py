"""二维几何约束求解（设计与算法参照 CADCraft `crates/constraints`）。

为什么需要：AutoCAD 完整版**没有**几何约束（那是 Mechanical 的能力），
所以"改一个尺寸、全图跟着重算"在真机驱动路线里做不到。
CADCraft 用 Levenberg–Marquardt（LM）解约束残差，这套数学与语言无关，可以搬：
我们在 Python 侧解出坐标，再让 acadkit 重画（参数驱动重建）。

约定：
* 约束 = 残差分量 rᵢ(x)；求解 = min Σrᵢ²；
* 雅可比用数值差分（实现简单、规模小够用）；
* 自由度 dof = 自由变量数 − rank(J)：0 恰好，>0 欠约束；
* **过约束/冲突必须明确失败**（`ok=False` + 原因），不许返回"差不多"的解。

暂未移植：上游的自动约束推断（`auto.rs`）与增量求解缓存——需要几何分类器，
价值低于求解器本体，留 TODO。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]


# ── 模型 ────────────────────────────────────────────────────────────
@dataclass
class Point:
    id: str
    xy: Vec2
    fixed: bool = False


@dataclass
class Segment:
    id: str
    p1: str
    p2: str


@dataclass
class Constraint:
    """一个约束产生若干残差。`value` 是目标值（距离/坐标）。"""

    id: str
    kind: str
    points: Sequence[str] = ()
    segments: Sequence[str] = ()
    value: Optional[float] = None
    value_y: Optional[float] = None

    def residuals(self, pts: Dict[str, Point], segs: Dict[str, Segment]) -> List[float]:
        P = lambda n: pts[n].xy                      # noqa: E731
        k = self.kind
        if k == "fixed":
            p = P(self.points[0])
            return [p[0] - float(self.value), p[1] - float(self.value_y)]
        if k == "coincident":
            a, b = P(self.points[0]), P(self.points[1])
            return [a[0] - b[0], a[1] - b[1]]
        if k == "horizontal":
            a, b = P(self.points[0]), P(self.points[1])
            return [a[1] - b[1]]
        if k == "vertical":
            a, b = P(self.points[0]), P(self.points[1])
            return [a[0] - b[0]]
        if k == "distance":
            a, b = P(self.points[0]), P(self.points[1])
            return [math.hypot(a[0] - b[0], a[1] - b[1]) - float(self.value)]
        if k == "parallel":
            ax, ay = _dir(P(segs[self.segments[0]].p1), P(segs[self.segments[0]].p2))
            bx, by = _dir(P(segs[self.segments[1]].p1), P(segs[self.segments[1]].p2))
            return [ax * by - ay * bx]
        if k == "perpendicular":
            ax, ay = _dir(P(segs[self.segments[0]].p1), P(segs[self.segments[0]].p2))
            bx, by = _dir(P(segs[self.segments[1]].p1), P(segs[self.segments[1]].p2))
            return [ax * bx + ay * by]
        if k == "equal_length":
            s1, s2 = segs[self.segments[0]], segs[self.segments[1]]
            return [_len(P(s1.p1), P(s1.p2)) - _len(P(s2.p1), P(s2.p2))]
        raise ValueError("未知约束类型：%s" % k)


def _dir(a: Vec2, b: Vec2) -> Vec2:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return (0.0, 0.0) if n < 1e-12 else (dx / n, dy / n)


def _len(a: Vec2, b: Vec2) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


@dataclass
class Problem:
    points: Dict[str, Point]
    segments: Dict[str, Segment] = field(default_factory=dict)
    constraints: List[Constraint] = field(default_factory=list)

    # ── 向量化 ──
    def vector(self) -> List[float]:
        out: List[float] = []
        for p in self.points.values():
            if not p.fixed:
                out.extend((p.xy[0], p.xy[1]))
        return out

    def apply(self, x: Sequence[float]) -> None:
        i = 0
        for p in self.points.values():
            if p.fixed:
                continue
            p.xy = (x[i], x[i + 1])
            i += 2

    def residuals(self) -> List[float]:
        out: List[float] = []
        for c in self.constraints:
            out.extend(c.residuals(self.points, self.segments))
        return out

    def jacobian(self, h: float = 1e-7) -> List[List[float]]:
        """返回 m×n（m=残差数，n=自由变量数）。"""
        x0 = list(self.vector())
        base = self.residuals()
        cols: List[List[float]] = []
        for j in range(len(x0)):
            x = list(x0)
            step = h * max(1.0, abs(x[j]))
            x[j] += step
            self.apply(x)
            after = self.residuals()
            cols.append([(after[i] - base[i]) / step for i in range(len(base))])
        self.apply(x0)
        return [[cols[j][i] for j in range(len(x0))] for i in range(len(base))]

    def dof(self) -> int:
        n = len(self.vector())
        if not self.constraints:
            return n
        return n - _rank(self.jacobian())


def _rank(rows: List[List[float]], tol: float = 1e-9) -> int:
    m = [list(r) for r in rows]
    if not m:
        return 0
    nrow, ncol, rank = len(m), len(m[0]), 0
    for col in range(ncol):
        pivot = next((r for r in range(rank, nrow) if abs(m[r][col]) > tol), None)
        if pivot is None:
            continue
        m[rank], m[pivot] = m[pivot], m[rank]
        pv = m[rank][col]
        m[rank] = [v / pv for v in m[rank]]
        for r in range(nrow):
            if r != rank and abs(m[r][col]) > tol:
                f = m[r][col]
                m[r] = [a - f * b for a, b in zip(m[r], m[rank])]
        rank += 1
        if rank == nrow:
            break
    return rank


def _solve_linear(A: List[List[float]], b: List[float]) -> Optional[List[float]]:
    n = len(b)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[pivot][col]) < 1e-14:
            return None
        M[col], M[pivot] = M[pivot], M[col]
        pv = M[col][col]
        for j in range(col, n + 1):
            M[col][j] /= pv
        for r in range(n):
            if r != col and abs(M[r][col]) > 1e-16:
                f = M[r][col]
                for j in range(col, n + 1):
                    M[r][j] -= f * M[col][j]
    return [M[i][n] for i in range(n)]


@dataclass
class SolveResult:
    ok: bool
    iterations: int
    residual_norm: float
    dof: int
    message: str
    values: Dict[str, Vec2]

    @property
    def max_residual(self) -> float:
        return self.residual_norm


def solve(problem: Problem, *, max_iter: int = 300, tol: float = 1e-10,
          lambda0: float = 1e-3) -> SolveResult:
    """Levenberg–Marquardt。收敛判据是**残差**，不是"跑完就算成功"。"""
    x = problem.vector()
    r = problem.residuals()
    cost = sum(v * v for v in r)
    lam = lambda0
    it = 0

    def converged(res: List[float]) -> bool:
        return (not res) or max(abs(v) for v in res) < tol

    for it in range(1, max_iter + 1):
        if converged(r):
            break
        J = problem.jacobian()
        m, n = len(J), len(J[0])
        JTJ = [[sum(J[k][i] * J[k][j] for k in range(m)) for j in range(n)]
               for i in range(n)]
        JTr = [sum(J[k][i] * r[k] for k in range(m)) for i in range(n)]
        for i in range(n):
            JTJ[i][i] += lam * (1.0 + abs(JTJ[i][i]))
        delta = _solve_linear(JTJ, [-v for v in JTr])
        if delta is None:
            lam *= 10.0
            if lam > 1e12:
                return SolveResult(False, it, math.sqrt(cost), problem.dof(),
                                   "雅可比奇异且阻尼无效（约束冲突或几何退化）",
                                   _snapshot(problem))
            continue
        trial = [x[i] + delta[i] for i in range(n)]
        problem.apply(trial)
        r_new = problem.residuals()
        cost_new = sum(v * v for v in r_new)
        if cost_new < cost:
            x, r, cost = trial, r_new, cost_new
            lam = max(lam * 0.3, 1e-12)
        else:
            problem.apply(x)
            lam = min(lam * 5.0, 1e12)

    residual = math.sqrt(sum(v * v for v in r)) if r else 0.0
    ok = converged(r)
    return SolveResult(ok, it, residual, problem.dof(),
                       "收敛" if ok else "残差降不下去（过约束或冲突）",
                       _snapshot(problem))


def _snapshot(problem: Problem) -> Dict[str, Vec2]:
    return {k: (round(p.xy[0], 9), round(p.xy[1], 9))
            for k, p in problem.points.items()}


# ── 参数表达式（对照上游 expr.rs，只做四则与括号）─────────────────────
def evaluate_expr(expr: str, vars_: Dict[str, float]) -> float:
    """安全的参数表达式求值：只允许数字、变量名、+ - * / ( ) 与空格。"""
    import ast as _ast

    allowed = set("0123456789.+-*/() eE_")
    for ch in expr:
        if ch not in allowed and not ch.isalpha() and ch not in vars_:
            raise ValueError("表达式含非法字符：%r" % ch)
    tree = _ast.parse(expr, mode="eval")

    def walk(node) -> float:
        if isinstance(node, _ast.Expression):
            return walk(node.body)
        if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, _ast.Name):
            if node.id not in vars_:
                raise ValueError("未知变量：%s" % node.id)
            return float(vars_[node.id])
        if isinstance(node, _ast.UnaryOp) and isinstance(node.op, (_ast.USub, _ast.UAdd)):
            v = walk(node.operand)
            return -v if isinstance(node.op, _ast.USub) else v
        if isinstance(node, _ast.BinOp):
            a, b = walk(node.left), walk(node.right)
            if isinstance(node.op, _ast.Add):
                return a + b
            if isinstance(node.op, _ast.Sub):
                return a - b
            if isinstance(node.op, _ast.Mult):
                return a * b
            if isinstance(node.op, _ast.Div):
                if abs(b) < 1e-15:
                    raise ZeroDivisionError("表达式除以 0")
                return a / b
        raise ValueError("表达式只支持四则与括号：%s" % expr)

    return walk(tree)

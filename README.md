# acadkit

AutoCAD 2025 自动化内核（库 + CLI + 可选 MCP），设计与
[swkit](https://github.com/Winterwind2017/solidworks-agent-kit) 同构：

> **每个能力都必须有可复现的判据；说不清判据的，不许标 verified。**

当前状态：**P0（设计与盘点）已完成，执行代码尚未开始**。
P0 只做只读分析，不碰 AutoCAD、不写驱动代码。

## P0 产出（已就绪）

| 文件 | 内容 |
|---|---|
| [`docs/registry.yaml`](docs/registry.yaml) | **60 条能力**：后端、状态、判据草案、证据出处 |
| [`docs/BACKEND_MATRIX.md`](docs/BACKEND_MATRIX.md) | 4 条执行路径（com/lisp/headless/file）× 20 个能力族 |
| [`docs/JUDGE_SPEC.md`](docs/JUDGE_SPEC.md) | 判据四级 + 按族模板 + 环境自检 + 负面对照 |
| [`docs/P0_SUMMARY.md`](docs/P0_SUMMARY.md) | 结论：能不能做、工作量、必须定的规矩 |
| `docs/_extract.json` | 从三处源码抽出的能力清单（机器可读） |

## 结论摘要

| 指标 | 值 |
|---|---|
| 能力条目 | 60 |
| `verified`（判据说得清） | 30 |
| `usable_unjudged`（可用但缺判据） | 22 |
| `pending` | 2 |
| `dead`（官方缺口） | 6 |
| 后端覆盖 | com 48 / lisp 31 / headless 14 / file 2 / python 1 / csg 1 |

## 三处与 swkit 的本质差异

1. **执行路径不是一条**：com（ActiveX 晚绑定）/ lisp（命令层）/ headless
   （accoreconsole+ezdxf）/ file。每条能力都要声明后端。
2. **判据不是体积**：AutoCAD 用"计数 → 属性读回 → 几何自洽 → **重开文件复核**"四级。
3. **多一层风险：环境污染**。profile（`<<VANILLA>>`）、`TRUSTEDPATHS`、
   `SECURELOAD`、`.sv$` 残留都会跨会话影响本机。判据必须包含**环境自检**。

## 目录约定（P1 起）

```
src/acadkit/
├─ core/        COM 晚绑定、profile 守卫、clean_quit、错误类型
├─ backends/    com / lisp / headless / file 路由
├─ judges/      四级判据实现（按族）
├─ registry.py  从 docs/registry.yaml 载入
└─ cli/         子命令（与 MCP 同一批实现）
tests/          每个能力一条真机用例 + 环境自检
```

## 边界

`acadkit` **不注册第二个 AutoCAD MCP**。与 `autocad-mcp` 的关系是复用其后端，
对外 CLI 优先；MCP 面与 `autocad-mcp` 二选一（两个 MCP 同连 AutoCAD 会互相抢
文档与命令队列）。

## 运行前提

- AutoCAD **完整版**（非 LT；LT 没有 `vlax-*`/ActiveX）
- 启动配置必须是 `<<VANILLA>>`（`acad.exe /p "<<VANILLA>>"`），不是 `<<ACADE>>`
- 单实例运行（多实例会导致 COM 连错文档）

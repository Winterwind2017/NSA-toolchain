# 架构

四层：**设计（先算）→ 内核（手）→ hub（统一入口）→ 技能（脑子）**。

设计层不驱动任何 CAD。`design/design_calc` 出力和尺寸，`design/knowledge` 给出机构与标准件的查法，技能 `ww-nsa-design` 规定七段流程。算完之后才进入下面的内核。

```
                     ┌──────────────────────────────┐
   你的 agent ──────▶│ hub/  (stdio MCP, 1 个端点)   │
   (Claude/Cursor/   │  nsa_hub_status + 9 个 kit    │
    Codex/DSH/...)   └──────┬───────────────────────┘
                            │ 每个 kit 一个子进程（按需拉起）
        ┌───────────┬───────┼────────┬───────────┬──────────┐
        ▼           ▼       ▼        ▼           ▼          ▼
      acad         sw      nx       gx        codesys    autoshop
   (AutoCAD)  (SolidWorks) (NX) (GX Works3) (CODESYS)  (AutoShop)
        │           │       │        │           │          │
        └───────────┴───────┴────────┴───────────┴──────────┘
                     各留 COM / journal / 脚本引擎 / CLI
```

## 1. 内核（`kernels/<kit>/`）

每个内核是同一个骨架：

```
kernels/<kit>/
  src/<kit>kit/          库：能力实现，一个能力一个模块
    caps.py 或 caps.yaml 能力注册表（id → 实现 + 判据）
  mcp/ 或 servers/       MCP 端点（可选，hub 自己也会起）
  docs/
    VERIFY.md            每条能力"怎么算通过"
    PITFALLS.md          踩过的坑（不踩第二次）
    UNSUPPORTED.md       已证伪/不可用的路径（别浪费时间）
  tests/                 离线测试（不需要真机）
  tools/                 生成/审计脚本
```

约定：

- **一个能力 = 一个 id + 一个实现 + 一组判据**；判据失败就是失败，没有"看起来成功"。
- 能力 id 在技能里也被引用，`scripts/check_skills.py` 会核对两边是否一致（内部矛盾 FAIL，跨仓漂移 WARN）。
- 离线可跑的部分（DFM、B-rep、图纸、FEA、解析）与真机部分严格分开，测试里也一样。

## 2. hub（`hub/`）

- `nsa_mcp_hub/servers/nsa_hub_mcp.py` —— 聚合端点：对外一个 MCP，对内按需拉起 9 个 kit 子进程。
- `nsa_mcp_hub/adapters/` —— 每个 kit 一份适配器，把内核能力翻译成 MCP 工具。
- `nsa_mcp_hub/contracts.py` —— **统一返回结构**：

```python
{"ok": bool, "kit": str, "capability": str,
 "reads": {...},      # 读到的原始值（判据的输入）
 "checks": [{"check": str, "got": ..., "want": ..., "ok": bool}],
 "errors": [...], "seconds": float}
```

`ok = ok and all(c["ok"] for c in checks) and not errors`。
调用方（agent）只需要看 `ok` 和 `checks`，不需要理解每个工具。

- `nsa_mcp_hub/acceptance/` —— 验收 runner：`python -m nsa_mcp_hub.acceptance --kit sw [--only id]`。
- `nsa_mcp_hub/paths.py` —— 所有路径的唯一来源（仓库相对 + 环境变量覆盖）。

## 3. 技能（`skills/`）

- `skills/nsa-toolchain/` —— **路由**：只回答"用哪个域、什么顺序、怎么判"。
- `skills/ww-nsa-design/` —— 非标设计流程：需求、方案、选型计算、再交给 CAD 技能。
- `skills/ww-*/` —— 其余域技能：配方、判据、证伪清单。
- CAD/PLC 域技能带 `capabilities.json`（能力快照）与 `tools/check_skill.py`。设计技能没有软件注册表，计算判据在 `design/tests/`。

技能与内核的关系是"**文档不重复、判据不漂移**"：能力 id 必须存在于内核注册表，
由 CI 的 `scripts/check_skills.py --check` 守住。

## 4. 质量门

| 门 | 命令 | 覆盖 |
|---|---|---|
| 设计计算 | `pytest design/tests` | 缸径、惯量、丝杆寿命、节拍、公差、疲劳 |
| 仓库级脚本单测 | `pytest scripts/tests` | doctor / install_skills / nsa CLI |
| hub 单测 | `PYTHONPATH=hub pytest hub/tests` | JSON-RPC、server、tools |
| acad 离线离线三件套 | `pytest kernels/acad/tests/test_{docs,reports,offline}.py` | 注册表自检、文档新鲜度、离线能力 |
| 技能一致性 | `python scripts/check_skills.py --check` | 路由覆盖 / 快照↔注册表 |
| 真机验收 | `python -m nsa_mcp_hub.acceptance --kit <kit>` | 需要装对应软件 |

真机验收不在 CI 里跑（需要商业软件与许可证），由人/agent 在真机上跑并把结果写进各内核 `docs/`。

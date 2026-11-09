# RECIPES — 加一条能力的标准流程

> 目标：**能力 = 动作 + 判据 + 真机用例 + 文档**，四件套一起进仓库。
> 只想"先试试"可以，但不要标 `verified`。

## 0. 先查有没有

```bash
acadkit list --family dim     # 已实现的能力
acadkit registry --status dead
```

## 1. 登记到 registry（先写清判据）

`docs/registry.yaml` 加一条：

```yaml
  - id: dim.new_thing
    family: dim
    backend: [com]
    status: usable_unjudged
    source: "AddDimXxx(...)"
    judge: "读回 Measurement = 期望值；重开再读一致"
    evidence: "matrix #NN / 探针日期"
```

先写 `judge` 再写代码 —— 写不出判据就说明这条能力还不该标 verified。

## 2. 写动作（`src/acadkit/build/`）

一个函数 `build_xxx(doc, ctx)`，参数从 `ctx["params"]` 读（CLI/MCP 要能覆盖），
需要落文件的写 `ctx["artifacts"]`：

```python
def build_new_thing(doc, ctx):
    p = ctx.get("params") or {}
    ms = ms_of(doc)
    add(ms, "AddDimXxx", pt(*p.get("p1", (0, 0, 0))), label="AddDimXxx")
```

约定：
- COM 调用一律走 `com.retry` / `helpers.add`（忙等待）；
- 命令行用 `(vl-cmdf "…")`，不要 `(command "…")`；
- 不加载 `.lsp` 文件（不碰 `TRUSTEDPATHS`）。

## 3. 写判据（`src/acadkit/judges/`）

能复用就复用：

| 形状 | 判据 |
|---|---|
| 新增一个实体 + 属性 | `generic.judge_new_entity(type, object_name, expected={...})` |
| 多类型计数变化（符号） | `generic.judge_delta(expect={"LINE": 3, "TEXT": 1})` |
| 命名表新增/改行 | `generic.judge_named_table(table, name, expected={...})` |
| 3D 体积 | `solid.judge_solids(expected=[...])` |
| 布尔 | `solid.judge_boolean(expected_volume=...)` |

必须满足 `docs/JUDGE_SPEC.md`：`ok` 由 `verdict()` 的 `all(checks)` 算出、
`detail` 有可人工核对的数字、失败保留 `raw`。

## 4. 接到 caps（`src/acadkit/caps.py`）

```python
Cap("dim.new_thing", "dim", "新标注：Measurement", "L1–L4",
    b_dim.build_new_thing,
    lambda rb, ctx: j_g.judge_new_entity(
        rb, type_name="NEWDIMENSION", object_name="AcDbNewDimension",
        expected={"Measurement": _P(ctx, "expected")}),
    {"p1": (0, 0, 0), "expected": 60.0}),
```

`params` 里是默认值；CLI 用 `--param expected=50` 覆盖。

## 5. 真机跑

```bash
acadkit cap dim.new_thing                       # 单条
acadkit cap dim.new_thing --param expected=50   # 换参数
acadkit run --only dim                          # 整族
python tests/live_judges.py --only dim.new_thing --keep
```

失败时看 `_scratch/<run>/progress.txt`（停在哪个阶段）和
`results.json` 的 `checks/detail/raw`。

## 6. 加离线测试

`tests/test_judges.py` 里加两条：正例（构造读回值 → `ok=True`）和
**反例**（改坏一个读数 → `ok=False` 且失败在预期检查项上）。
"不能失败的判据，通常也证明不了成功"。

## 7. 提升状态 + 重新生成文档

```bash
# registry.yaml: status: usable_unjudged → verified，evidence 写清真机日期
python tools/gen_readme_counts.py
python tools/gen_unsupported.py
python -m pytest tests -q
git add -A && git commit -m "cap: dim.new_thing（真机通过）"
```

`pre-push` 会核对 README 计数与 UNSUPPORTED 是否最新，不一致直接拒推。

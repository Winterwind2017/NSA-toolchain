# nxkit

UG NX 2512 自动化内核：**Python journal + 几何判据**。
宿主侧只负责拼任务、起 NX、跑判据；所有碰 NX 的代码都在 `nxkit.runtime`，
由 `run_journal.exe` 在 NX 进程内执行。

> 与 [acadkit](https://github.com/Winterwind2017/autocad-agent-kit) 同构：
> 能力表 + 四级判据 + 真机证据，不写"没验证过"的能力。

## 为什么是 Python journal

- NX 2512 自带 CPython 3.12 与 `NXOpen_*.pyd`（113 个扩展模块，117 MB），
  **不需要编译**，`run_journal -py` 直接跑；
- 一次 NX 会话约 **13 s**，10 条能力只占 **0.6 s** 计算，适合"一次会话跑一批"；
- 需要 .NET/C++ 才有的能力时，再走 `cs`/`cpp` journal（同一协议）。

## 安装

```bash
pip install -e .
nxkit status          # 找 run_journal、看能力数（不启动 NX）
nxkit selftest        # 离线自检：动作/判据/负例
```

要求：本机装 NX（默认路径 `D:\Program Files\Siemens\DesigncenterNX2512`，
可用 `NXKIT_RUN_JOURNAL` 覆盖）、许可证可检出。

## 用法

```bash
nxkit list                          # 能力清单
nxkit cap block.create              # 跑一条：建 -> 读回 -> 存盘重开 -> 判据
nxkit run --only assembly           # 跑一族
nxkit run                           # 全部，一次 NX 会话
```

`nxkit run` 输出：

```
27/27 通过  (会话 13.8s, 退出码 1)
  PASS block.create           0.19s
  PASS boolean.subtract       0.05s
  ...
```

## 许可证档位

NX 的每个特征调用都会 `JAM_reserve_uf_license("<feature>")`（反编译
`UF_MODL_create_block1` 证实），所以"能不能做"首先是"有没有这个 feature"。

```bash
nxkit licenses          # 读 SPLM .dat，看本机有哪些 feature、能力族缺不缺
```

本机 `.dat`（`C:\ProgramData\Siemens\siemens_SSQ.dat`）实测 **4,420 个 feature**，
覆盖本仓库用到的全部四类：

| 能力族 | 需要的 feature | 本机 |
|---|---|---|
| 建模 / 布尔 / 曲线 / 特征 / 草图 / 曲面 | `solid_modeling` | 有 |
| 制图（图纸页、视图） | `drafting` | 有 |
| 装配 | `assemblies` | 有 |
| 部件 / 属性 / 测量 / 检查 / 导出 / 文件 | `gateway` | 有 |

`selftest` 会自动做这项预检（读不到 `.dat` 时跳过，不误报）。

## 判据怎么算

| 级别 | 内容 | 例子 |
|---|---|---|
| L1 | 计数 | 实体数 1、面 6、边 12 |
| L2 | 属性读回 | 特征名 `Block(0)`、字符串属性 |
| L3 | 几何自洽 | 体积 100000（100×50×20）、圆柱 37699.11 |
| L4 | 存盘重开 | 重开后体积/属性仍一致 |

判据只比 **NX 里读回来的读数**（`MeasureManager` / `GetBodies` / 属性），
不看返回值、不看异常。

## 能力（92 条，全部真机通过）

| 族 | 能力 |
|---|---|
| part | `part.new` |
| sketch | `sketch.rect` `sketch.extrude` `sketch.circle_extrude` `sketch.constraint` `sketch.horizontal` `sketch.vertical` `sketch.equal_length` `sketch.perpendicular` `sketch.dimension` `sketch.fixed` `sketch.collinear` `sketch.concentric` `sketch.midpoint` `sketch.parallel` `sketch.equal_radius` `sketch.tangent` |
| solid | `block.create` `block.two_bodies` `cylinder.create` `cone` `sphere` `cone_frustum` |
| boolean | `subtract` `union` `intersect` `two_tools` `intersect_two` |
| curve | `curve.line` `curve.arc` `curve.ellipse` `curve.hyperbola` `curve.parabola` |
| surface | `surface.bounded_plane` |
| feature | `extrude.rect` `extrude.ring` |
| assembly | `asm.add_component` `asm.two_components` `asm.three_components` `asm.four_components` `asm.nested` |
| drawing | `drawing.sheet` `drawing.sheet_a4` `drawing.base_view` `drawing.view_isometric` |
| attr | `attr.string` `attr.int` `attr.double` `attr.logical` `attr.on_body` `attr.on_feature` `attr.delete` `attr.update` |
| measure | `measure.mass` `measure.face_area` `measure.face_single` |
| inspect | `body.topo` `body_type` |
| export | `export.step` `export.step_ap203` `export.iges` `export.acis` `export.stl` |
| file | `file.roundtrip` |

## 结构

```
src/nxkit/
├─ caps.py            能力表（id/参数/期望读数/层级）
├─ judges.py          判据（只比读数，含 L4 重开）
├─ session.py         起 run_journal、超时杀进程、收 result.json
├─ live.py            一次会话跑一批
├─ protocol.py        job/result JSON 契约
├─ cli.py             status/list/registry/cap/run/selftest
└─ runtime/           在 NX 进程内
   ├─ runner.py       读 job → 逐条执行 → 立刻落盘
   └─ actions.py      22 条能力的实现（唯一碰 NXOpen 的地方）
```

## 已知边界

- `run_journal` 成功时也返回退出码 1（NX 自己的状态），**以 result.json 为准**；
- Python 绑定是 NXOpen 的**子集**（如 `ufs.Modl` 只有 213 个方法），
  缺的能力走 `cs`/`cpp` journal；
- 每个 UF 调用内部 `JAM_reserve_uf_license("<feature>")`，能力可用性取决于许可证；
- 详细坑见 [`docs/PITFALLS.md`](docs/PITFALLS.md)。

## 许可

MIT，见 [`LICENSE`](LICENSE)。

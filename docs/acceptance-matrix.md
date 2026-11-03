# 验收矩阵（kitmcp 0.2.0）

两条并行的验收线：**固定用例**（真实场景，39 条）和**能力扫描**（把每条能力/命令
当用例跑一遍，`--sweep`，共 306 条可生成）。

## 固定用例：42/42

| kit | 用例 | 耗时 | 说明 |
|---|---|---|---|
| sw | 15 | 194 s | 拓扑自审 / 参数化 / 回滚 / 选择 / 特征图 / 索引 / Simulation 自检 / **FEA 求解** / STEP 导出 |
| acad | 15 | 118 s | 块插入/定义、几何、标注、文字、图层、三维、投影、BOM 表、DXF/PDF 导出 |
| nx | 2 | 16 s | 状态 + 块建模（6 条几何判据） |
| gx | 2 | 204 s | ST 粘贴转换 + 全部转换 |
| codesys | 4 | 2 s | 服务、建工程、工程信息、工程树 |
| autoshop | 4 | 166 s | 状态、工程树、编译、apply（写程序→编译→诊断） |

最近一次全量：**42/42 通过，714.9 s**（`_runs/acceptance-20261103-150359.json`）。

## 能力扫描（`--sweep`）

```powershell
python -m kitmcp.acceptance --kit acad --sweep            # 57 条
python -m kitmcp.acceptance --kit nx --sweep --sweep-max 20
```

| kit | 扫描用例 | 实测 | 备注 |
|---|---|---|---|
| acad | 57 | **57/57**（472 s） | 58 条能力，1 条负例不扫 |
| nx | 146 | **146/146**（1997 s，一轮干净全量） | 11 条制图曾因缺 `import NXOpen.Drawings` 全挂，已修；`_runs/acceptance-20261103-223706.json` |
| gx | 42 | **42/42**（7242 s） | 干净全量一轮跑通；单条 57–595 s |
| codesys | 15 | **15/15** | 23 条里 8 条需真机/网关（`online.*`、`symbols.create`），扫描跳过 |
| autoshop | 0 | — | 不是能力表模型，只有固定用例 |

合计可生成 **302 条**（acad 57 + nx 146 + gx 42 + codesys 15 + 固定 42）。

### 扫描逼出来的三个真 bug（都已修）

1. **NX 制图 11 条全挂**：`AttributeError: module 'NXOpen' has no attribute 'Drawings'`
   —— NX 的 `NXOpen` 是包，子模块必须显式 `import NXOpen.Drawings`。
2. **nx 经 MCP 必超时**（直跑 16 s）：`run_journal` 继承了 JSON-RPC 的 stdin，卡在
   `communicate()`。四级修法：所有 spawn 都 `stdin=subprocess.DEVNULL`。
3. **DXF 判据卡 45 s+**：`ezdxf` 在"stdout 被重定向 + COM 已初始化 + 读线程在跑"
   的上下文首次 import 会死锁；改为服务器启动时预热。

### 环境依赖（扫描跳过，固定用例或需真机）

* `codesys online.*`：本机没配网关，`login` 必然失败（"网关没有正确配置"）。
* `codesys symbols.create`：工程里没有 PLC 设备树，父对象不接受符号配置。
* `gx`：每条都会前台拉起 GX Works3，40–120 s，跑完才轮到下一条。

### GX 全量扫描（2026-11-03，7028 s + 复跑 1303 s）

首轮 38/42，4 条失败全部定位并修掉：

| 用例 | 首轮 | 原因 | 修法 |
|---|---|---|---|
| `program.import_fb` | TIMEOUT 400 s | 本身要 438 s（XML 建程序+FB+转换） | 扫描超时提到 900 s |
| `program.import_fb_instance` | ERROR 无响应 | **GX Works3 继承了 MCP 的 stdout**，把启动日志写进 JSON-RPC 流 | spawn 时 `stdout/stderr=DEVNULL` |
| `program.write_ladder` | TIMEOUT >600 s | 先 `save()` 后 `convert_all()`：未转换工程 GX 拒存，弹框把 `session.save` 的等待循环拖到十几分钟 | 改成**先转换再存盘**；`session.save` 存不下去时立刻报错 |
| `build.error_messages` | ERROR 无响应 | 同上（stdout 污染）；且前一条超时后服务器重启的竞争 | 同上 |

修完复跑 4/4 通过；随后**一轮干净的全量**（默认超时 900 s）跑出 **42/42，7242 s**
（`_runs/acceptance-20261103-211633.json`），最慢 4 条：write_ladder 595 s、
import_fb 434 s、batch.new_projects 386 s、multi_programs 366 s。

### 汇总（2026-11-03）

固定 42/42、acad 57/57、nx 146/146（一轮）、gx 42/42（一轮）、codesys 15/15 =
**全部 302 条都至少跑过一遍且通过**，0 失败。nx 与 gx 都各自有**单轮干净全量**的报告。


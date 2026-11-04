# 上游测试对照（145 个用例，0 失败）

`tests/parity/run_parity.py` 在本机跑三组上游测试，用来回答一个问题：

> hub 里 vendored 的几何代码、以及代理的 EPLAN / CATIA 代码，到底还是不是上游那份？

## 跑法与结果（2026-11-04 11:20 实测）

```powershell
python tests\parity\run_parity.py            # 三组全跑
python tests\parity\run_parity.py --group sw # sw | eplan | catia
```

```
=== hubsw（hub vendored 几何）：18 通过 / 0 失败 ===
=== EPLAN（离线 5 个套件）：  68 通过 / 0 失败 ===
=== CATIA（非 COM 的 unittest）：59 通过 / 0 失败 ===
合计：145 通过 / 0 失败
```

## 三组分别测什么

### 1. hubsw —— hub 自己那份，18 个用例

`tests/parity/hubsw/` 是上游 `MCP/Solidworks/tests` 里 **6 个纯几何测试**的副本，
只改了 import 前缀（`solidworks_mcp.` → `nsa_mcp_hub.adapters.hubsw.`）：

| 上游测试文件 | 覆盖内容 |
|---|---|
| `test_feature_graph.py` | 图编译、前向引用必须被拒、旋转轴歧义必须被拒 |
| `test_involute_gear.py` | 分度/基圆/外径/齿根半径、渐开线齿廓端点、采样齿宽收敛、11 个特征树 |
| `test_gearbox.py` | 传动比 6.0、两级中心距 60/80、末特征 `ReducerKeywayCut` |
| `test_part_generators.py` | block/cylinder/tube/flange/stepped_shaft 五种都能编译；法兰 8 孔 → 9 个实体 |
| `test_output_shaft.py` | 总长 333、7 段直径、末特征 `EndBlindHoleDia3Depth12` 深度 12 |
| `test_primitives.py` | 球体用确定性旋转；球+齿轮合成一个多实体零件 |

这组的意义：**hub 的 vendored 副本不是残件**——上游对这些模块有多少断言，这边一条不少地跑过。

### 2. EPLAN —— 直接跑上游那 5 个离线套件，68 个用例

| 套件 | 内容 |
|---|---|
| `test_intent.py` | 设计意图校验：端点身份、相/PE 分离、导线容量、PLC 地址与公共组、正反转约束 |
| `test_native_snapshot.py` | 快照比对：重复边、页/功能/引脚身份、容量、语义网分组 |
| `test_help_search.py` | 本地 FTS5 索引与检索 |
| `test_bridge.py` | 发现文件校验（伪 pid / 过期 start_filetime 必须拒绝） |
| `test_transport_windows.py` | 定长帧管道读写与超时 |

这些是 hub 的 eplan kit **直接代理**的代码，所以跑通等于代理的那一半是可信的。

### 3. CATIA —— 非 COM 的 7 个 unittest，59 个用例

`test_contracts / compatibility / surfaces / runtime / simulation / modeling / server_contract`。
碰真机 COM 的部分（需要装 CATIA）不在其中——这台机器没有 CATIA。

## 没搬的部分（以及为什么）

| 来源 | 没搬 | 原因 |
|---|---|---|
| Solidworks | `test_com_runtime` / `test_inspection` / `test_interactive*` / `test_metadata` / `test_save_routing` / `test_single_document_mode` / `test_server_compat` | 要连 SolidWorks 或要跑上游 server 进程 |
| EPLAN | `test_authoring_*`（22+2+1） | 要 C# 编译器 + EPLAN API 程序集（本机没有 EPLAN 平台） |
| EPLAN | `test_mcp_stdio` | 起上游 server 子进程，与 hub 的代理入口不同 |
| CATIA | 需要 `CNEXT`/COM 的用例 | 本机没装 CATIA |
| UG | `test_nx_bridge`（39）/ `test_bridge_client`（5） | 要 NX 或 NX 的远程桥 |

这些在 `docs/parity-report.md` 里记为待办，条件具备时再补。

## 和验收用例的关系

两套东西互补，别混淆：

* **本页这 145 个**：验证「代码没被改坏」——纯逻辑，秒级，任何机器都能跑；
* **`nsa_mcp_hub.acceptance`（61 条）**：验证「工具真的能干活」——走 MCP 协议、要判据、
  有依赖真机的用例；覆盖率见 `docs/acceptance-coverage.md`（当前 41/609 = 6.7%）。

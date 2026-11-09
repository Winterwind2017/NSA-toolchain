# Verified command ids

Extracted from `AutoShop.exe` resources (MENU 128…, RT_TOOLBAR 241, ACCELERATOR 9)
and confirmed by dispatching them to a live process.  ``docs/RECON.md`` §2
describes the extraction; `tools/scan_menu_ids.ps1` + `tools/build_catalog.py`
reproduce it.

Dispatch with `AutoShop.command(id)` (alias: `AutoShop.cmd("compile_all")`).

## Project

| id | label | alias |
| --- | --- | --- |
| 32858 | 新建工程(&N) | `new_project` |
| 32859 | 打开工程(&O)... | `open_project` |
| 32860 | 关闭工程(&C) | `close_project` |
| 32861 | 保存工程(&S) | `save_project` |
| 32862 | 工程另存为(&A)... | `save_project_as` |
| 33181 | 工程属性(PLC类型)(&T) | `project_props` |
| 33838 | 打包工程档案 | `pack_project` |
| 33839 | 解压工程档案 | `unpack_project` |

## Files / documents

| id | label | alias |
| --- | --- | --- |
| 57603 | 保存文件(&F) | `save_file` |
| 57602 | 关闭文件(&E) | `close_file` |
| 33031 | 导入(&I) | `import` |
| 33032 | 导出(&U) | `export` |
| 33186 | 生成下载文件(&D) | `make_download_file` |
| 33507 | 比较本地工程(&M) | `compare_local` |
| 33594 | 比较PLC中工程(&N) | `compare_plc` |

## Views

| id | label | alias |
| --- | --- | --- |
| 32883 | 切换为指令列表编辑器 | `view_il` |
| 32884 | 切换为梯形图编辑器 | `view_ladder` |
| 32885 | 切换为步进状态图编辑器 | `view_sfc` |
| 33367 | 查看 → 符号编址(&A) | `view_symbols` |
| 32953 | 内置梯形图(&O) | — |

> **Correction (2026-10-26, runtime-verified).** An earlier revision of this table listed
> `32867/32868/32869` as the view switches. That is wrong: those three IDs are the SFC
> 并行分支 / 并行汇合 / 梯形图块 insert commands — posting them on a program document is a
> silent no-op (or really inserts an SFC branch). The view switches are `32883/32884/32885`,
> which is what `autoshopkit.app.CMD` has always used. `32867` also appears in the menu
> resource labelled 查看 → 指令列表, which is how the stale rows got there.
>
> Separately: `CMD["run"]` (33009) currently collides with `CMD["upload"]`, while this table
> says run=33600 / stop=33601. **Unverified** — do not trust either until measured; the
> `run`/`stop` aliases are not used by any verified path today.

## PLC / build

| id | label | alias | accelerator |
| --- | --- | --- | --- |
| 32992 | 编译(&C) | `compile` | Ctrl+Alt+F7 |
| 32993 | 全部编译(&A) | `compile_all` | Ctrl+F7 |
| 33008 | 清理编译信息(&E) | `clean_compile` | — |
| 33009 | 上载(&U)... | `upload` | — |
| 32882 | 下载(&D)... | `download` | Ctrl+F8 |
| 33006 | 程序校验(&V) | `program_check` | — |
| 33600 | PLC 运行(&R) | `run` (menu 调试→运行) | — |
| 33601 | PLC 停止(&S) | `stop` | — |

> Note: two ids appear twice in different menu templates (MFC ids are global, and
> some labels are reused).  The aliases above are the ones exercised.

## Debug / monitoring

| id | label | alias | accelerator |
| --- | --- | --- | --- |
| 32893 | 调试 → 监控(&M) | `monitor` | Ctrl+F3 |
| 32910 | 监控状态暂停 | `monitor_pause` | — |
| 32908 | 在线修改模式(&L) | `online_edit` | — |
| 32895 | 写入(&F)... | `write` | Ctrl+F4 |
| 33030 | 添加到监控表(&E) | `monitor_table_add` | — |

## Ladder editor elements

| id | label | alias |
| --- | --- | --- |
| 32931 | 常开触点(&O)... | `no_contact` |
| 32932 | 常闭触点(&F)... | `nc_contact` |
| 33927 | 立即常开触点 | — |
| 33926 | 立即常闭触点 | — |
| 32841 | 应用指令(&I)... | `application_ins` |
| 32935 | 竖线(&V) | `vertical_line` |
| 32930 | 删除竖线(&D) | `delete_vertical` |

The 常开触点 / 常闭触点 dialogs are `#32770` with
`ComboBox 1045` (元件名称: device class), `Edit 1065` (元件编号) + spinner 1066,
`确定` = id 1, `取消` = id 2.  The combo is owner-draw, so pick items with real
keyboard input rather than `CB_GETLBTEXT`.

## Debugging / simulation

| id | label | note |
| --- | --- | --- |
| 33198 | 离线调试 | offline debugger (simulator mode); **no effect on H3U** — see `docs/RECON.md` §10 |
| 33022 | 通讯设置 → 系统选项 | tabbed options dialog; contains `启动离线调试后下载程序` (1377), `监控前先进行程序校验` (1374), `监控数据显示格式` (1376) |
| 33130 | 电话拨号设置 | modem link |
| 33201 / 33202 / 33592 | 固件升级 / 下载FPGA / 生成CVxxx下载文件 | PLC maintenance |
| 33320 | 无线通讯配置 | — |

Document-local toolbars (not the frame's command table): the 符号表 document
exposes ids `33359 / 33360 / 33364 / 33480 / 33479`; posting `WM_COMMAND` for them
opens nothing, and they are disabled while the table is empty.

## Editing (MFC standard ids)

57643 撤消 · 57644 恢复 · 57635 剪切 · 57634 复制 · 57637 粘贴 · 57632 删除 ·
57641 替换 · 33842 增量粘贴 · 57665 退出

## Complete id map

`recon/catalog_commands.json` holds all 261 menu commands with their labels,
their MFC status-bar hints and their accelerator keys; `recon/resources/menus_full.txt`
is the raw menu tree (78 templates) and `recon/resources/strtab_exe.txt` the full
string table.

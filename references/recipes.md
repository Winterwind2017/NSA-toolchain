# 配方

每条都是本机实测过的调用序列。`app` 指 `autoshopkit.AutoShop` 实例。

## 1. 先看工程长什么样（不启动 AutoShop）

```python
from autoshopkit import hcp, projectfile

index = hcp.read_project(r"D:\work\demo\demo.hcp")
print(index["fields"]["GCMModal"], index["fields"]["Capbility"])   # H3U/H5U, 步容量
print([f["filename"] for f in index["files"]][:10])                # 组件清单
print(len(projectfile.read_symbols(r"D:\work\demo")))              # 符号数
```

判据：`GCMModal` 与现场一致；`files` 里点名的 `.IL`/`.LD` 在盘上真的存在。

## 2. 读 H5U 的程序文本

```python
log = projectfile.read_il_log(r"D:\work\demo")
programs = projectfile.split_il_programs(r"D:\work\demo", log)
print(programs["MAIN"][:5])
```

判据：`len(programs["MAIN"])` 等于 `Compile\MAIN.compile` 里记录的指令数。
不等说明拆错了（多半是 `MAINEND`/`SRET`/`FBRET` 边界被跳过）。

## 3. 读梯形图元件（两代都行）

```python
ladder = projectfile.read_ladder(r"D:\work\demo\MAIN.LD")
for element in ladder["elements"][:8]:
    print(element["kind"], element["text"], element["node_a"], element["node_b"])
```

判据：`kind ∈ {1,2,3,4}`；每个 `element["text"]` 都能在对应程序的 IL 里找到。

## 4. 打开程序（H3U）

```python
app = AutoShop.launch(r"D:\work\demo\demo.hcp", wait=120)
assert app.doctors()["il_editor"] is True          # 没有 Scintilla 就不是 H3U
doc = app.open_program("MAIN")                     # 返回新文档句柄，None = 没打开
text = app.program_il(strict=True)
```

判据：`open_program` 返回非 None，且 `program_il` 行数 > 0。

## 5. 写程序并证明它生效（H3U）

```python
app.apply_program(source, save=False)
assert app.program_il(strict=True).split() == source.split()   # 回读一致
ok, lines = app.compile()
assert ok, lines[-3:]
app.save()                                                    # 报告 changed_files
```

判据：回读一致 + 编译 0 错误 + `changed_files` 里出现该程序部件。

## 6. 改符号表 / 监控表

```python
app.add_symbol("M100", "启动按钮", note="HMI")
rows = app.symbols()                          # 重新读整表
assert any(r["symbol"] == "M100" for r in rows)
```

判据：重新读表能读到，不是"点完就完事"。

## 7. 编译并定位错误

```python
ok, lines = app.compile()
parsed = diagnostics.parse(lines)
print(parsed["summary"])          # (0)错误, (25026)步占用/(200000)总容量…
print(parsed["errors"][:3])       # [{code, message, program, line}]
```

判据：`summary` 里的错误数；不要用返回码判断（编译失败也可能返回 True）。

## 8. 生成离线下载文件

```python
path = app.make_download_file(dest=r"D:\work\demo.updown")
```

判据：文件存在且大小 > 0；**不要**把它当成"已下载到 PLC"。

## 9. 收尾

```python
app.close()        # 关工程；再不行 stop() 杀进程释放 .hcp 锁
```

## 10. 体检

```python
report = app.project_check()          # 需要编译
print(report["counts"])               # {"errors":0,"warnings":3,...}
print(report["findings"][:5])         # 每条带 code/program/line/message
```

## 11. 批量写符号表（>19 行）：走「导入Excel」

网格默认只有 19 个数据行，逐格 `add_symbol` 建不出新行（见 pitfalls「符号表只有 19 行」）。
一次性的做法：

```bash
python scripts/import_symbol_table.py --csv out\symbols.csv --hcp D:\work\demo\demo.hcp
```

手工等价：

```python
import autoshopkit.app as A

# 1) 按导出模板生成 .xls：r0 = (空)|符号|地址|注释；数据行 = 序号|符号|地址|注释
#    （BIFF8，用 xlwt 写；符号名先规范到 <=8 字符并去重）
# 2) 打开 符号表 文档，命令投给 frame
A.w.post(app.frame, A.w.WM_COMMAND, 33183)        # 导入Excel
# 3) 「打开」对话框里文件名框是 cid=1148（另存为才是 1001），要递归找 Edit
#    填路径 -> 回车 -> 确认框点「确定」-> cmd("save_project")
rows = app.symbols(source="file")                  # 秒级，读 VarList.gdt
assert len(rows) == 74
```

判据：`symbols(source="file")` 的行数与内容逐条一致；再写一个引用这些符号的程序并
`compile()` 到 `(0)错误`——回读 IL 会看到符号被解析成地址（`SB_START → X61`），
这是符号表真正生效的独立证据。

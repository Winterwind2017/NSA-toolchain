# 梯形图正文（`LadderBlocks`）的 `V1:` DSL —— 实测规格

> 来自三处一致证据：我们自己用键盘画出来的块（probe151/152/161/162/163）、
> 真实产线工程（`D:\某设备厂\…\某产线项目(上盖位)_6.110.gx3`）、以及改顺序后的对照实验。
> 读法实现：`src/gxkit/ladder.py`（离线，不开 GUI）。

## 1. 位置

`.gx3` 是 ZIP；梯形图程序的正文在 `*_LDDB.db`（SQLite）的 `LadderBlocks` 表：

| 列 | 含义 |
|---|---|
| `id` | `_guid/…` |
| `pos` | 块顺序（1000000.0 是 END 块，正文块常见 500000/1024/2304/3584） |
| `blocktype` | **0 = 正文块，5 = END 块** |
| `data` | `V1:` 开头的文本 DSL |
| `rowsize` / `translated` / `ConvTarget` | 行数 / 是否已转换 / 转换目标 |

同库还有 `IstBlocks`（指令表视图，本次未见内容）、`McMcrTable`（MCMCR）、
`FoldBlockTable`（折叠）、`DeletedBlockTable`、`NopTemporaryTable`。

## 2. 形状

```
V1:<头>:a:X:a:X:c:Y:cb{ fg=fg{ dim=<列>x<行>: es=[ ... ] } :vs=[ v{pos=列,行} ... ] }
```

- **头**：`V1:` 后跟一串数字与 `字母:软元件` 组成的软元件表（顺序 = 首次使用顺序）。
  实测：`6:1:1:1:1:1:1:a:X:a:X:c:Y`（串联两触点一线圈）／
  `8:1:1:1:1:1:1:1:1:a:X:a:X:c:Y:a:X`（多一条并联支路）／
  `5:1:1:3:3:1:a:X:MOV:K_1:D`（应用指令 MOV K1 D0）。
- `dim=<列>x<行>`：网格尺寸。插并联后会从 `12x1` 变成 `12x2`。
- `es=[…]`：元素列表，**按列优先顺序**排列，空位也显式写出：`e{s=-:pos=列,行}`。
- `vs=[…]`：竖线（并联的连接导线），`v{pos=列,行}`。

## 3. 元素

| DSL | 含义 | 关键字段 |
|---|---|---|
| `e{s=ce{op=ct{…}:args=[d{s=#:a=N:vt=nn}]}:pos=C,R}` | 触点 | `a=N` = 软元件地址 |
| `e{s=ce{op=cl{…}:args=[d{s=#:a=N:vt=nn}]}:pos=C,R}` | 线圈 | 同上 |
| `e{s=ce{op=cl{…:as=[as{vt=A16}:as{vt=A16}]}:args=[c{s=#:v=1:si=s}:d{s=#:a=0…}]}:pos=C,R}` | 应用指令（例：`MOV K1 D0`） | `c{…v=1}` = 常数 K1；`d{a=0}` = D0 |
| `e{s=-:pos=C,R}` | 空位 | — |

`ct{op=#:ct=a:as=[as{vt=Abl}]}` 里的 `ct=a` / `vt=Abl` 在本次所有样本里都一样，
不随软元件变化；**软元件信息只在 `args` 的 `d{a=N}` 与头的软元件表里**。

## 4. 已验证的构造顺序（GUI 侧，`program.write_ladder`）

1. **UIA `Invoke` 工具栏按钮**：`常开触点` / `常闭触点` / `常开触点OR` / `常闭触点OR` /
   `线圈` / `应用指令`（F5/F7 对"格位"挑剔，会用「执行位置不正确。」拒绝，不要用）。
2. 点画布格位：`x = canvas.left + 84 + 28*列`，`y = canvas.top + 46 + 22*行`
   （84/28/46/22 都是本机 150% 缩放下的实测值；`canvas` = `m_splitterControl` 下面积最大的子元素）。
3. 键入软元件（应用指令则整条 `MOV K1 D0` 走剪贴板粘贴）→ 回车 → **Esc 清放置模式**。
4. 顺序**必须**是：串联触点 → 端子 → 并联支路。
   反例：先插并联再放端子时，OR 会被静默丢弃，并把「线圈」按钮变成禁用态。

## 5. 转换错误原文（本 DSL 相关）

| 现象 | 输出面板原文 | 错误代码 |
|---|---|---|
| F5 落在步号列/无效格 | 对话框「执行位置不正确。」 | — |
| 只有线圈直接接左母线 | `请不要与左母线直接连接。` | — |
| 有元素但结构不成立 | `存在无法转换的梯形图。请修改程序。` | `0x11031F01` |
| 未定义标签 | `使用了未定义的标签。` | `0x110E1A20` |

## 6. 读回判据

`gxkit.ladder.read_blocks(path)` → `[{blocktype, pos, cols, rows, devices,
instructions, elements:[{col,row,op,kind,addr,const}], verticals}]`，
`summarize()` 给一行人类可读摘要（如 `-[ ]-a0@0,0 -[ ]-a1@1,0 -( )-a0@2,0`），
`count_kinds()` 数触点/线圈个数。**判据只认这些读数 + `Progress.txt` 的 errors**。

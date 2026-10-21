# AutoCAD 判据规范（JUDGE SPEC）

> swkit 的判据是"几何量变没变"（体积/面数/包围盒）。
> AutoCAD **没有体积这种单一总账**，判据必须换形态：**计数 → 属性读回 → 重开文件复核**。
> 本文规定 acadkit 里什么叫"这条能力算通过"。

## 〇、三条总原则

1. **判据必须是读回来的值，不是返回值。**
   `SaveAs` 返回 `True` 但文件可能是 0 字节；`AddTable` 返回对象但可能在别的布局里。
2. **写完必须重开再读一次。** AutoCAD 的内存模型与 DWG 落盘结果会不一致
   （尤其是块属性、表格、标注关联）。这就是"复读式判据"。
3. **环境必须还原，并且自检。** 判据不只判"图形对不对"，还要判
   "profile/系统变量/进程状态有没有被改坏"。这条 swkit 没有，AutoCAD 必须有。

## 一、判据四级（从弱到强，逐级叠加）

| 级 | 名称 | 做法 | 能证明什么 |
|---|---|---|---|
| **L1** | 计数 | `ModelSpace.Count` / 按类型计数 / 表记录数 | 东西多了没（**最弱，只排除"完全没做"**） |
| **L2** | 属性读回 | 读 `TypeName`、`Center`/`Radius`/`TextString`/`Measurement`/`InsertionPoint` | 东西做对了没 |
| **L3** | 几何自洽 | 面积≈πR²、体积≈A×h、两段之和=总长、三视图长对正 | 数值对不对（**手工可算才用**） |
| **L4** | 复读一致 | 存盘 → `Close`+重开 → 再读 L2/L3 | 落盘后仍对（**AutoCAD 必需**） |

**验收线**：

* `status: verified` 的能力，必须至少做到 **L2**，且能 L4 的都补 L4；
* `usable_unjudged` 的能力，目前只做到 L1 或没做 L2 —— P1 要补到 L2；
* 只做到 L1 的**不许标 verified**（这正是 SW 那边"特征数+1 就宣布成功"的翻版）。

## 二、按能力族的判据模板

### 2.1 几何图元（line/circle/arc/polyline/rect/ellipse/hatch）

```
L1: 实体数 = before + n
L2: TypeName 匹配；关键几何属性读回（端点/Center/Radius/闭合位）
L3: 圆 area ≈ πR²（容差 1e-6 相对）；矩形 area = w×h；多段线 length 手算
L4: SaveAs → 重开 → 重复 L2/L3
```

### 2.2 标注（dim.*）

```
L1: 标注计数 +1（按 DimType 分）
L2: TypeName（ROTATEDDIMENSION/DIAMETRICDIMENSION/…）+ Measurement
L3: Measurement ≈ 输入尺寸；直径标注 ≈ 2R；角度 ≈ 输入弧度
L4: 重开后 Measurement 不变（标注关联性）
     注意：DIMASSOC=2 时 Measurement 由关联几何决定，改写几何后应自动更新
```

### 2.3 公差 / 形位公差

```
L2: 标注的 Tolerance 字段（UpperLimit/LowerLimit）或 TextOverride 读回
    GD&T：实体类型 = ACDBFCF，文字含 {\Fgdt; 符号码
L3: 配合代号：fit_deviation() 表值对照（H7@50 → +0.025 / 0）
    **超范围必须抛错，不许猜**
L4: 重开后文字不丢（`%%v`/DIMPOST 容易在落盘时错位）
```

### 2.4 表格 / BOM

```
L1: 表对象计数 +1
L2: 行列数；逐单元格 GetText 与输入比对
L3: 汇总列 = 各行之和；件数 = 明细行数 − 1（表头）
L4: 重开后单元格文字不丢（ACDBTABLE 的 SetText 在落盘后会丢格式类内容）
```

### 2.5 块 + 属性

```
L1: Blocks 表 +1；BlockReference +1
L2: 每个 Attdef 的 TagString/TextString 读回一致
L3: 属性个数 = 定义里的 Attdef 数（缺一个就是假成功）
L4: 重开后属性仍在（-INSERT 时属性可能丢失）
```

### 2.6 3D 实体 / 布尔

```
L1: 3DSOLID 数（布尔后应减少）
L2: TypeName = 3DSOLID
L3: 体积（MASSPROP 或 GetBoundingBox+解析式）
    union: V ≈ VA + VB − V∩；subtract: V ≈ VA − V∩；intersect: V ≈ V∩
    容差按 1% 相对
L4: 重开后体积不变（布尔结果在落盘时要 ACIS 校验）
```

### 2.7 导出（dwg/dxf/pdf）

```
L0: 文件存在 + size > 0 + mtime 变化（防"导到旧文件"）
L1: 文件头魔数
    DWG  → `AC10`（AC1015/AC1032…）
    DXF  → 含 `SECTION` + `HEADER` + `ENTITIES`
    PDF  → `%PDF-`
L2: DXF 用 ezdxf 读回实体计数 == 内存计数（**这是最强的一条**）
    PDF 页数（用最小 PDF 解析或 pdftotext）
L3: PDF 页面尺寸 ≈ A3（842×595 pt 或 1191×842 pt）
```

> ⚠️ PDF 有个专门的坑：**没显式配布局就出白纸**。判据必须包含"页面尺寸 + 非空白"，
> 只看"文件存在"会把白纸当成功。

### 2.8 投影视图（自建 CSG）

```
L3（这里 L1/L2 不够）:
  长对正：主视 width == 俯视 width
  高平齐：主视 height == 左视 height
  宽相等：俯视 height == 左视 width
  隐藏线：被遮挡线段必须落在虚线层，且遮挡前后的段数符合遮挡关系
L4: 重开后上述关系仍成立
```

## 三、环境自检（AutoCAD 专有，必须每次跑）

每条用例前后各做一次，**不一致即判失败**：

| 检查项 | 读法 | 期望 |
|---|---|---|
| 配置（profile） | `(getvar "CPROFILE")` | `<<VANILLA>>`（**不是 `<<ACADE>>`**） |
| TRUSTEDPATHS | `(getvar "TRUSTEDPATHS")` | 与用例前一致（**不许残留**） |
| SECURELOAD | 同上 | 与用例前一致（本机只能命令行设、且持久化，**绝不碰**） |
| 打开文档数 | `Documents.Count` | 用例后回到用例前（关掉自己开的） |
| 未保存提示 | 关闭时是否弹模态 | 不弹（弹了说明没清干净） |
| `.sv$` 残留 | `%TEMP%\*.sv$` 数量 | 不增加（强杀会留下 → 下次启动弹"图形修复"） |
| 进程 | 用例后 acad.exe 是否存活 | 按用例声明（交互式用例要保持存活） |

> 历史教训：`Stop-Process -Force` 强杀后 `.sv$` 会留在 `%TEMP%`，AutoCAD 每次启动
> 扫到就弹"图形修复"，点关闭也不清。断根三件套见 `acad_clean_shutdown.py`。

## 四、负面对照（和 swkit 一样必须做）

每条能力至少一条"应该失败"的用例：

| 能力 | 负例 | 期望 |
|---|---|---|
| `fit_code` | `H7@600mm`（超范围） | **抛错**，不许返回近似值 |
| `export.pdf` | 不配布局直接 PlotToFile | 页面尺寸判据不通过（白纸） |
| `block.insert_with_attributes` | 属性个数少一个 | L3 不通过 |
| `dim.diametric` | 用 `AddDimLinear`（不存在） | 调用直接报错 |
| `layer.create` | 用早绑定 `gen_py` 设 Color | `AttributeError`（证明晚绑定是必需的） |
| `constraint.*` | 发 `GEOMCONSTRAINT` | 命令不存在 |

**不能失败的判据，通常也证明不了成功**——这条从 swkit 搬过来，一字不改。

## 五、判据代码的落地形态（P1）

```python
# 每个能力一个 judge 函数，返回证据字典（和 swkit 的 verified 返回同构）
def judge_circle(before, after) -> dict:
    return {
        "ok": ...,
        "checks": {"count": ..., "type": ..., "geometry": ..., "reopen": ...},
        "detail": {"radius_mm": ..., "area_mm2": ...},
    }
```

约定：

* `ok` 只能是 `all(checks.values())`，**禁止**在别处手动置 `True`；
* `detail` 里必须有**人能核对**的数字（半径/面积/体积/页数），不能只有布尔；
* 判据失败时保留原始读回值，方便定位是"没做"还是"做错"。

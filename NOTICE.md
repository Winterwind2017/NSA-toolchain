# NOTICE

本仓库整体以 **MIT** 许可发布，见根目录 [`LICENSE`](LICENSE)。

## 一、本仓库内部许可

每个内核与技能目录下都保留各自的 `LICENSE`（同为 MIT，Copyright (c) 2026 Winterwind2017）：

```
kernels/{sw,acad,nx,gx,codesys,autoshop}/LICENSE
skills/ww-*/LICENSE
```

## 二、吸收自外部项目的内容

| 上游 | 许可 | 吸收方式 | 义务履行 |
|---|---|---|---|
| [beclab/cadcraft](https://github.com/beclab/cadcraft) | MIT OR Apache-2.0（双许可，择一） | 只吸收**方法、行为规格与数据模型**，不搬几何内核代码 | 见 [`kernels/acad/ATTRIBUTION.md`](kernels/acad/ATTRIBUTION.md) 与 [`docs/CADCRAFT_MINE.md`](kernels/acad/docs/CADCRAFT_MINE.md) |

未吸收任何 GPL / AGPL / 商业许可代码。

## 三、运行时依赖

本仓库**不打包**第三方 Python 包，按需 `pip install`：

- 通用：`pyyaml`、`pytest`（测试）
- Windows COM：`pywin32`
- 数值/网格：`numpy`、`gmsh`（FEA 划网格）
- 可选：`cadquery`/`OCP`（B-rep 与 STEP）、`sfepy`、`skfem`、`matplotlib`

各依赖遵循其自身许可证（多为 BSD/MIT/Apache-2.0）。若分发二进制或镜像，请一并附带对应许可文本。

## 四、商标声明

AutoCAD®（Autodesk）、SOLIDWORKS®（Dassault Systèmes）、UG NX®（Siemens）、
MELSOFT GX Works3®（Mitsubishi Electric）、CODESYS®（CODESYS GmbH）、
Inovance AutoShop®（汇川技术）、EPLAN®（EPLAN Software & Service）、
CATIA®（Dassault Systèmes）等均为其各自权利人的商标。

本项目通过各软件的**官方自动化接口**（COM / ActiveX / 脚本引擎 / CLI）驱动本机已安装的软件，
与上述公司**无隶属或背书关系**；使用前请自行确认你所持许可证允许自动化调用。

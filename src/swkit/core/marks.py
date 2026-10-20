"""swkit.core.marks —— 选择标记（selection marks）常量

这是整个项目里**最容易错、也最值钱**的一张表，来自官方帮助
`IFeatureManager::FeatureLinearPattern4/5` 的 Remarks（`sldworksapi.chm`）：

| 选择方式 | 选**特征** | 选**组件** |
|---|---|---|
| `IModelDocExtension::SelectByID2` | 方向1=1、方向2=2、**要阵列的特征=4**、偏移参考=2097152、种子参考=8388608 | **要阵列的组件=1**、**方向=2 和 4** |
| `IFeature::Select2` | 同上 | — |
| `ISelectData::Mark` + `IComponent2::Select4` | — | 组件=1、方向=2/4 |

**特征和组件的标记刚好相反**。按"特征"的标记去选组件，SolidWorks 会把 mark=4 当成
"方向 2"，而方向 1 从未选中 → 调用必然 no-op，且 `GetSelectedObjectCount2` 恒为 1
（这就是本项目卡了两轮的真正原因）。

其它已实测的约定：
* 辅助实体（面、边、轴、圆边）多数用 **mark=1** 就能被特征识别；
* `FeatureLinearPattern5` 的 `DName1/DName2` 要传**字符串 `"NULL"`**，不是空串；
* 组件在 `SelectByID2` 里的全名必须是 `组件名@装配标题(去扩展名)`，只给组件名返回 False。
"""

from __future__ import annotations

__all__ = [
    "FEATURE_DIR1", "FEATURE_DIR2", "FEATURE_TO_PATTERN",
    "COMPONENT_TO_PATTERN", "COMPONENT_DIR1", "COMPONENT_DIR2",
    "OFFSET_REFERENCE", "SEED_REFERENCE", "AUX_ENTITY",
    "NULL_DIMENSION_NAME",
]

# ── 阵列"特征" ────────────────────────────────────────────────
FEATURE_DIR1 = 1
FEATURE_DIR2 = 2
FEATURE_TO_PATTERN = 4
OFFSET_REFERENCE = 2097152
SEED_REFERENCE = 8388608

# ── 阵列"组件"（与上面相反）──────────────────────────────────
COMPONENT_TO_PATTERN = 1
COMPONENT_DIR1 = 2
COMPONENT_DIR2 = 4

# ── 通用 ─────────────────────────────────────────────────────
AUX_ENTITY = 1               # 面/边/轴/草图线段当辅助实体时的默认标记
NULL_DIMENSION_NAME = "NULL"  # FeatureLinearPattern5 的 DName1/DName2 占位值

# 相对 solidworks-automation-skill 补进的能力

对方是 SolidWorks 专用的 v2.2.0。这里是 NSA-toolchain v1.4.0。
下表只记对方有、这里原来没有的项。状态以本机 SolidWorks 2025（33.4.1）的读回为准。

| 能力 | 现在放在哪 | 状态 |
|---|---|---|
| 直齿轮实体 | `sw_spur_gear` | 已验证。m=2、z=12、厚 8 mm，体积 4079.97 mm³，小于齿顶圆柱 |
| 近似链轮实体 | `sw_sprocket` | 已验证。12 齿、节距 12.7 mm、厚 6 mm，体积 12442.06 mm³ |
| 假成功门禁 | `design/gapfill.py` `reject_false_success` | 离线测试。声称成功但体积没变则失败。不是对方那 1045 项测试套件 |
| 运动结果是否可交付 | `motion_samples_ok` | 离线测试。结果过期或采样少于两点则失败。读取运动算例原来就有 |
| 钻孔面板孔表 | `holes_from_cylinders` | 离线测试。按圆柱面半径归并孔径和个数 |
| 尺寸公差文字 | `parse_tolerance` | 离线测试。认 `10±0.05` 和 `10 +0.02/-0.01` |
| 改名预览、另存路径 | `rename_preview` / `copy_target` | 离线测试。不写文件。新名字为空或撞车、目标路径相同，都失败 |
| 中文 DXF 文字 | `cjk_text_issues` | 离线测试。中文没有大字体、两行文字贴在一起，都记问题 |
| 无 SolidWorks 的 STL | `write_box_stl` | 离线测试。ASCII STL，文件头是 `solid`。STEP 仍走已有的 cadquery 出口，没装就不假装写出 |
| 预览页 | `write_preview_page` | 本地 HTML，只显示已经抓到的窗口帧。不是对方的 CAD Studio 安装包 |
| 语义选边 | `edges_in_band` | 离线测试。按边长区间挑边 |
| 可变半径圆角 | `sw_fillet_edges` | 未验证。60×40×12 板上调用后体积仍是 28800 mm³ |
| 整圆圆角 | 同上，`kind=full_round` | 接口有，未做成本机几何变化 |
| 筋 | `sw_rib` | 未验证。`InsertRib` 返回 0，体积不变 |
| 弹簧实体 | `helix_length` / `helix_points` | 只有螺旋线长度和点，没有扫成 SolidWorks 弹簧体 |
| 形位公差投影带 | `sw_gtol_frame` | 未验证。本机类型库没有投影公差带和公共基准 |
| 焊件与规格 | `sw_structural_member` | 已在 v1.3.3 验证，不是这次新补的缺口 |

对方的 CAD Studio 桌面程序、安装器和 12 条黄金流程没有搬进来。那些是一套独立产品，不是把上面这些几何调用再写一遍就能等价的。

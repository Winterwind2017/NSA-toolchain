# 工具表面（nsa-mcp-hub 0.2.0 / P0–P8）

> 自动生成，勿手改。聚合网关 `nsa-mcp-hub` 把下面**八家**合并成 **579 个工具**
> （八家合计去重 + 1 个 `nsa_hub_status`；各家自带的 `kit_runtime` 被聚合层取代）。
> `ug` / `catia` 是 2026-11-04 从 CAD-Agent-Hub 补进来的两块（代理模式，见 `_contrib/README.md`）。
>
> 自动生成，勿手改。生成器 `nsa-mcp-hub/adapters/capgen.py`，策展清单 `capcuration.py`。

| kit | 工具 | 任务级 | 说明 |
|---|---|---|---|
| **sw** | 176 | 172 | 165 原有 + 9 个 hub 语义增强 + 2 个运行时自检（固定用例 15/15） |
| **acad** | 52 | 49 | 58 条能力 → 49 个工具（sweep 57/57） |
| **nx** | 65 | 62 | 146 条能力 → 60 个工具（sweep 146/146） |
| **gx** | 46 | 43 | 42 条能力 → 42 个工具（sweep 采样 6/6） |
| **ug** | 83 | 82 | CAD-Agent-Hub 的 NX MCP 代理：CAM 16 / 机床 20 / 钣金 6 / 装配约束 2 / run_python 等（需 NX 交互式会话 + .NET 桥；未起桥则 SKIP） |
| **catia** | 56 | 55 | CAD-Agent-Hub 的 CATIA V5 MCP 代理：建模/曲面/原生 Analysis（本机未装 CATIA，验收 SKIP） |
| **codesys** | 59 | 56 | 77 条命令 → 56 个工具（sweep 15/15） |
| **autoshop** | 41 | 40 | 24 个 CLI verb + 17 个聚焦变体（固定用例 4/4） |
| **合计** | **437** | **420** | |

## sw（170 个任务工具）

| 工具 | 参数 | 说明 |
|---|---|---|
| `sw_document_info` | — | 当前文档概览：标题、类型、特征数、实体数、组件数。

    判据用计数而不是返回值——SolidWorks 很多"成功"的调用返回 Non |
| `sw_pattern_component` | kind, count, spacing, angle_deg, component_index | 组件阵列（verified）。kind=linear\|circular；spacing 单位米；angle_deg 角度。

    内部 |
| `sw_mirror_component` | plane, component_filter, mirror_type | 镜像组件（verified）。mirror_type：0=包围盒中心 1=质心 2=组件原点。 |
| `sw_api` | op, params | 透传高层 API（**unverified**）：op 是 `SolidWorksApp` 的方法名。

    例：{"op": "new |
| `sw_new_drawing` | model, template, view, x, y | 从零件建图并插主视图（出图夹具）。中文模板只认本地化视图名（`*前视`）。 |
| `sw_add_center_mark` | x | 中心标记（verified）：判据 `IView.GetCenterMarks` 计数 +1。 |
| `sw_add_centerline` | — | 中心线（verified）：判据 `IView.GetCenterLines` 计数 +1。 |
| `sw_add_datum_feature` | — | 基准符号（verified）：判据 `IView.GetDatumTagCount` +1。 |
| `sw_add_gtol` | — | 形位公差（verified）：判据 `IView.GetGTolCount` +1。 |
| `sw_add_weld_symbol` | — | 焊接符号（verified）：判据 `IView.GetWeldSymbolCount` +1。 |
| `sw_add_surface_finish` | x, y | 表面粗糙度（**unverified**）：调用会执行，但本机没有可读计数，无法证明符号生成。 |
| `sw_note` | text, x, y | 注释（verified）：判据 文本读回 + 位置读回。 |
| `sw_add_annotation` | text, x, y | 图纸注释（verified，与 sw_note 同一实现）。 |
| `sw_add_auxiliary_view` | — | 辅助视图（verified）：`CreateAuxiliaryView()` 零参、靠选择集；判据视图数 +1。 |
| `sw_create_section_view` | plane, offset | 剖视图（verified）：`CreateSectionViewData` + `CreateSectionView`，成功后自动复位。 |
| `sw_add_broken_view` | orientation, position, size | 断裂视图（verified）：判据是 `GetBreakLines` 数量（**不新增视图**）。 |
| `sw_add_drawing_dimension` | x, y | 图纸尺寸（verified）：选两条边 → `AddDimension2`；判据 `GetDisplayDimensions` +1。 |
| `sw_add_hole_table` | x, y | 孔表（verified）：先 `ActivateView` 再 `InsertHoleTable2`；判据表格数 +1。 |
| `sw_add_balloon` | x, y | 自动球标（verified）：先 `InsertBomTable2`（7 参、`BomType` 必须 1/2/3），
    再**选中视 |
| `sw_check_interference` | expected | 装配干涉检查（verified）：分开 120mm→0、重叠 20mm→1、完全重合→1。

    走 `IAssemblyDoc.Int |
| `sw_fix_component` | component_index | 固定组件（verified）：判据 `IsFixed=True`。 |
| `sw_show_all_components` | — | 显示全部组件（verified）：判据是所有组件 `IsHidden(False)=False`。 |
| `sw_move_component` | delta_x, part_path | 平移组件（verified，三轴校验 + 临时件清理）。

    用"变换拷贝法"绕开 IMathUtility；`AddComponen |
| `sw_explode_assembly` | — | 自动爆炸（verified）：判据是爆炸视图数 +1。

    注意 `AutoExplode` 在 pywin32 下是**属性**，读 |
| `sw_add_drawing_view` | model_path, view_name, x, y | 图纸加视图（verified）：API 在 IDrawingDoc，中文版只认本地化视图名。 |
| `sw_add_bom_table` | x, y | 插 BOM 表（verified）：需装配图；BomType=0 无效，用 1/2/3。 |
| `sw_cut_extrude` | depth, through_all, flip_side | 切除拉伸（verified）：先选中草图；判据体积必须下降。

    坑：`UseAutoSelect` 必须 True（否则只选草图会静 |
| `sw_extruded_surface` | depth, through_all | 拉伸曲面（verified）：需草图；走 FeatureExtruRefSurface3（22 参，草图 mark 0）。 |
| `sw_planar_surface` | — | 平面区域曲面（verified）：需闭合草图；判据曲面数 +1。 |
| `sw_mirror` | plane | 镜像**实体**（verified）：判据 实体数 +1。

    与 `sw_mirror_feature`（镜像特征）不同。选择标记： |
| `sw_export_iges` | path | 导出 IGES（verified）：判据 文件 >200B 且头部含 `SolidWorks IGES`。

    必须走 `SaveAs |
| `sw_mirror_feature` | plane | 镜像特征（verified）：判据 体积必须翻倍。

    选择标记（官方 Remarks）：待镜像特征 = **1**，镜像面/基准面  |
| `sw_revolve` | angle_deg | 旋转凸台（verified）：草图需含中心线；判据 体积>0 且小于同外径实心圆柱。

    `FeatureRevolve2` 的 5  |
| `sw_sketch_circular_pattern` | count, radius, angle_deg | 草图圆周阵列（verified）：9 参真实签名，三个 Dim 传 None，须 comtypes。 |
| `sw_revolved_surface` | angle_deg | 旋转曲面（verified）：需草图+中心线；判据曲面数 +1。 |
| `sw_scale_body` | factor | 整体缩放（verified）：必须先选中实体，否则几何不变（假成功）。 |
| `sw_move_body` | dx_mm, dy_mm, dz_mm, copy, copies | 平移/复制实体（verified）：判据 包围盒位移 = 请求值。

    坑：TransX/Y/Z 是**字面米制位移**（1.0=10 |
| `sw_combine_bodies` | operation | 组合实体（verified）：判据 实体数 -1 且体积在并集范围内。

    坑：OperationType 用 swBodyOpera |
| `sw_delete_body` | body_index | 删除实体（verified）：判据实体数 -1。 |
| `sw_sketch_offset` | offset_mm, outward | 草图偏移（verified）：先选中草图实体；判据线段数增加（4→8）。 |
| `sw_sketch_linear_pattern` | x_count, y_count, x_spacing_mm, y_spacing_mm | 草图线性阵列（verified）：12 参真实签名；判据线段数按份数增加。 |
| `sw_sketch_convert_entities` | chain | 转换实体引用（verified）：先选中模型边/面，再调用 `SketchUseEdge3(Chain, InnerLoops)`。

   |
| `sw_sketch_trim` | x, y | 草图裁剪（verified）：判据是线段总长/数量变化。 |
| `sw_fillet` | radius | 边圆角（verified）：先选中若干条边；判据 体积必须下降。

    坑：`FeatureFillet3` 有**两套同名签名**—— |
| `sw_chamfer` | distance, angle_deg | 边倒角（verified）：先选中若干条边；判据 体积必须下降（面数+边数同增）。

    坑：`InsertFeatureChamfer |
| `sw_sketch_fillet` | radius | 草图圆角（verified）：需两条线段选中；判据线段数 +1。 |
| `sw_sketch_chamfer` | distance, angle_deg | 草图倒角（verified）：`CreateChamfer(type:int, dist, angle_rad)`。 |
| `sw_start_3d_sketch` | — | 开 3D 草图（verified）：判据 Is3D=True。 |
| `sw_add_equation` | expression | 加方程/全局变量（verified）：判据 计数 +1 且 Equation 读回一致。

    坑：`IModelDoc2` 没有 Ad |
| `sw_delete_equation` | index | 删方程/全局变量（verified）：判据 计数 -1。 |
| `sw_get_equations` | — | 列方程（verified）：走 comtypes IEquationMgr。 |
| `sw_list_global_variables` | — | 列全局变量（verified）：语法 `"名字" = 数值`。 |
| `sw_set_global_variable` | name, value | 写全局变量（verified）：判据计数 +1 且 Value 读回。 |
| `sw_create_reference_axis` | plane1, plane2 | 两基准面建参考轴（verified）：判据 RefAxis +1（只选一个面不出特征）。 |
| `sw_zoom_to_fit` | — | 缩放到合适（verified）：判据 Scale2 可读且 > 0。 |
| `sw_set_view_orientation` | view_name | 视图定向（verified）：判据 Orientation 矩阵变化。 |
| `sw_measure_distance` | p1, p2, expected_mm, tol_mm | 量两面距离（verified，mm）：判据与期望值之差 ≤ 容差。 |
| `sw_open_document` | path | 打开文档（verified）：判据文档数 +1。 |
| `sw_close_document` | title | 关闭文档（verified）：判据文档数 -1。 |
| `sw_close_all` | save | 关闭全部（verified）：`save=False` 会被未保存提示卡住，默认 True。 |
| `sw_save_all` | — | 保存全部（verified）。 |
| `sw_save_as_copy` | path | 另存副本（verified）：判据副本存在 + 原路径不变。 |
| `sw_list_configurations` | — | 列配置（verified）：激活配置走 ConfigurationManager。 |
| `sw_add_configuration` | name | 新增配置（verified）：判据配置数 +1。 |
| `sw_activate_configuration` | name | 切换配置（verified）：判据激活名读回（返回值不可靠）。 |
| `sw_get_referenced_documents` | — | 引用文档（verified）：判据依赖数 > 0。 |
| `sw_analyze_draft` | angle_deg, feature_name | 拔模分析（读取侧）：需要零件里**已有分型线特征**。

    `IPartingLineFeatureData.DraftAnalysi |
| `sw_flow_check` | — | Flow Simulation 自检（verified）：版本、静默模式、Flow 文档、工程数。

    真 API 在 `<安装>\S |
| `sw_dxp` | config, create | DimXpert 读取（verified）：schema 名 + 要素数 + 标注数。

    接口在独立的 swdimxpert.tlb |
| `sw_insert_bends` | radius | 实体转钣金（verified）：先选中一个固定面；判据出现 SheetMetal+ProcessBends+FlatPattern。 |
| `sw_base_flange` | thickness_mm, radius_mm, depth_mm | 钣金基体法兰（verified）：判据是特征树出现 SheetMetal/SMBaseFlange。

    注意：`InsertShee |
| `sw_get_flat_pattern_info` | — | 展开图信息（verified）：判据 FlatPattern 特征存在。 |
| `sw_hem` | hem_type, length_mm, radius_mm | 钣金卷边（verified）：判据特征数 +1。 |
| `sw_connect` | — | 连接检查（verified）：版本 + 文档数。 |
| `sw_create_part` | template | 新建零件（verified）：判据 GetType==1。 |
| `sw_create_reference_plane` | base_plane, offset_mm | 基准面偏移（verified）：判据 RefPlane +1。选择类型只认 PLANE。 |
| `sw_select_entity` | name, kind, append | 按名字选中（verified）：判据选择集 ≥1。 |
| `sw_clear_selection` | — | 清空选择（verified）。 |
| `sw_capture_screenshot` | path | 截图（verified）：判据 PNG 魔数 + 大小。 |
| `sw_delete_feature` | name | 删除特征（verified）：判据特征数 -1。 |
| `sw_view_rotate` | angle_deg | 旋转图纸视图（verified）：判据 IView.Angle 变化。 |
| `sw_export_drawing_pdf` | path | 图纸导出 PDF（verified）：判据 %PDF。 |
| `sw_export_drawing_dwg` | path | 图纸导出 DWG（verified）：判据 AC10xx。 |
| `sw_extrude` | depth_mm, draft_deg, is_cut | 拉伸当前草图（verified）。判据：特征 +1 且体积变化。

    实测：40×25 草图 ×20 mm → 体积 **20000. |
| `sw_export_step` | path | 导出 STEP（verified）：判据是文件头 `ISO-10303-21`。 |
| `sw_export_stl` | path | 导出 STL（verified）：判据是二进制头/ASCII `solid`。 |
| `sw_export_file` | path | 导出 PDF（verified）：判据是文件头 `%PDF`。 |
| `sw_save_document` | path | 保存/另存（verified）：判据是文件存在且未变小。 |
| `sw_create_assembly` | template | 新建装配（verified）：判据 `GetType==2`。 |
| `sw_insert_component` | part, x, y, z, fixed | 插入组件（verified，mm）：判据组件数 +1。零件需先打开；内部会切回装配。 |
| `sw_get_assembly_tree` | — | 装配树（verified）：名称/路径/固定/抑制/隐藏。 |
| `sw_suppress_component` | name, suppress | 抑制/解除组件（verified）：判据 `IsSuppressed` 读回。

    注意枚举：0=Suppressed、2=Resol |
| `sw_hide_component` | name, hide | 隐藏/显示组件（verified）：要用 `HideComponent/ShowComponent`，不是 `Visible`。 |
| `sw_replace_component` | name, new_file | 替换组件（verified）：`ReplaceComponents2` 5 参，判据是路径读回。 |
| `sw_suppress_feature` | name | 抑制特征（verified）：判据 `IsSuppressed`。 |
| `sw_unsuppress_feature` | name | 解除抑制（verified）：判据 `IsSuppressed`。 |
| `sw_list_open_documents` | — | 已打开文档列表（verified）：列表长度与 GetDocumentCount 一致。 |
| `sw_get_model_info` | — | 当前文档信息（verified）：标题/路径/类型/特征数/实体数。 |
| `sw_list_features` | — | 特征树（verified）：名称 + 类型名。 |
| `sw_get_mass_properties` | — | 质量属性（verified）：质量/体积/表面积/重心。

    注意：pywin32 取不到 `IMassProperty` 成员，内部 |
| `sw_list_bodies` | — | 实体/曲面计数（verified）。 |
| `sw_get_custom_properties` | config | 自定义属性（verified）：名 → 值。 |
| `sw_set_custom_property` | name, value, config | 写自定义属性（verified）：**读回等于写入值**才算成功。 |
| `sw_get_material` | — | 读材料（verified）。 |
| `sw_set_material` | name, config | 赋材料（verified）：`IPartDoc.SetMaterialPropertyName2`，读回校验。 |
| `sw_rebuild_model` | — | 强制重建（verified）：判据是特征数不变。 |
| `sw_set_display_mode` | mode | 显示模式（verified）：`DisplayMode` 是**可写属性**，读回校验。 |
| `sw_list_display_states` | — | 列显示状态（verified）。 |
| `sw_get_dimension` | name | 读尺寸（verified，输出 mm）。 |
| `sw_set_dimension` | name, value_mm | 改尺寸（verified，输入 mm，读回校验）。 |
| `sw_create_sketch` | plane | 新建草图（verified）。中文版必须用本地化面名（`前视基准面`）。 |
| `sw_edit_sketch` | sketch_name | 重入草图（verified）：选中后 `EditSketch()`（`MenuCommand` 在本机不可用）。 |
| `sw_exit_sketch` | — | 退出草图（verified）。 |
| `sw_sketch_line` | x1, y1, x2, y2 | 草图直线（verified，输入 mm）。判据：线段 0→1。 |
| `sw_sketch_circle` | cx, cy, radius | 草图圆（verified，mm）。判据：线段 0→1。 |
| `sw_sketch_rectangle` | x1, y1, x2, y2, rect_type | 草图矩形（verified，mm）。判据：线段 0→4。 |
| `sw_sketch_arc` | cx, cy, radius, start_angle_deg, end_angle_deg, clockwise | 草图圆弧（verified，角度按度、逆时针为正）。判据：线段 0→1。 |
| `sw_sketch_ellipse` | cx, cy, semi_major, semi_minor, rotation_deg | 草图椭圆（verified，mm）。判据：线段 0→1。 |
| `sw_sketch_polygon` | cx, cy, num_sides, circumscribed_radius, rotation_deg | 草图正多边形（verified）。判据：6 边形 → 线段 0→7。 |
| `sw_sketch_spline` | points | 草图样条（verified）：需要 COM 数组，`CreateSpline(list)` 在 pywin32 下会失败。 |
| `sw_sketch_centerline` | x1, y1, x2, y2 | 草图中心线（verified，构造线）。判据：线段 0→1。 |
| `sw_sketch_construction` | plane, length | 草图构造线（verified）：判据是 ConstructionGeometry 开关 True→False 往返成功。 |
| `sw_sketch_text` | text, x, y, plane | 草图文字（verified）：判据是字形轮廓线段增加，或能读回文字。 |
| `sw_add_sketch_constraint` | constraint, plane | 草图约束（verified）：判据是约束数 +1 **或**端点被真正拉平（几何证据）。 |
| `sw_activate_display_state` | name | 激活显示状态（verified）。文档没有显示状态时返回 note 而不是假装成功。 |
| `sw_list_materials` | name_filter, limit | 列材料库（verified）：**不打开 SolidWorks**，直接解析 `.sldmat`。

    本机实测 3 库 / 29 分 |
| `sw_bounding_box` | — | 实体包围盒（verified）：每个实体输出 min/max/尺寸（mm）。 |
| `sw_screenshot` | out_path, width, height | 存 BMP 位图（verified）。PhotoView 无 COM 接口，`SaveBMP` 是等价物。 |
| `sw_shell` | thickness, face_index | 抽壳（verified）：`face_index=-1` 自动选最大面；判据是面数翻倍（实测 7→14）。 |
| `sw_split_line` | — | 分割线（verified）：先试零参 `InsertSplitLineSil`，再试 `InsertSplitLineProject`。 |
| `sw_thicken_surface` | thickness | 曲面加厚（verified）：判据是出现 `Thicken` 特征。 |
| `sw_offset_surface` | distance | 曲面偏移（verified）：判据是曲面实体数 +1。 |
| `sw_pattern_feature` | kind, count, spacing, angle_deg | **特征**阵列（verified）。注意：组件阵列请用 `sw_pattern_component`。

    标记与组件阵列相反：特征 |
| `sw_sim_solve` | open_path, restraint_face, force_face, force_n, material | 一条龙静力分析（verified，**约 13–15 分钟**，star.exe 峰值 ~15 GB）。

    位移可靠；应力注意：固定 |
| `sw_sim_read` | open_path, study | 读已有静力结果（verified）。应力不可用时会返回 stress_available=False。 |
| `sw_motion_read` | open_path, study, component, samples | 读 Motion 结果（verified）：位移/速度/加速度采样。

    底层用 `GetResults(4)`——索引 1/2 是空 |
| `sw_docs_stats` | — | DocumentMgr 索引统计（verified）：文件数、属性条目、组件行、视图行、表格数。 |
| `sw_docs_query` | prop, folder, ext, limit | 按属性/目录/扩展名查索引（verified）。`prop` 支持 `名=值`。

    注意：**没有全文检索**（底层只有 --pro |
| `sw_props` | file | 单文件自定义属性（verified）；不给 file 则做 Simulation 加载项自检。 |
| `sw_vba_dump` | swp | 导出 `.swp` 内嵌 VBA 源码（verified）。只读。 |
| `sw_proxy_tools` | — | 列出被代理的 swkit 原始工具名（诊断用）。 |
| `sw_sim_faces` | open_path, limit | 列出零件面（索引/中心 mm/尺寸 mm），用于挑约束面与受力面。 |
| `sw_sim_list` | open_path | 列出所有仿真研究及其结果状态（有/无、步数）。 |
| `sw_sim_setup` | restraint_face, force_face, force_n, material, open_path, mesh, size, tol, request_id | 建静力研究 + 固定约束 + 法向力（可同时划网格）。分步 FEA 第一步。 |
| `sw_sim_mesh` | open_path, study, size, tol, request_id | 只划网格。size/tol 以**米**为单位；内部按实测的 ×100 换算成 API 值，并按单元数（上限 200 万）拦截过大网格。 |
| `sw_sim_run` | open_path, study, timeout_s, request_id | 只求解（不建研究、不划网格）。40 mm 级零件约 11–13 分钟，star.exe 峰值约 15 GB。 |
| `sw_sim_addin_check` | — | Simulation 加载项自检（不打开文档）：cosworks.dll 是否存在、能否拿到 AddIn 对象。 |
| `sw_motion_list` | open_path | 列出 Motion 算例、马达与结果集可用性。 |
| `sw_scan` | dir_path, pattern, out, verbose, timeout_s, request_id | 一个会话批量只读扫描目录：逐个打开、读配置与自定义属性，输出 JSON。 |
| `swdm_query` | prop, dir, ext, limit, print_rows | 按属性/目录/扩展名查私有 DocumentMgr 索引（275 文件 / 2684 组件）。prop 写成 `名=值`（子串匹配）；不带任 |
| `swdm_stats` | — | DocumentMgr 索引统计：文件数/成功数/扩展名分布/组件数。 |
| `sw_list_documents_dirty` | — | 列出打开的文档 + 是否有未保存修改（dirty），并标出当前活动文档。比 sw_list_open_documents 多 dirty/a |
| `sw_activate_document` | title | 按标题激活已打开的文档（多文档切换）。 |
| `sw_bounding_box_with_hidden` | include_hidden | 包围盒（mm），include_hidden=true 时把隐藏/抑制的也算进去（装配量外形用）。 |
| `sw_rebuild_diagnostics` | full | 重建并给诊断：是否成功、特征总数、失败特征（需要早绑定才有逐条错误码，拿不到时 failed_count=null 而不是 0）。 |
| `sw_inspect_active` | — | 当前文档自审查：类型/是否脏/特征数/错误与警告数/配置可用性。 |
| `sw_inspect_relations` | — | 装配关系自审查：组件数、配合数、路径为空的悬空组件。 |
| `sw_set_custom_properties` | props, config | 批量写自定义属性并逐条读回（数字自动用数值类型）。props 形如 {"料号": "A-01", "重量": 2.5}。 |
| `sw_create_configuration_full` | name, comment, alternate, activate | 新增配置（可带备注/派生/直接激活），比 sw_add_configuration 参数更全。 |
| `sw_assign_material_full` | name, db, config, rebuild | 赋材料并可指定材料库/配置/是否重建，然后读回材料名（读回才是判据）。 |
| `sw_gear_involute_plan` | module_mm, tooth_count, pressure_angle_deg, thickness_mm, bore_diameter_mm, root_fillet_mm, tip_chamfer_mm, include_finishing | 渐开线直齿轮：算出分度/基圆/齿顶/齿根半径并生成可执行的 Feature Graph。判据是数学恒等式（da=m(z+2)、df=m(z- |
| `sw_gearbox_plan` | module_mm, pressure_angle_deg, stage1_teeth, stage2_teeth, gear_thickness_mm, axial_gap_mm, bore_diameters_mm, radial_clearance_mm, shaft_extension_mm | 两级平行轴减速器：生成整机 Feature Graph（16 个特征），判据是传动比 (z2/z1)·(z4/z3) 与两级中心距 a=m( |
| `sw_part_plan` | part_type, parameters | 参数化零件 Feature Graph：block / cylinder / tube / flange / stepped_shaft。 |
| `sw_output_shaft_plan` | — | 按《输出轴零件图.DWG》生成输出轴 Feature Graph（13 个特征、333 mm）。 |
| `sw_internal_gear_plan` | module_mm, tooth_count, pressure_angle_deg, thickness_mm, rim_outer_diameter_mm, profile_shift_x | 内齿圈（齿顶朝内，**渐开线齿槽**，3 特征）；判据=四个特征圆直径、齿槽半角、轮缘壁厚 ≥ 1 个模数 |
| `sw_helical_gear_plan` | module_normal_mm, tooth_count, pressure_angle_deg, helix_angle_deg, thickness_mm, bore_diameter_mm, slices | 斜齿轮（**放样真螺旋面**，slices 段截面）；判据=mt=mn/cosβ、L=πd/tanβ、θ=b·tanβ/r、特征数 4+2·slices |
| `sw_spline_plan` | outer_diameter_mm, inner_diameter_mm, tooth_count, key_width_mm, length_mm | 矩形花键轴 GB/T 1144（3 特征）；判据=截面积夹在内外圆之间、体积=面积×长度 |
| `sw_keyway_lookup` | shaft_diameter_mm, required_length_mm | 标准平键与键槽 GB/T 1096；按轴径给 b×h、t1、t2，键长向上取标准系列 |
| `sw_create_internal_gear` | 同上 + execute | 一步到位建内齿圈（渐开线齿槽）；真机判据=体积 26325.888（±1%） |
| `sw_create_helical_gear` | 同上 + execute | 一步到位建斜齿轮（放样）；真机判据=体积 36290.5（4 段，±3%） |
| `sw_create_spline_shaft` | 同上 + execute | 一步到位建花键轴；真机判据=体积 85197.301（±1%） |
| `sw_feature_graph_compile` | feature_graph | 校验并编译 Feature Graph IR（含 sketch / boss_extrude / boss_revolve / loft_boss / cut_extrude / 阵列 / 基准面与基准轴），返回确定性的可审计执行计划（纯函数，不碰 COM）。 |
| `sw_feature_inspect` | include_topology, include_tokens, limit | 列出活动文档的特征树与相互关系（可含拓扑与持久引用 token）。只读。 |
| `sw_feature_rollback` | location, feature | 移动回滚棒：location = end / previous / before / after（后两者需 feature）。 |
| `sw_set_feature_parameter` | feature, parameter, value, unit, configuration, rebuild, confirm | 按「特征名 + 参数名」改尺寸（比 sw_set_dimension 高一档）。需 confirm=true。 |
| `sw_select_references` | tokens | 用持久引用 token 选中实体（token 由 sw_feature_inspect 给出）。 |
| `sw_execute_feature_graph` | feature_graph, template_path, save_path, expected_volume_mm3, use_active_document, confirm | 把 Feature Graph 编译后**在新零件里执行**（不碰已有文档），执行完读回体积/特征名做判据。可选 save_path 存盘、 |

## acad（49 个任务工具）

| 工具 | 参数 | 说明 |
|---|---|---|
| `acad_geom_line` | start, end | 直线：计数/端点/长度/重开｜能力 geom.line，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_geom_circle` | center, radius | 圆：计数/半径/面积=πR²/重开｜能力 geom.circle，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_geom_arc` | center, radius, start_angle, end_angle | 圆弧：Center/Radius/起止角｜能力 geom.arc，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_geom_polyline` | points, closed, expected_length | 多段线：顶点/闭合/长度｜能力 geom.polyline，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_geom_rect` | corner1, corner2 | 矩形：闭合/4 顶点/面积｜能力 geom.rect，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_geom_ellipse` | center, major_radius, ratio | 椭圆：长短轴/面积｜能力 geom.ellipse，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_geom_spline` | points | 样条：控制点数｜能力 geom.spline，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_geom_hatch` | corner1, corner2, pattern | 填充：ANSI31/面积｜能力 geom.hatch，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_text_single` | text, insertion, height | 单行文字：内容/位置/字高｜能力 text.single，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_text_mtext` | text, insertion, width | 多行文字：内容/宽度｜能力 text.mtext，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_text_style` | name, font | 文字样式：新增 + 字体读回｜能力 text.style，由能力自动生成（级别 L2–L4）。判据沿用该能力自带的 judge。 |
| `acad_dim_linear` | p1, p2, dim_line, expected | 线性标注：Measurement/文字外侧｜能力 dim.linear，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge |
| `acad_dim_aligned` | p1, p2, text_pos, expected | 对齐标注：Measurement｜能力 dim.aligned，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_dim_diametric` | radius, center | 直径标注：Measurement=2R｜能力 dim.diametric，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judg |
| `acad_dim_radial` | radius, center | 半径标注：Measurement=R｜能力 dim.radial，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_dim_angular` | vertex, p1, p2, text_pos | 角度标注：Measurement=π/2｜能力 dim.angular，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge |
| `acad_dim_ordinate` | point, leader, use_x | 坐标标注：Measurement=X｜能力 dim.ordinate，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_dim_arc` | center, start, end, text_pos | 弧长标注：Measurement=R·θ｜能力 dim.arc，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_dim_baseline` | — | 基线标注：两条同基 Measurement｜能力 dim.baseline，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 jud |
| `acad_dim_continuous` | — | 连续标注：两段首尾相接且和=总长｜能力 dim.continuous，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_dim_tolerance` | upper, lower, override | 尺寸公差：DIMTOL+TextOverride 读回｜能力 dim.tolerance，由能力自动生成（级别 L2–L4）。判据沿用该能力 |
| `acad_gdt_tolerance` | text, insertion, direction | 形位公差：ACDBFCF + 符号码｜能力 gdt.tolerance，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge |
| `acad_symbol_roughness` | — | 粗糙度符号：3 线 + Ra 文字｜能力 symbol.roughness，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 jud |
| `acad_symbol_weld` | size | 焊接符号：2 线 + 焊缝尺寸｜能力 symbol.weld，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_symbol_centerline` | start, end, extend | 中心线：线型 + 两端超出｜能力 symbol.centerline，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_symbol_centermark` | center, radius, gap | 中心标记：十字过圆心｜能力 symbol.centermark，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_symbol_balloon` | tip, text, index | 序号气泡：MULTILEADER + 序号｜能力 symbol.balloon，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 j |
| `acad_table_bom` | — | BOM 表：逐格 + 合计｜能力 table.bom，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_table_grid` | — | 通用网格表：逐格 + 合计｜能力 table.grid，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_table_chinese` | style, font | 中文表格：CN 样式 + 重开不丢字｜能力 table.chinese，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge |
| `acad_block_define` | — | 块定义 + 属性定义｜能力 block.define，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_block_insert_with_attributes` | — | 块插入 + 属性值｜能力 block.insert_with_attributes，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 |
| `acad_frame_titleblock` | — | A3 图框 + 标题栏 6 属性｜能力 frame.titleblock，由能力自动生成（级别 L3–L4）。判据沿用该能力自带的 judg |
| `acad_layout_multipage` | name, viewport_w, viewport_h | 新建布局 + 视口｜能力 layout.multipage，由能力自动生成（级别 L2–L4）。判据沿用该能力自带的 judge。 |
| `acad_layer_create` | name, color | 建图层：Name/Color 读回｜能力 layer.create，由能力自动生成（级别 L2–L4）。判据沿用该能力自带的 judge。 |
| `acad_layer_set_current` | name, color | 设当前层 + 新实体落层｜能力 layer.set_current，由能力自动生成（级别 L2–L4）。判据沿用该能力自带的 judge。 |
| `acad_layer_snapshot` | name | 图层状态快照：属性级保存→改→恢复｜能力 layer.snapshot，由能力自动生成（级别 L3–L4）。判据沿用该能力自带的 judge |
| `acad_solid_primitive` | — | 基本体：box/cylinder/sphere 体积｜能力 solid.primitive，由能力自动生成（级别 L1–L4）。判据沿用该能 |
| `acad_solid_extrude` | — | 拉伸：体积 = 轮廓面积 × 高度｜能力 solid.extrude，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_boolean_union` | — | 并集：2→1，V=10000｜能力 boolean.union，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_boolean_subtract` | — | 差集：2→1，V=6000｜能力 boolean.subtract，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_boolean_intersect` | — | 交集：2→1，V=2000｜能力 boolean.intersect，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `acad_boolean_section_slice` | — | SLICE：两块体积之和=原体积｜能力 boolean.section_slice，由能力自动生成（级别 L3–L4）。判据沿用该能力自带的 |
| `acad_view_zoom` | center, radius | ZoomExtents：视图包住几何｜能力 view.zoom，由能力自动生成（级别 L3）。判据沿用该能力自带的 judge。 |
| `acad_projection_orthographic` | — | 三视图投影：CSG→front/top/left（可见/隐藏/轴线分层）｜能力 projection.orthographic，由能力自动生 |
| `acad_export_dwg` | — | DWG：文件 + AC10 + 重开一致｜能力 export.dwg，由能力自动生成（级别 L0–L4）。判据沿用该能力自带的 judge。 |
| `acad_export_dxf` | — | DXF：段 + 族计数 + 重新导入｜能力 export.dxf，由能力自动生成（级别 L0–L4）。判据沿用该能力自带的 judge。 |
| `acad_export_pdf` | — | PDF：A3 + 非空白｜能力 export.pdf，由能力自动生成（级别 L0–L3）。判据沿用该能力自带的 judge。 |
| `acad_export_pdf_multipage` | — | 多页 PDF：逐布局出图 + 合并（每页 A3 且有墨）｜能力 export.pdf_multipage，由能力自动生成（级别 L0–L3） |

## nx（62 个任务工具）

| 工具 | 参数 | 说明 |
|---|---|---|
| `nx_selftest` | — | 离线自检：每条能力的动作是否实现、判据是否齐全（不需要 NX）。 |
| `nx_solid_move_body` | — | 移动实体：+X 平移 100（重心 50→150）｜能力 solid.move_body，由能力自动生成（级别 L1–L3）。判据沿用该能力 |
| `nx_feature_text` | — | 三维文字 NXTEST（6 条字母 Spline）｜能力 feature.text，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 |
| `nx_export_dwg` | — | DWG 导出（翻译器 CLI，m=ugtodwg）｜能力 export.dwg，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 j |
| `nx_export_dxf` | — | DXF 导出（翻译器 CLI，约 190 KB）｜能力 export.dxf，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 ju |
| `nx_drawing_dimension` | — | 视图上建线性尺寸标注（失败退回直接标注）｜能力 drawing.dimension，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 |
| `nx_drawing_projected_view` | — | 基础视图 + 投影视图（2 个视图）｜能力 drawing.projected_view，由能力自动生成（级别 L1–L2）。判据沿用该能力 |
| `nx_solid_delete_face` | — | 删孔面愈合（93716.8 → 100000 / 6 面）｜能力 solid.delete_face，由能力自动生成（级别 L1–L2）。判 |
| `nx_feature_hole` | — | 孔：顶面 Ø20 通孔（体积 93716.8）｜能力 feature.hole，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 j |
| `nx_solid_trim_body` | — | 用辅助体的面修剪实体（目标 50000）｜能力 solid.trim_body，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 j |
| `nx_feature_rib` | — | 轮廓筋（10×15，体积 115000）｜能力 feature.rib，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge |
| `nx_feature_sweep_guide` | — | 圆截面沿直线引导扫掠（体积 31415.9）｜能力 feature.sweep_guide，由能力自动生成（级别 L1–L3）。判据沿用该能 |
| `nx_inspect_edge_count` | — | 边计数（块 12 / 圆柱 3）｜能力 inspect.edge_count，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 ju |
| `nx_inspect_body_state` | — | 实体/片体判定（1 solid + 1 sheet）｜能力 inspect.body_state，由能力自动生成（级别 L1–L2）。判据沿 |
| `nx_inspect_face_types` | — | 圆柱体面类型分类（2 平面 + 1 圆柱面）｜能力 inspect.face_types，由能力自动生成（级别 L1–L2）。判据沿用该能力 |
| `nx_measure_perimeter` | — | 顶面周长（100×50 → 300）｜能力 measure.perimeter，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 j |
| `nx_part_new` | name | 新建毫米部件｜能力 part.new，由能力自动生成（级别 L1）。判据沿用该能力自带的 judge。 |
| `nx_datum_plane` | — | 固定基准面（z=10，法向 +Z）｜能力 datum.plane，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_datum_axis` | — | 固定基准轴（沿 +X）｜能力 datum.axis，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_block_create` | length, width, height | 建 100×50×20 块｜能力 block.create，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `nx_block_two_bodies` | offset_x | 同一部件两个块（实体数=2）｜能力 block.two_bodies，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `nx_boolean_subtract_retain` | — | 求差并保留工具体（2 实体 / 100000）｜能力 boolean.subtract_retain，由能力自动生成（级别 L1–L3）。判 |
| `nx_boolean_subtract` | offset_x | A−B（重叠 10×50×20）｜能力 boolean.subtract，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judg |
| `nx_boolean_union` | offset_x | A∪B｜能力 boolean.union，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `nx_boolean_intersect` | offset_x | A∩B（10×50×20）｜能力 boolean.intersect，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `nx_cylinder_create` | diameter, height | 建 Ø40×30 圆柱｜能力 cylinder.create，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `nx_measure_mass` | length, width, height | 质量属性：体积/面积/重心｜能力 measure.mass，由能力自动生成（级别 L3）。判据沿用该能力自带的 judge。 |
| `nx_body_topo` | length, width, height | 拓扑计数：面 6 / 边 12 / 顶点 8｜能力 body.topo，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge |
| `nx_extrude_rect` | length, width, distance | 矩形截面拉伸（100×50×10）｜能力 extrude.rect，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `nx_asm_add_component` | — | 装配插入 1 个组件｜能力 asm.add_component，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_asm_two_components` | — | 装配插入 2 个组件并存盘｜能力 asm.two_components，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge |
| `nx_export_step` | — | 导出 STEP（ISO-10303-21）｜能力 export.step，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judg |
| `nx_export_iges` | — | 导出 IGES｜能力 export.iges，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge。 |
| `nx_drawing_base_view` | model_view | A3 图纸 + Front 基础视图｜能力 drawing.base_view，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 j |
| `nx_extrude_ring` | — | 带内孔截面拉伸（外框−内框）｜能力 extrude.ring，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge。 |
| `nx_feature_chamfer` | — | 一条边倒角 5 mm｜能力 feature.chamfer，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge。 |
| `nx_feature_edge_blend` | — | 一条边圆角 R5｜能力 feature.edge_blend，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge。 |
| `nx_feature_pattern_linear` | — | 沿 X 阵列 3 个（间距 120）｜能力 feature.pattern_linear，由能力自动生成（级别 L1–L3）。判据沿用该能力 |
| `nx_export_acis` | — | 导出 ACIS (.sat)｜能力 export.acis，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_measure_face_area` | — | 六面面积和/周长｜能力 measure.face_area，由能力自动生成（级别 L3）。判据沿用该能力自带的 judge。 |
| `nx_solid_cone` | diameter, height | Ø40×30 圆锥｜能力 solid.cone，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge。 |
| `nx_solid_sphere` | diameter | Ø40 球｜能力 solid.sphere，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge。 |
| `nx_boolean_two_tools` | — | 一次减去两个工具体｜能力 boolean.two_tools，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge。 |
| `nx_sketch_rect` | — | XY 平面草图 + 4 条线｜能力 sketch.rect，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_sketch_extrude` | — | 草图 4 线拉伸 10 → 50000｜能力 sketch.extrude，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 jud |
| `nx_sketch_circle_extrude` | — | 草图整圆拉伸 30 → 37699.11｜能力 sketch.circle_extrude，由能力自动生成（级别 L1–L3）。判据沿用该能 |
| `nx_drawing_sheet_a4` | size | A4 图纸页（297×210）｜能力 drawing.sheet_a4，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge |
| `nx_asm_three_components` | — | 装配插 3 个组件｜能力 asm.three_components，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_export_stl` | — | 导出 STL｜能力 export.stl，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_inspect_body_type` | — | 实体/片体判定｜能力 inspect.body_type，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_sketch_constraint` | — | 两条线加重合约束｜能力 sketch.constraint，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_sketch_horizontal` | kind | 水平约束｜能力 sketch.horizontal，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_sketch_dimension` | — | 整圆直径尺寸 50｜能力 sketch.dimension，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_part_inch` | — | 英制部件（4×2×1 in 块，体积 8 in³）｜能力 part.inch，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 ju |
| `nx_export_step_ap214` | — | AP214 STEP｜能力 export.step_ap214，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_export_parasolid` | — | Parasolid X_T｜能力 export.parasolid，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `nx_measure_faces_two` | — | 只量两个大面（面积 10000）｜能力 measure.faces_two，由能力自动生成（级别 L2–L3）。判据沿用该能力自带的 jud |
| `nx_measure_distance` | — | 两个大面之间距离 20｜能力 measure.distance，由能力自动生成（级别 L2–L3）。判据沿用该能力自带的 judge。 |
| `nx_asm_component_names` | — | 组件名保留（AAA/BBB/CCC）｜能力 asm.component_names，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 |
| `nx_file_save_copy` | — | 另存副本并重开验证｜能力 file.save_copy，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judge。 |
| `nx_boolean_unite_three` | — | 三体并集（C 在 A 内）｜能力 boolean.unite_three，由能力自动生成（级别 L1–L4）。判据沿用该能力自带的 judg |
| `nx_asm_constraint_refs` | — | 建贴合约束并挂两个面参考｜能力 asm.constraint_refs，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge |

## gx（43 个任务工具）

| 工具 | 参数 | 说明 |
|---|---|---|
| `gx_selftest` | — | 离线自检：动作与判据是否齐全（不需要 GX Works3）。 |
| `gx_project_new` | — | 新建 FX5U + ST 工程｜能力 project.new，由能力自动生成（级别 L1）。判据沿用该能力自带的 judge。 |
| `gx_project_new_rcpu` | series, model | 新建 iQ-R（RCPU/R00）+ ST 工程｜能力 project.new_rcpu，由能力自动生成（级别 L1）。判据沿用该能力自带的 |
| `gx_project_new_fx5s` | series, model | 新建 FX5S + ST 工程｜能力 project.new_fx5s，由能力自动生成（级别 L1）。判据沿用该能力自带的 judge。 |
| `gx_program_rcpu_roundtrip` | series, model | iQ-R 上粘贴 ST 并读回｜能力 program.rcpu_roundtrip，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 |
| `gx_project_save` | — | 另存为 .gx3（含读回校验）｜能力 project.save，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `gx_project_meta` | — | 解包 .gx3：Config.xml + 条目数｜能力 project.meta，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的  |
| `gx_program_paste_st` | — | 把 ST 代码粘进编辑器并转换｜能力 program.paste_st，由能力自动生成（级别 L1–L3）。判据沿用该能力自带的 judge |
| `gx_program_read_st` | — | 从 .gx3 读回 ST 源码（逐字比对）｜能力 program.read_st，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的  |
| `gx_program_import_xml` | program_name | 用 XML 新建程序（另起一个 PrgGen）｜能力 program.import_xml，由能力自动生成（级别 L2–L3）。判据沿用该能 |
| `gx_program_import_fb` | program_name, fb_name | 用 XML 建程序+功能块（带局部标签）｜能力 program.import_fb，由能力自动生成（级别 L3）。判据沿用该能力自带的 ju |
| `gx_program_import_fb_instance` | program_name, fb_name, inst_name | 用 XML 建功能块实例并调用｜能力 program.import_fb_instance，由能力自动生成（级别 L3）。判据沿用该能力自带 |
| `gx_program_import_fb_params` | — | 功能块带参数（IN/OUT/IN_OUT）+ 调用传参｜能力 program.import_fb_params，由能力自动生成（级别 L3） |
| `gx_datatype_import` | program_name, struct_name | 用 XML 建结构体（并用变量读回）｜能力 datatype.import，由能力自动生成（级别 L3）。判据沿用该能力自带的 judge。 |
| `gx_datatype_member_var` | program_name, struct_name, var_name | 结构体类型的变量（成员级软元件分配）｜能力 datatype.member_var，由能力自动生成（级别 L3）。判据沿用该能力自带的 ju |
| `gx_datatype_custom_members` | program_name, struct_name, var_name | 自定义结构体成员｜能力 datatype.custom_members，由能力自动生成（级别 L3）。判据沿用该能力自带的 judge。 |
| `gx_datatype_member_access` | program_name, struct_name, label_name | 正文按成员名访问结构体（全局标签）｜能力 datatype.member_access，由能力自动生成（级别 L3）。判据沿用该能力自带的  |
| `gx_label_multi_type` | — | BOOL/WORD/DWORD 全局标签｜能力 label.multi_type，由能力自动生成（级别 L2–L3）。判据沿用该能力自带的  |
| `gx_datatype_struct_array` | — | 结构体数组成员 + 元素访问｜能力 datatype.struct_array，由能力自动生成（级别 L3）。判据沿用该能力自带的 judg |
| `gx_program_multi_programs` | — | 一个工程里两个程序｜能力 program.multi_programs，由能力自动生成（级别 L2–L3）。判据沿用该能力自带的 judge |
| `gx_inspect_devices_rcpu` | series, model | iQ-R 软元件模板（与 FX5U 不同）｜能力 inspect.devices_rcpu，由能力自动生成（级别 L2）。判据沿用该能力自带 |
| `gx_xmlgen_manual_template` | — | 手写骨架也能导入（不依赖 MELSOFT 样例）｜能力 xmlgen.manual_template，由能力自动生成（级别 L3）。判据沿用 |
| `gx_inspect_source_map` | — | 步→源码坐标（Row/Col/StrLen）｜能力 inspect.source_map，由能力自动生成（级别 L2）。判据沿用该能力自带的 |
| `gx_inspect_programs` | — | 列程序清单（步数/源码行数）｜能力 inspect.programs，由能力自动生成（级别 L2）。判据沿用该能力自带的 judge。 |
| `gx_project_diff` | — | 两个工程的源码级差异｜能力 project.diff，由能力自动生成（级别 L2–L3）。判据沿用该能力自带的 judge。 |
| `gx_inspect_devices` | — | 读 FX5U 系统软元件模板｜能力 inspect.devices，由能力自动生成（级别 L1–L2）。判据沿用该能力自带的 judge。 |
| `gx_inspect_mil` | — | 读编译后的 IL 文本｜能力 inspect.mil，由能力自动生成（级别 L2）。判据沿用该能力自带的 judge。 |
| `gx_label_import_xml` | — | 导入全局标签 XML 并读回｜能力 label.import_xml，由能力自动生成（级别 L2–L3）。判据沿用该能力自带的 judge。 |
| `gx_build_convert_all` | — | 全部转换：从 Progress.txt 读错误数｜能力 build.convert_all，由能力自动生成（级别 L1–L3）。判据沿用该能 |
| `gx_build_program_check` | — | 程序检查：读「无错误」判定文本｜能力 build.program_check，由能力自动生成（级别 L2–L3）。判据沿用该能力自带的 ju |
| `gx_program_write_ladder_multi` | rungs | **画两个梯级**（X0→(Y0)、X1-X2→(Y1)）｜能力 program.write_ladder_multi，由能力自动生成（级别 |
| `gx_program_write_ladder_parallel` | contacts, parallel, out | **画并联支路**（X0 ∥ X2 → (Y0)）｜能力 program.write_ladder_parallel，由能力自动生成（级别  |
| `gx_program_write_ladder_appl` | contacts, parallel, out | **画应用指令**（X0 → MOV K1 D0）｜能力 program.write_ladder_appl，由能力自动生成（级别 L3）。 |
| `gx_inspect_ladder` | — | **离线读梯形图**（LadderBlocks → 结构/摘要）｜能力 inspect.ladder，由能力自动生成（级别 L1）。判据沿用 |
| `gx_program_write_ladder` | — | **画梯级**（触点/并联/线圈/应用指令）｜能力 program.write_ladder，由能力自动生成（级别 L3）。判据沿用该能力自 |
| `gx_build_error_messages` | — | **编译器原话**（输出面板的表格）｜能力 build.error_messages，由能力自动生成（级别 L2）。判据沿用该能力自带的 j |
| `gx_build_error_detail` | — | 故意写错：定位错在哪个编译阶段｜能力 build.error_detail，由能力自动生成（级别 L2–L3）。判据沿用该能力自带的 jud |
| `gx_build_locate_error_line` | bad_line, total_lines | 二分法定位坏行（前缀问编译器）｜能力 build.locate_error_line，由能力自动生成（级别 L3）。判据沿用该能力自带的 j |
| `gx_batch_new_projects` | — | 同会话连新建 3 个工程（关闭后重建）｜能力 batch.new_projects，由能力自动生成（级别 L3）。判据沿用该能力自带的 ju |
| `gx_batch_projects` | batch_count | 同会话批量出 3 个工程（各自 0 错）｜能力 batch.projects，由能力自动生成（级别 L3）。判据沿用该能力自带的 judge |
| `gx_project_new_language` | — | **换程序语言建工程**（ST / SFC / FBD）｜能力 project.new_language，由能力自动生成（级别 L1）。判据 |
| `gx_project_check` | — | **工程校验**（与另一个 .gx3 比对）｜能力 project.check，由能力自动生成（级别 L3）。判据沿用该能力自带的 judg |
| `gx_project_reopen` | — | 存盘→重开→步数仍在（L4）｜能力 project.reopen，由能力自动生成（级别 L4）。判据沿用该能力自带的 judge。 |

## codesys（56 个任务工具）

| 工具 | 参数 | 说明 |
|---|---|---|
| `codesys_commands` | — | 列出常推荐的 services 命令与参数提示。 |
| `codesys_ping` | — | 往返检查（最轻量，先判断服务在不在）（服务命令 ping） |
| `codesys_version` | — | 服务与 IDE 版本（服务命令 version） |
| `codesys_devices` | filter, limit | 列出设备描述（1562 条），可按名过滤（服务命令 devices） |
| `codesys_projects` | — | 列出已打开工程（服务命令 projects） |
| `codesys_project_create` | path, device, program, task, interval, priority, unit, bare, device_node | 新建工程（可同时建 ST 程序与任务）（服务命令 project.create，写操作） |
| `codesys_project_open` | path | 打开工程（服务命令 project.open，写操作） |
| `codesys_project_save` | path | 保存工程（服务命令 project.save，写操作） |
| `codesys_project_save_as` | path | 另存为（服务命令 project.save_as，写操作） |
| `codesys_project_close` | — | 关闭当前工程（服务命令 project.close，写操作） |
| `codesys_project_info` | — | 当前工程信息（路径/dirty/应用/子对象）（服务命令 project.info） |
| `codesys_project_meta` | — | 工程元信息（标题/公司/版本）（服务命令 project.meta） |
| `codesys_tree` | path, depth | 对象树（可限深度）（服务命令 tree） |
| `codesys_object_info` | path | 单个对象信息（类型/子对象/文本能力）（服务命令 object.info） |
| `codesys_object_rename` | path, name | 重命名对象（服务命令 object.rename，写操作） |
| `codesys_object_move` | path, parent, index | 移动对象到父路径（服务命令 object.move，写操作） |
| `codesys_object_delete` | path | 删除对象（拒绝删工程根）（服务命令 object.delete，写操作） |
| `codesys_folder_create` | parent, name | 新建文件夹（服务命令 folder.create，写操作） |
| `codesys_pou_read` | path, part | 读 POU 声明/实现（服务命令 pou.read） |
| `codesys_pou_write` | path, text, part | 写 POU 声明/实现（**会读回比对**）（服务命令 pou.write，写操作） |
| `codesys_pou_create` | parent, name, kind, language | 新建 POU（默认语言不是 ST，务必显式给 language）（服务命令 pou.create，写操作） |
| `codesys_pou_create_typed` | parent, name, kind, language, return_type, text | 新建带返回类型的 POU（服务命令 pou.create_typed，写操作） |
| `codesys_pou_member` | parent, name, kind, text, return_type | 给 POU 加方法/属性/动作（服务命令 pou.member，写操作） |
| `codesys_pou_members` | path | 列出 POU 成员（服务命令 pou.members） |
| `codesys_pou_persistent` | name | 建持久变量表（服务命令 pou.persistent，写操作） |
| `codesys_find_text` | pattern, path, part, limit, case_sensitive | 在声明/实现里搜文本（带行号）（服务命令 find.text） |
| `codesys_task_create` | name, pous, interval, priority, unit | 建任务并绑定 POU（服务命令 task.create，写操作） |
| `codesys_tasks` | — | 列出任务（服务命令 tasks） |
| `codesys_task_info` | path | 单个任务信息（服务命令 task.info） |
| `codesys_app_clean` | — | 清理应用（让 is_uptodate 变 false）（服务命令 app.clean，写操作） |
| `codesys_app_generate` | — | 生成代码（真编译，诊断看 execute 的引擎日志）（服务命令 app.generate，写操作） |
| `codesys_libraries` | — | 已引用库 + 可用库（537 个）（服务命令 libraries） |
| `codesys_library_add` | name | 引入库（服务命令 library.add，写操作） |
| `codesys_symbols_create` | opc_ua, export_comments, layout_calculator | 建符号配置（服务命令 symbols.create，写操作） |
| `codesys_symbols_info` | path | 符号配置信息（服务命令 symbols.info） |
| `codesys_textlist_create` | name, languages | 建文本表（服务命令 textlist.create，写操作） |
| `codesys_textlist_languages` | path, add | 文本表语言（可 add）（服务命令 textlist.languages，写操作） |
| `codesys_textlist_rows` | path, limit | 读文本表行（服务命令 textlist.rows） |
| `codesys_textlist_export` | path, out | 导出文本表（服务命令 textlist.export） |
| `codesys_export_xml` | path, target | 导出 PLCopenXML（带字节数判据）（服务命令 export.xml） |
| `codesys_import_xml` | path | 导入 PLCopenXML（**比对导入前后对象数**）（服务命令 import.xml，写操作） |
| `codesys_export_native` | path, target | 原生导出（服务命令 export.native） |
| `codesys_project_archive` | path | 整包归档（数 MB）（服务命令 project.archive） |
| `codesys_generate_runtime` | directory | 生成运行时文件（服务命令 generate.runtime） |
| `codesys_project_io_export` | path, device | 导出 I/O 映射 CSV（服务命令 project.io_export） |
| `codesys_project_io_import` | path, device | 导入 I/O 映射 CSV（服务命令 project.io_import，写操作） |
| `codesys_online_simulation` | enabled | 开关仿真模式（服务命令 online.simulation，写操作） |
| `codesys_online_login` | autostart | 登录（仿真可用）（服务命令 online.login，写操作） |
| `codesys_online_logout` | — | 注销（服务命令 online.logout，写操作） |
| `codesys_online_state` | — | 在线状态（服务命令 online.state） |
| `codesys_online_start` | — | 启动应用（服务命令 online.start，写操作） |
| `codesys_online_stop` | — | 停止应用（服务命令 online.stop，写操作） |
| `codesys_online_read` | expression, expressions | 读在线变量值（数值判据）（服务命令 online.read） |
| `codesys_online_write` | expression, value | 写在线变量并读回（服务命令 online.write，写操作） |
| `codesys_online_monitor` | expression, samples, interval_ms, expressions | 在线采样（给样本数与间隔，**返回的是数字序列**）（服务命令 online.monitor） |
| `codesys_online_download` | — | 下载到 PLC（服务命令 online.download，写操作） |

## autoshop（40 个任务工具）

| 工具 | 参数 | 说明 |
|---|---|---|
| `autoshop_doctor` | — | 环境自检：工程、UIA、frida、编辑器。 |
| `autoshop_tree` | — | 导出工程树（程序/子程序/FB/MODULE）。 |
| `autoshop_summary` | compile | 工程总览：程序、树、符号、监控表、编译。 |
| `autoshop_compile` | one, timeout_s | 全部编译（或当前文档）并报告消息。 |
| `autoshop_il` | doc, view, write_file | 读取/写入当前文档的指令列表（默认读）。write_file 指向 LF 结尾的文本文件。 |
| `autoshop_apply` | file, doc, save, confirm, request_id | 写程序 → 转换 → 编译 → 报告诊断（不可逆，需 confirm=true）。 |
| `autoshop_check` | no_compile, offline | 工程体检（双线圈/无效写入等）；offline 指定目录则不启动 AutoShop。 |
| `autoshop_symbols` | add, note, row | 读符号表；add=[NAME,ADDRESS] 追加一条。 |
| `autoshop_crossref` | — | 交叉引用：元件在哪些程序里被用到。 |
| `autoshop_hcp` | project, xml | 读 .hcp 工程索引（离线，解密容器；不启动 AutoShop）。 |
| `autoshop_illog` | project, program, paths | 从 il_log.log 读带行号的 IL（H5U 可用）。 |
| `autoshop_save` | settle | 保存工程并报告哪些文件被重写。 |
| `autoshop_commands` | — | 列出 autoshopkit CLI 的全部 verb 与参数提示。 |
| `autoshop_start` | project | 启动 AutoShop（可选带工程路径），已启动则复用。 |
| `autoshop_stop` | — | 关闭 AutoShop。 |
| `autoshop_open` | project | 打开 .hcp 工程（会抢焦点）。 |
| `autoshop_new` | path, hcp | 新建工程。 |
| `autoshop_monitor` | filter, limit | 读监控表/软元件值（在线动作）。 |
| `autoshop_output` | limit | 读 AutoShop 输出窗口文本（编译/错误信息的原始来源）。 |
| `autoshop_dialogs` | — | 列出当前 AutoShop 的模态/非模态对话框（UI 卡死排查用）。 |
| `autoshop_shot` | out | 截屏（默认当前窗口），配合 dialogs 定位 UI 问题。 |
| `autoshop_cmd` | argv | 透传一条 autoshopkit CLI 命令（逃生口）。 |
| `autoshop_dlfile` | — | 生成离线下载文件（dlfile，无参数；产物路径从输出里读）。 |
| `autoshop_il_read` | doc | 读当前程序的指令表（il --read，只读）。 |
| `autoshop_il_write` | write_file, doc | 写指令表文本并回读（il --write <file>，写操作）。 |
| `autoshop_il_view` | doc | 以只读视图方式打开指令表（il --view，写保护）。 |
| `autoshop_symbols_read` | — | 读符号/变量表（symbols，只读）。 |
| `autoshop_symbols_add` | name, address | 向符号表追加一条 NAME,ADDRESS（symbols --add）。 |
| `autoshop_symbols_row` | row | 读符号表第 N 行（symbols --row N）。 |
| `autoshop_compile_one` | timeout_s | 只编译当前文档（compile --one），比全量编译快。 |
| `autoshop_check_offline` | offline | 离线工程体检（check --offline <目录> --no-compile，不开 AutoShop）。 |
| `autoshop_hcp_xml` | project | 读 .hcp 工程索引并输出 XML（hcp --project <p> --xml）。 |
| `autoshop_illog_program` | program, project | 读某个程序的带行号 IL（illog --program <名>）。 |
| `autoshop_illog_paths` | project | 列出 il_log 里可用的程序路径（illog --paths）。 |
| `autoshop_summary_compile` | — | 工程总览并顺带编译（summary --compile）。 |
| `autoshop_monitor_read` | — | 读监控表当前值（monitor，在线）。 |
| `autoshop_monitor_row` | row | 读/扩展监控表第 N 行（monitor --row N）。 |
| `autoshop_output_tail` | — | 读输出窗口文本（output，编译/错误原文）。 |
| `autoshop_status_launch` | project | 启动（若未运行）并报告 AutoShop 状态（status --launch）。 |
| `autoshop_hcp_write_xml` | project, xml_file | 把一份 XML 加密写回 .hcp（hcp --project FILE.hcp --write-xml FILE）。会改写工程文件，属写操 |

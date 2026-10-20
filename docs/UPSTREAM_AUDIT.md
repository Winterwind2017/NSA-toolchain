# 上游 188 工具去向审计

> 由 `tools/audit_upstream.py` 生成，**只读**上游 `server.py`，不执行。
> 目的：让「上游工具去哪了」这件事可查，而不是「看起来整合过了」。

## 汇总

| 归宿 | 数量 | 含义 |
|---|---|---|
| 已覆盖 | 115 | 本仓库有实现、有真机判据 |
| 已判死 | 5 | 上游实现调用了不存在/已废弃 API，或本仓库实测不可用 |
| 已知不稳 | 2 | 能跑但会崩/判据不立，不进自动回归 |
| 未达可用 | 24 | 已登记但没打通 |
| 未复核 | 42 | **待办**：还没验证 |

上游共解析出 **188** 个工具。

## 明细

| 工具 | 判死 API | 归属 | 说明 | 上游行 |
|---|---|---|---|---|
| `sw_check_geometry` | — | 已判死 | 本仓库实测不可用： | 1714 |
| `sw_delete_face` | — | 已判死 | 本仓库实测不可用：option=0/1/2/4/8 × flag=T/F 共 10 组全 (False,False)，面数不变 | 2644 |
| `sw_knit_surfaces` | — | 已判死 | 本仓库实测不可用：sldworks.tlb 无 InsertKnitSurface | 2165 |
| `sw_start_macro_recording` | — | 已判死 | 本仓库实测不可用：类型库穷举无 StartRecording | 2049 |
| `sw_stop_macro_recording` | — | 已判死 | 本仓库实测不可用：类型库穷举无 StopRecording | 2066 |
| `sw_add_sketch_dimension` | — | 已知不稳 | 不进自动回归：round 17 成功 0.01→0.03；round 32 挂起并崩溃过一次 | 1085 |
| `sw_show_all_planes` | — | 已知不稳 | 不进自动回归：API 存在且可调，但 IFeature.Visible 不反映图形可见性，无法构造 A/B | 3338 |
| `sw_activate_configuration` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1806 |
| `sw_activate_display_state` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3484 |
| `sw_add_annotation` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1586 |
| `sw_add_auxiliary_view` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3002 |
| `sw_add_balloon` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3052 |
| `sw_add_bom_table` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1603 |
| `sw_add_broken_view` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3022 |
| `sw_add_center_mark` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3042 |
| `sw_add_centerline` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3032 |
| `sw_add_configuration` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1823 |
| `sw_add_datum_feature` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3092 |
| `sw_add_drawing_dimension` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1569 |
| `sw_add_drawing_view` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1533 |
| `sw_add_hole_table` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3102 |
| `sw_add_sketch_constraint` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1108 |
| `sw_add_surface_finish` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3062 |
| `sw_add_weld_symbol` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3082 |
| `sw_base_flange` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2709 |
| `sw_capture_screenshot` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1917 |
| `sw_chamfer` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1190 |
| `sw_check_interference` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1493 |
| `sw_circular_pattern` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1266 |
| `sw_clear_selection` | — | 已覆盖 | 本仓库有实现且有真机判据 | 824 |
| `sw_close_all` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3528 |
| `sw_close_document` | — | 已覆盖 | 本仓库有实现且有真机判据 | 667 |
| `sw_connect` | — | 已覆盖 | 本仓库有实现且有真机判据 | 611 |
| `sw_create_assembly` | — | 已覆盖 | 本仓库有实现且有真机判据 | 716 |
| `sw_create_part` | — | 已覆盖 | 本仓库有实现且有真机判据 | 699 |
| `sw_create_reference_axis` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2103 |
| `sw_create_reference_plane` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2084 |
| `sw_create_section_view` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3298 |
| `sw_create_sketch` | — | 已覆盖 | 本仓库有实现且有真机判据 | 855 |
| `sw_delete_body` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2369 |
| `sw_delete_feature` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1363 |
| `sw_edit_sketch` | — | 已覆盖 | 本仓库有实现且有真机判据 | 872 |
| `sw_exit_sketch` | — | 已覆盖 | 本仓库有实现且有真机判据 | 888 |
| `sw_explode_assembly` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1515 |
| `sw_export_drawing_dwg` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3132 |
| `sw_export_drawing_pdf` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3122 |
| `sw_export_file` | — | 已覆盖 | 本仓库有实现且有真机判据 | 764 |
| `sw_export_step` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3686 |
| `sw_export_stl` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3696 |
| `sw_extrude` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1133 |
| `sw_extruded_surface` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2594 |
| `sw_fix_component` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1459 |
| `sw_get_assembly_tree` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3258 |
| `sw_get_bounding_box` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1680 |
| `sw_get_custom_properties` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1752 |
| `sw_get_dimension` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1621 |
| `sw_get_equations` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1842 |
| `sw_get_flat_pattern_info` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2201 |
| `sw_get_mass_properties` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1661 |
| `sw_get_material` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2270 |
| `sw_get_model_info` | — | 已覆盖 | 本仓库有实现且有真机判据 | 783 |
| `sw_get_referenced_documents` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3548 |
| `sw_get_status` | — | 已覆盖 | 本仓库有实现且有真机判据 | 630 |
| `sw_hem` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2759 |
| `sw_hide_component` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3238 |
| `sw_insert_component` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1414 |
| `sw_linear_pattern` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1246 |
| `sw_list_bodies` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2329 |
| `sw_list_configurations` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1790 |
| `sw_list_display_states` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3474 |
| `sw_list_features` | — | 已覆盖 | 本仓库有实现且有真机判据 | 837 |
| `sw_list_global_variables` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3431 |
| `sw_list_materials` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2290 |
| `sw_list_open_documents` | — | 已覆盖 | 本仓库有实现且有真机判据 | 748 |
| `sw_measure_distance` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1697 |
| `sw_mirror_component` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3218 |
| `sw_move_component` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3248 |
| `sw_offset_surface` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2614 |
| `sw_open_document` | — | 已覆盖 | 本仓库有实现且有真机判据 | 649 |
| `sw_pattern_component_circular` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3208 |
| `sw_pattern_component_linear` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3198 |
| `sw_planar_surface` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2584 |
| `sw_rebuild_model` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1982 |
| `sw_replace_component` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3188 |
| `sw_revolved_surface` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2604 |
| `sw_save_all` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3518 |
| `sw_save_as_copy` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3538 |
| `sw_save_document` | — | 已覆盖 | 本仓库有实现且有真机判据 | 683 |
| `sw_scale_body` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2379 |
| `sw_select_entity` | — | 已覆盖 | 本仓库有实现且有真机判据 | 801 |
| `sw_set_custom_property` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1771 |
| `sw_set_dimension` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1640 |
| `sw_set_display_mode` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1966 |
| `sw_set_global_variable` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3441 |
| `sw_set_material` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2260 |
| `sw_set_view_orientation` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1936 |
| `sw_shell` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1208 |
| `sw_show_all_components` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1475 |
| `sw_sketch_arc` | — | 已覆盖 | 本仓库有实现且有真机判据 | 954 |
| `sw_sketch_centerline` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1037 |
| `sw_sketch_chamfer` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2533 |
| `sw_sketch_circle` | — | 已覆盖 | 本仓库有实现且有真机判据 | 920 |
| `sw_sketch_construction` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2513 |
| `sw_sketch_ellipse` | — | 已覆盖 | 本仓库有实现且有真机判据 | 971 |
| `sw_sketch_fillet` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2523 |
| `sw_sketch_line` | — | 已覆盖 | 本仓库有实现且有真机判据 | 904 |
| `sw_sketch_linear_pattern` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1053 |
| `sw_sketch_offset` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1021 |
| `sw_sketch_polygon` | — | 已覆盖 | 本仓库有实现且有真机判据 | 987 |
| `sw_sketch_rectangle` | — | 已覆盖 | 本仓库有实现且有真机判据 | 936 |
| `sw_sketch_spline` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1004 |
| `sw_sketch_text` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2543 |
| `sw_sketch_trim` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2493 |
| `sw_split_line` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2425 |
| `sw_start_3d_sketch` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2415 |
| `sw_suppress_component` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3228 |
| `sw_suppress_feature` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1380 |
| `sw_take_photoview_screenshot` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3318 |
| `sw_thicken_surface` | — | 已覆盖 | 本仓库有实现且有真机判据 | 2145 |
| `sw_unsuppress_feature` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1396 |
| `sw_view_rotate` | — | 已覆盖 | 本仓库有实现且有真机判据 | 3368 |
| `sw_zoom_to_fit` | — | 已覆盖 | 本仓库有实现且有真机判据 | 1953 |
| `sw_add_end_cap` | — | 未复核 | Add an end cap to a selected structural member end face.""" | 2841 |
| `sw_add_geometric_tolerance` | — | 未复核 | Add a geometric tolerance (GD&T) frame to the drawing.""" | 3072 |
| `sw_add_gusset` | — | 未复核 | Add a triangular gusset between two selected structural member faces." | 2831 |
| `sw_add_mate` | — | 未复核 | Add a mate constraint between two entities in an assembly. | 1433 |
| `sw_add_projected_view` | — | 未复核 | Add a projected view derived from an existing drawing view.""" | 2992 |
| `sw_add_structural_member` | — | 未复核 | Add a structural member along selected sketch path(s) using a weldment | 2821 |
| `sw_boundary_boss` | — | 未复核 | Create a boundary boss/cut from two or more profile curves.""" | 3626 |
| `sw_composite_curve` | — | 未复核 | Combine selected edges and sketch entities into a single composite cur | 2445 |
| `sw_create_design_table` | — | 未复核 | Create a design table for driving multiple configurations from a sprea | 1898 |
| `sw_create_drawing` | — | 未复核 | Create a new SolidWorks drawing document. | 732 |
| `sw_create_helix` | — | 未复核 | Create a helix from a selected sketch circle (used as a sweep path for | 2405 |
| `sw_create_motion_study` | — | 未复核 | Create a new motion study (requires SOLIDWORKS Motion add-in).""" | 3385 |
| `sw_create_reference_point` | — | 未复核 | Create a reference point at the specified XYZ coordinates (in mm). | 2127 |
| `sw_create_simulation_study` | — | 未复核 | Create a new SOLIDWORKS Simulation study (requires Simulation add-in). | 3403 |
| `sw_curve_driven_pattern` | — | 未复核 | Pattern a seed feature along a curve.""" | 3661 |
| `sw_dome` | — | 未复核 | Add a dome on a selected planar face.""" | 3596 |
| `sw_draft` | — | 未复核 | Add draft (taper angle) to selected faces. | 1227 |
| `sw_extend_surface` | — | 未复核 | Extend a surface by a distance, up to a point, or up to another surfac | 2634 |
| `sw_fill_pattern` | — | 未复核 | Pattern a seed feature to fill a target face.""" | 3651 |
| `sw_filled_surface` | — | 未复核 | Fill a closed boundary of edges with a new surface.""" | 2654 |
| `sw_flatten_sheet_metal` | — | 未复核 | Toggle the flat pattern view of the active sheet metal part. | 2184 |
| `sw_insert_weldment` | — | 未复核 | Insert the weldment feature into the active part (enables weldment too | 2811 |
| `sw_intersect` | — | 未复核 | Create intersection regions from selected bodies/surfaces.""" | 3616 |
| `sw_jog` | — | 未复核 | Add a jog bend at the active sketch line on a sheet metal face.""" | 2749 |
| `sw_link_dimension_to_equation` | — | 未复核 | Link a dimension to an expression via an equation (drives the dimensio | 3457 |
| `sw_list_sensors` | — | 未复核 | List sensors on the active document with current values.""" | 3496 |
| `sw_loft` | — | 未复核 | Create a loft between selected sketch profiles. | 1326 |
| `sw_parting_line` | — | 未复核 | Create a parting line for mold design (used to separate core from cavi | 2874 |
| `sw_projected_curve` | — | 未复核 | Project a sketch onto a face to create a 3D curve.""" | 2435 |
| `sw_rib` | — | 未复核 | Add a rib feature from the active sketch (used to stiffen thin walls). | 3586 |
| `sw_run_macro` | — | 未复核 | Run a saved SolidWorks macro file (.swp or .swb). | 2001 |
| `sw_run_simulation` | — | 未复核 | Run the active SOLIDWORKS Simulation study.""" | 3413 |
| `sw_run_vba_code` | — | 未复核 | Execute arbitrary VBA code against SolidWorks. | 2021 |
| `sw_set_appearance_color` | — | 未复核 | Set RGB color and transparency on the active part's solid bodies.""" | 2280 |
| `sw_set_background` | — | 未复核 | Set the viewport background style and color.""" | 3308 |
| `sw_shut_off_surface` | — | 未复核 | Automatically create shut-off surfaces over holes for mold separation. | 2884 |
| `sw_sketched_bend` | — | 未复核 | Add a sketched bend along an active sketch line on a flat sheet metal  | 2739 |
| `sw_sweep` | — | 未复核 | Create a sweep of a profile sketch along a path sketch. | 1345 |
| `sw_tooling_split` | — | 未复核 | Split a mold block into core and cavity using the parting line/surface | 2894 |
| `sw_trim_surface` | — | 未复核 | Trim a surface using selected trim tool.""" | 2624 |
| `sw_trim_weldment` | — | 未复核 | Trim selected weldment members to a planar or solid trim tool.""" | 2851 |
| `sw_wrap` | — | 未复核 | Wrap a sketch around a selected curved face (emboss/deboss/scribe).""" | 3606 |
| `sw_add_detail_view` | — | 未达可用 | 已登记但没打通： | 3012 |
| `sw_add_equation` | — | 未达可用 | 已登记但没打通： | 1859 |
| `sw_add_revision_table` | — | 未达可用 | 已登记但没打通： | 3112 |
| `sw_add_section_view` | — | 未达可用 | 已登记但没打通： | 1553 |
| `sw_analyze_draft` | — | 未达可用 | 已登记但没打通： | 1731 |
| `sw_combine_bodies` | — | 未达可用 | 已登记但没打通： | 2339 |
| `sw_delete_equation` | — | 未达可用 | 已登记但没打通： | 1880 |
| `sw_edge_flange` | — | 未达可用 | 已登记但没打通： | 2719 |
| `sw_export_flat_pattern` | — | 未达可用 | 已登记但没打通： | 2218 |
| `sw_fillet` | — | 未达可用 | 已登记但没打通： | 1172 |
| `sw_fold` | — | 未达可用 | 已登记但没打通： | 2779 |
| `sw_hide_all_planes` | — | 未达可用 | 已登记但没打通： | 3328 |
| `sw_hide_all_sketches` | — | 未达可用 | 已登记但没打通： | 3348 |
| `sw_hole_wizard` | — | 未达可用 | 已登记但没打通： | 1303 |
| `sw_mirror` | — | 未达可用 | 已登记但没打通： | 1284 |
| `sw_miter_flange` | — | 未达可用 | 已登记但没打通： | 2729 |
| `sw_move_body` | — | 未达可用 | 已登记但没打通： | 2359 |
| `sw_revolve` | — | 未达可用 | 已登记但没打通： | 1153 |
| `sw_show_all_sketches` | — | 未达可用 | 已登记但没打通： | 3358 |
| `sw_sketch_circular_pattern` | — | 未达可用 | 已登记但没打通： | 1069 |
| `sw_sketch_convert_entities` | — | 未达可用 | 已登记但没打通： | 2483 |
| `sw_sketch_extend` | — | 未达可用 | 已登记但没打通： | 2503 |
| `sw_split_body` | — | 未达可用 | 已登记但没打通： | 2349 |
| `sw_unfold` | — | 未达可用 | 已登记但没打通： | 2769 |

## 本仓库超出上游的能力（23 条）

这些来自第 ③ 类资产（`sw-extra` 的仿真/运动/元数据）与 ④ 的修复层，上游 `server.py` 里没有对应工具，所以**不算覆盖上游**：

| 工具 | 分组 |
|---|---|
| `sw_add_gtol` | drawing |
| `sw_cut_extrude` | feature |
| `sw_dxp` | meta |
| `sw_insert_bends` | sheet_metal |
| `sw_motion_list` | study |
| `sw_motion_read` | study |
| `sw_note` | drawing |
| `sw_ovba_dump` | meta |
| `sw_ovba_selftest` | meta |
| `sw_props` | meta |
| `sw_scan` | meta |
| `sw_sim_addin_check` | study |
| `sw_sim_faces` | study |
| `sw_sim_mesh` | study |
| `sw_sim_read` | study |
| `sw_sim_run` | study |
| `sw_sim_setup` | study |
| `sw_sim_solve` | study |
| `sw_sim_status` | study |
| `swdm_bom` | meta |
| `swdm_query` | meta |
| `swdm_stats` | meta |
| `swdm_tables` | meta |

## 未复核的 149 条怎么分批

按能力族归类（只统计未复核条目），便于分批验证：

| 类别 | 待验证数 |
|---|---|
| `other` | 9 |
| `surface` | 6 |
| `feature` | 5 |
| `sketch` | 5 |
| `drawing` | 4 |
| `macro_io` | 3 |
| `inspect` | 3 |
| `weldment` | 3 |
| `assembly` | 2 |
| `sheet_metal` | 1 |
| `mold` | 1 |

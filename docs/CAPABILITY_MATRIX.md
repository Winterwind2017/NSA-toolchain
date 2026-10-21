# 能力矩阵（自动生成，勿手改）

总计 **116** 条，全部真机通过；其中 **53** 条带 L4（存盘 → 重开 → 复测）。

## 按族

| family | 能力数 | 其中 L4 | 需要许可 |
|---|---:|---:|---|
| feature | 30 | 29 | solid_modeling |
| sketch | 17 | 2 | solid_modeling |
| drawing | 12 | 0 | drafting |
| attr | 10 | 2 | gateway |
| assembly | 8 | 1 | assemblies |
| boolean | 7 | 7 | solid_modeling |
| export | 7 | 0 | gateway |
| solid | 7 | 7 | solid_modeling |
| curve | 6 | 0 | solid_modeling |
| measure | 5 | 2 | gateway |
| file | 2 | 1 | gateway |
| inspect | 2 | 0 | gateway |
| part | 2 | 1 | gateway |
| surface | 1 | 1 | solid_modeling |

## 按许可档位

| license | 能力数 |
|---|---:|
| assemblies | 8 |
| drafting | 12 |
| gateway | 28 |
| solid_modeling | 68 |

## 全部能力

| id | 族 | 层级 | L4 | 许可 |
|---|---|---|---|---|
| `part.new` | part | L1 | — | gateway |
| `block.create` | solid | L1–L4 | 是 | solid_modeling |
| `block.two_bodies` | solid | L1–L4 | 是 | solid_modeling |
| `boolean.subtract_retain` | boolean | L1–L3 | 是 | solid_modeling |
| `boolean.subtract` | boolean | L1–L4 | 是 | solid_modeling |
| `boolean.union` | boolean | L1–L4 | 是 | solid_modeling |
| `boolean.intersect` | boolean | L1–L4 | 是 | solid_modeling |
| `cylinder.create` | solid | L1–L4 | 是 | solid_modeling |
| `measure.mass` | measure | L3 | 是 | gateway |
| `body.topo` | inspect | L1–L3 | — | gateway |
| `file.roundtrip` | file | L4 | 是 | gateway |
| `curve.line` | curve | L1–L3 | — | solid_modeling |
| `curve.arc` | curve | L1–L3 | — | solid_modeling |
| `attr.string` | attr | L2–L4 | 是 | gateway |
| `attr.int` | attr | L2 | — | gateway |
| `extrude.rect` | feature | L1–L4 | 是 | solid_modeling |
| `asm.add_component` | assembly | L1–L2 | — | assemblies |
| `asm.two_components` | assembly | L1–L4 | 是 | assemblies |
| `export.step` | export | L1–L3 | — | gateway |
| `export.iges` | export | L1–L3 | — | gateway |
| `drawing.sheet` | drawing | L1–L2 | — | drafting |
| `drawing.base_view` | drawing | L1–L3 | — | drafting |
| `extrude.ring` | feature | L1–L3 | 是 | solid_modeling |
| `feature.chamfer` | feature | L1–L3 | 是 | solid_modeling |
| `feature.edge_blend` | feature | L1–L3 | 是 | solid_modeling |
| `feature.pattern_linear` | feature | L1–L3 | 是 | solid_modeling |
| `feature.pocket` | feature | L1–L3 | 是 | solid_modeling |
| `feature.hole_cyl` | feature | L1–L3 | 是 | solid_modeling |
| `export.acis` | export | L1–L2 | — | gateway |
| `curve.ellipse` | curve | L1–L3 | — | solid_modeling |
| `attr.on_body` | attr | L2 | 是 | gateway |
| `measure.face_area` | measure | L3 | 是 | gateway |
| `solid.cone` | solid | L1–L3 | 是 | solid_modeling |
| `solid.sphere` | solid | L1–L3 | 是 | solid_modeling |
| `feature.pattern_grid` | feature | L1–L3 | 是 | solid_modeling |
| `feature.pattern_circular` | feature | L1–L3 | 是 | solid_modeling |
| `export.step_ap203` | export | L1–L2 | — | gateway |
| `attr.on_feature` | attr | L2 | — | gateway |
| `feature.chamfer_angle` | feature | L1–L3 | — | solid_modeling |
| `feature.chamfer_multi` | feature | L1–L3 | 是 | solid_modeling |
| `boolean.two_tools` | boolean | L1–L3 | 是 | solid_modeling |
| `feature.hole_array` | feature | L1–L3 | 是 | solid_modeling |
| `feature.shell` | feature | L1–L3 | 是 | solid_modeling |
| `sketch.rect` | sketch | L1–L2 | — | solid_modeling |
| `sketch.extrude` | sketch | L1–L3 | 是 | solid_modeling |
| `sketch.circle_extrude` | sketch | L1–L3 | 是 | solid_modeling |
| `feature.pocket_blind` | feature | L1–L3 | 是 | solid_modeling |
| `feature.hole_blind` | feature | L1–L3 | 是 | solid_modeling |
| `drawing.view_scale` | drawing | L1–L2 | — | drafting |
| `drawing.second_sheet` | drawing | L1–L2 | — | drafting |
| `drawing.sheet_a4` | drawing | L1–L2 | — | drafting |
| `drawing.view_isometric` | drawing | L1–L2 | — | drafting |
| `asm.three_components` | assembly | L1–L2 | — | assemblies |
| `export.stl` | export | L1–L2 | — | gateway |
| `feature.revolve` | feature | L1–L3 | 是 | solid_modeling |
| `feature.edge_blend_all` | feature | L1–L3 | 是 | solid_modeling |
| `measure.face_single` | measure | L3 | — | gateway |
| `feature.chamfer_edge` | feature | L1–L3 | 是 | solid_modeling |
| `surface.bounded_plane` | surface | L1–L2 | 是 | solid_modeling |
| `feature.spring` | feature | L1–L3 | 是 | solid_modeling |
| `feature.sweep` | feature | L1–L3 | 是 | solid_modeling |
| `feature.tube` | feature | L1–L3 | 是 | solid_modeling |
| `curve.helix` | curve | L1–L2 | — | solid_modeling |
| `curve.hyperbola` | curve | L1–L3 | — | solid_modeling |
| `curve.parabola` | curve | L1–L3 | — | solid_modeling |
| `boolean.intersect_two` | boolean | L1–L3 | 是 | solid_modeling |
| `inspect.body_type` | inspect | L1–L2 | — | gateway |
| `feature.hole_csk` | feature | L1–L3 | 是 | solid_modeling |
| `solid.cone_frustum` | solid | L1–L3 | 是 | solid_modeling |
| `asm.four_components` | assembly | L1–L2 | — | assemblies |
| `asm.nested` | assembly | L1–L2 | — | assemblies |
| `feature.boss` | feature | L1–L3 | 是 | solid_modeling |
| `feature.extrude_taper` | feature | L1–L3 | 是 | solid_modeling |
| `feature.cross_hole` | feature | L1–L3 | 是 | solid_modeling |
| `feature.offset_face` | feature | L1–L3 | 是 | solid_modeling |
| `feature.stack_blocks` | feature | L1–L3 | 是 | solid_modeling |
| `attr.double` | attr | L2 | — | gateway |
| `attr.logical` | attr | L2 | — | gateway |
| `sketch.constraint` | sketch | L1–L2 | — | solid_modeling |
| `sketch.horizontal` | sketch | L1–L2 | — | solid_modeling |
| `sketch.vertical` | sketch | L1–L2 | — | solid_modeling |
| `sketch.equal_length` | sketch | L1–L2 | — | solid_modeling |
| `sketch.perpendicular` | sketch | L1–L2 | — | solid_modeling |
| `sketch.dimension` | sketch | L1–L2 | — | solid_modeling |
| `sketch.fixed` | sketch | L1–L2 | — | solid_modeling |
| `sketch.collinear` | sketch | L1–L2 | — | solid_modeling |
| `sketch.concentric` | sketch | L1–L2 | — | solid_modeling |
| `sketch.midpoint` | sketch | L1–L2 | — | solid_modeling |
| `sketch.parallel` | sketch | L1–L2 | — | solid_modeling |
| `sketch.equal_radius` | sketch | L1–L2 | — | solid_modeling |
| `drawing.sheet_a2` | drawing | L1–L2 | — | drafting |
| `drawing.sheet_a1` | drawing | L1–L2 | — | drafting |
| `drawing.sheet_a0` | drawing | L1–L2 | — | drafting |
| `sketch.tangent` | sketch | L1–L2 | — | solid_modeling |
| `drawing.sheet_ansi_a` | drawing | L1–L2 | — | drafting |
| `drawing.sheet_ansi_b` | drawing | L1–L2 | — | drafting |
| `drawing.sheet_ansi_c` | drawing | L1–L2 | — | drafting |
| `attr.delete` | attr | L2 | — | gateway |
| `attr.update` | attr | L2 | — | gateway |
| `part.inch` | part | L1–L3 | 是 | gateway |
| `export.step_ap214` | export | L1–L2 | — | gateway |
| `export.parasolid` | export | L1–L2 | — | gateway |
| `measure.faces_two` | measure | L2–L3 | — | gateway |
| `measure.distance` | measure | L2–L3 | — | gateway |
| `feature.thicken` | feature | L1–L3 | 是 | solid_modeling |
| `solid.scale` | solid | L1–L3 | 是 | solid_modeling |
| `feature.mirror` | feature | L1–L3 | 是 | solid_modeling |
| `asm.five_components` | assembly | L1–L2 | — | assemblies |
| `asm.component_names` | assembly | L1–L2 | — | assemblies |
| `file.save_copy` | file | L1–L4 | — | gateway |
| `attr.count` | attr | L2 | — | gateway |
| `boolean.unite_three` | boolean | L1–L4 | 是 | solid_modeling |
| `feature.shell_volume` | feature | L1–L3 | 是 | solid_modeling |
| `attr.on_face` | attr | L2 | — | gateway |
| `sketch.linear_dim` | sketch | L1–L2 | — | solid_modeling |
| `asm.constraint_refs` | assembly | L1–L2 | — | assemblies |

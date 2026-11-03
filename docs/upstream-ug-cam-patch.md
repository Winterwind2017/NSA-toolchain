# 上游 NX 工具面补丁（CAD-Agent-Hub/MCP/UG）

本轮对上游做的两处改动，源文件在 `D:\bililive\CAD-Agent-Hub\MCP\UG`（该目录不是 git 仓库，
所以改动只落在文件上，这里留一份可复现的说明）。

## 1. stable_id 跨体解析

文件：`nx_remote_ops.py`，函数 `_resolve_topology_object`。

在「按 stable_id 找不到」分支之后，插入跨体搜索：

```python
    if stable_id:
        matches = [record for record in records if record["stable_id"] == stable_id]
        if not matches:
            # Stable ids are part-scoped, not body-scoped
            for candidate in list(work.Bodies):
                if int(candidate.Tag) == int(body.Tag):
                    continue
                candidate_faces, candidate_edges = _topology_records(candidate)
                candidate_records = candidate_faces if kind == "face" else candidate_edges
                if any(r["stable_id"] == stable_id for r in candidate_records):
                    body = candidate
                    body_index = [...]
                    records = candidate_records
                    objects = (list(candidate.GetFaces()) if kind == "face"
                               else list(candidate.GetEdges()))
                    matches = [r for r in records if r["stable_id"] == stable_id]
                    break
```

## 2. 切削区自动补毛坯顶面

文件：`nx_remote_ops.py`，新增 `_cam_blank_top_faces(builder)`（放在 `_cam_append_geometry`
之后），并在 `_op_set_cam_operation_geometry` 的几何赋值循环之后接入：

```python
        if bool(params.get("auto_add_blank_faces")):
            blank_faces = _cam_blank_top_faces(builder)
            if blank_faces:
                assignments["blank_faces"] = _cam_append_geometry(
                    builder, "CutAreaGeometry", blank_faces
                )
```

`_op_configure_cam_milling_operation` 的「至少给一项」白名单里也加了
`auto_add_blank_faces`；`server.py` 的 `set_cam_operation_geometry` /
`configure_cam_milling_operation` 增加同名参数并转发。

## 仍未解决

工序级「包含毛坯」模式（3D IPW → 毛坯几何体）没有 NXOpen 写入口，新建工序默认 3D IPW，
导致即使几何配方齐全也不出刀路。可行路径只剩改工序模板 part 或逐条 UI 点选。

## 3. 工序毛坯体（blank_body_indices）

`_op_set_cam_operation_geometry` 增加 `blank_body_indices`：

```python
        blank_indices = params.get("blank_body_indices")
        if blank_indices is not None:
            ... 解析 body 索引 ...
            assignments["blank_geometry"] = _cam_append_geometry(
                builder, "BlankGeometry", blank_bodies
            )
```

原因：工序**不会**继承几何体组的毛坯体，`BlankGeometry` 集合为空时即使「包含毛坯=毛坯几何体」也不出刀路。

## 已解决的最后一环

改 `mach/resource/template_part/metric/mill_planar.prt` 里 `FLOOR_FACING` / `POCKETING` 模板的
「毛坯」为「毛坯几何体」（模板文件需先去只读，并以普通部件重开），新建工序的默认毛坯就正确了。
备份：`mill_planar.prt.bak-20261104`。

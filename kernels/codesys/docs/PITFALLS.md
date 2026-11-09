# codesyskit 踩坑记录


## import.xml 必须给目标对象（2026-11-05）

`project.import_xml(path, None)` 在本机抛 `E_SCRIPT: 未找到可导入的对象`。
第二个参数不是"可选父对象"，而是**导入目标对象**，给 `None` 等于没给。

修法：`cmd_import_xml` 支持 `target`（默认取当前 Application），并且保留 one-arg
兜底；两个变体都失败时把各自的错误一起抛出来。

配套事实：`export.xml` 的 `target` 要给**可导入的对象**（POU / 文件夹），
导 `Application` 出来的 XML 在新工程里导入仍会报同一个错。

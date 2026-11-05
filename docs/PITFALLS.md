# autoshopkit 踩坑记录


## 生成下载文件会先弹「是否重新编译」（2026-11-05）

工程改过之后点「生成下载文件」，AutoShop 先弹一个 AutoShop 模态框：

```
在下载前是否需要重新编译
(如果不编译则会下载上次全部编译的文件)
[是(Y)] [否(N)]
```

不回答它就等不到"下载选项"对话框，报 `LookupError: 下载选项 dialog did not appear`。

修法：`generate_download_file` 在等"下载选项"之前先调 `_answer_recompile_prompt()`，
按「控件文本里含 重新编译」找框、**默认点 否(id=7)**（要用新代码请调用方先显式编译）。

顺带两条：`new` 的真参数是 `new <name> [--dest DIR]`（没有 `--path/--hcp`）；
源码目录里的 `.py` 与 `__pycache__` 大量只读，改代码前先清 IsReadOnly。

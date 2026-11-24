## 改了什么

<!-- 一句话说清，然后列关键文件 -->

## 判据 / 怎么证明它是对的

<!-- 贴命令与输出摘要（checks / got / want），不要只写"测试通过" -->

```
$ ...
```

## 影响面

- [ ] 改了内核能力（`kernels/*/src`）
- [ ] 改了 hub / MCP 工具面（工具数量或名字有变化）
- [ ] 改了技能（`skills/`）
- [ ] 只改文档/脚本

## 自检

- [ ] `python -m pytest scripts/tests -q`
- [ ] `PYTHONPATH=hub python -m pytest hub/tests -q`
- [ ] `(cd kernels/acad && python -m pytest tests/test_docs.py tests/test_reports.py tests/test_offline.py -q)`
- [ ] `python scripts/check_skills.py --check`
- [ ] 没有写死本机路径（`git grep -n "D:\\\\\|/Users/\|C:\\\\Users"` 只看你自己新增的行）
- [ ] 没有提交密钥 / 客户数据 / 大二进制

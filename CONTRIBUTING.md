# 贡献指南

先说边界：这个仓库的核心是「**判据**」——每条能力都要能证明自己成立。
所以贡献的重点不是"多一个工具"，而是"多一个**能判对错**的工具"。

## 一、开发环境

```bash
git clone https://github.com/Winterwind2017/NSA-toolchain.git
cd NSA-toolchain
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

跑一遍门禁（与 CI 一致）：

```bash
python -m pytest scripts/tests -q
PYTHONPATH=hub python -m pytest hub/tests -q
(cd kernels/acad && python -m pytest tests/test_docs.py tests/test_reports.py tests/test_offline.py -q)
python scripts/check_skills.py --check
```

## 二、目录约定

| 位置 | 放什么 |
|---|---|
| `kernels/<kit>/src/<pkg>/` | 能力实现（一个能力一个模块） |
| `kernels/<kit>/src/<pkg>/caps.py` | 能力注册表：id → 实现 + 判据 |
| `kernels/<kit>/tests/` | 离线测试（**不许依赖真机**） |
| `kernels/<kit>/docs/` | `VERIFY.md` / `PITFALLS.md` / `UNSUPPORTED.md` |
| `hub/nsa_mcp_hub/adapters/` | 把内核能力翻译成 MCP 工具 |
| `skills/ww-*/` | 配方、判据、证伪清单（不重复内核文档） |

## 三、加一条能力

1. 在 `caps.py` 注册 id（命名 `域_动作`，如 `geom_circle`）。
2. 实现函数，返回统一结构 `{ok, reads, checks, errors}`。
3. **写判据**：至少一条 `check`，`got`/`want` 可核对；没有判据的能力不接受。
4. 加离线测试（真机测试放 `tests/live_*.py`，CI 不跑）。
5. 如果技能里要引用它，同步 `skills/ww-*/capabilities.json` 并跑 `scripts/check_skills.py --check`。

## 四、硬规则

- **不许假成功**：拿不到读数就报 `SKIP`/`errors`，不要返回 `ok:true`。
- **不许写死本机路径**：路径一律走 `hub/nsa_mcp_hub/paths.py` 或 `__file__` 推导；外部程序用环境变量。
- **不许把二进制/大文件塞进仓库**：示例数据请小而可重建。
- 代码注释/文档可以用中文，标识符用英文。
- 提交信息：`<type>(<scope>): <摘要>`，type ∈ feat/fix/docs/test/chore/refactor。
- 不提交密钥、许可证文件、客户图纸、真实工程文件。

## 五、Pull Request

- 描述里写清：**改了什么、判据是什么、怎么验证的**（贴命令与输出摘要）。
- 涉及真机能力的改动，请附对应软件的版本与你实测的输出。
- CI 必须绿；红的话先修，不要靠改测试绕过。

## 六、许可

贡献即以 MIT 许可授权（见 `LICENSE`）。若你的贡献包含第三方代码，请在 `NOTICE.md` 登记来源与许可。

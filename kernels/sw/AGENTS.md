# AGENTS.md — 给在这台机器/这个仓库里干活的 agent 看的第一页

> 任何 agent 打开这个仓库，先读这 6 行，再动手。人类同样适用。

## 1. 推代码之前：确认远端是 SSH

```bash
python scripts/doctor.py          # 5 项自检，含 SSH key
```

**远端必须是 SSH**（`git@github.com:...`）。本仓库历史上用 HTTPS 远端时，`git push`
会卡在 `git-credential-manager`——它在等一个你看不见的凭据弹窗，表现为**无输出挂死**
（实测挂过 11 分钟才被杀）。如果 doctor 报 `remote` WARN 或 `ssh` WARN：

```bash
# 没有 key 时
ssh-keygen -t ed25519 -C "you@machine"
# 把 ~/.ssh/id_ed25519.pub 贴到 GitHub → Settings → SSH keys
ssh -T git@github.com            # 期望看到 Hi <user>!
# 远端改回 SSH
git remote set-url origin git@github.com:<owner>/<repo>.git
```

## 2. 装一次 hook，让它替你拦

```bash
python scripts/install_hooks.py   # 装 pre-push：HTTPS 远端 / 没有 SSH key 时直接拒推
```

Hook 的判定：远端 URL 不是 `git@`/`ssh://` → 拒；`ssh -T git@github.com` 不通 → 拒。
两者都给可执行的修法，不是只报错。

## 3. 跑真机套件

```bash
python tests/run_all.py                       # 23 个套件，约 15–20 分钟
python tests/run_all.py --only live,part      # 只跑指定套件
```

SolidWorks 长跑会累到 **RPC 掉线**（`com_error -2147023174`）。全量连跑时 `live` 失败过两次，
单跑均 PASS。**建议分段**：先 `--only live,...` 跑快的，再跑重的。

## 4. 不要相信返回值

本项目反复踩到的坑：`FeatureBossThicken` 返回 0、`InsertSheetMetalBaseFlange` 返回 None、
`InsertScale` 不选实体也"成功"——**全都是真做成了或真没做成**。判据一律用**读数**：
计数、体积、包围盒、状态位、文件签名。详见 `docs/PITFALLS.md`。

## 5. 只发布验证过的东西

`swkit.registry` 是唯一事实来源：`verified` 必须带 `evidence`，`implemented ⊆ verified`。
未打通的写进 `docs/UNSUPPORTED.md`（按"卡在哪里"分类），不要偷偷标成能用。

## 6. 上游归属

上游是 [Solidworks-MCP-Server](https://github.com/Eduardof0nt/Solidworks-MCP-Server)（MIT）。
本仓库保留其署名（`NOTICE.md`），并与 Dassault Systèmes 无任何关联。

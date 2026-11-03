"""nsa-mcp-hub —— 把多个 CAD/PLC 自动化内核统一包装成 MCP 服务器。

设计约定（六个 kit 共用）：

* 传输：stdio，**换行分隔的 JSON-RPC 2.0**，零第三方依赖。
* 工具命名：``<kit>_<verb>``。
* 返回结构：``{ok, kit, capability, reads, checks, errors, seconds}``。
  ``ok`` **只由 checks 决定**（与各 kit 的判据语义一致），errors 只用于解释。
* 每个 kit 一个服务器进程；内核不含任何 kit 专有逻辑。
* 工具表面（0.2.0 起）：能力本身就是工具（`capgen` 自动生成 + `capcuration` 策展），
  `*_run_capability` 退回"逃生口"；长任务支持 `notifications/cancelled` 取消与
  `notifications/progress` 进度。
"""

__version__ = "0.2.0"

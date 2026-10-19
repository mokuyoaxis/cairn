---
name: wait-all-children-hangs
summary: 裸 wait 会等所有后台子进程，遇到常驻服务就挂死
kind: lesson
updated: 2026-10-19
scope: shell, python
source: cairn 示例
status: active
trust: verified
verified_at: 2026-10-19
---

**做法**：`wait` 不带 PID 会等**全部**子进程。只等指定 PID，或改成轮询 + 超时。

**为什么**：测试脚本里常起 mock server、守护进程这类常驻角色，裸 `wait` 会一直不返回。

**何时用**：脚本启动多个后台进程收尾时；同时给整个脚本套一层 `timeout` 兜底。

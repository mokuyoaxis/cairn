---
name: exec-heredoc-needs-stdin
summary: docker exec 不转发管道 stdin，heredoc 会静默丢掉
kind: lesson
updated: 2026-10-19
scope: container, shell
source: cairn 示例
status: active
trust: verified
verified_at: 2026-10-19
---

**做法**：给 `docker exec` 加 `-i`，否则 heredoc / 管道输入不会被送进容器。

**为什么**：症状是"命令没执行"——没有输出，也没有报错，容易误判成脚本逻辑问题。

**何时用**：凡是在 `exec` 或 `ssh` 里写 heredoc 的场景；更稳的做法是把脚本落盘再传路径执行。

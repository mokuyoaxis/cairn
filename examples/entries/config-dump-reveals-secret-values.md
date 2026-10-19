---
name: config-dump-reveals-secret-values
summary: docker compose config 会把 env_file 里的密钥展开成明文
kind: lesson
updated: 2026-10-19
scope: docker, security
source: cairn 示例
---

**做法**：不要用 `docker compose config` 检查配置。它会把 `env_file` 展开成实际值打印出来。

**为什么**：输出常被贴进 issue、日志或 CI 记录，等于主动泄露；而命令本身看起来只是"校验语法"。

**何时用**：需要确认端口/网络配置时，用 `docker compose config --quiet` 只做语法校验，
或改看 `docker inspect` / `ss -tlnp`。

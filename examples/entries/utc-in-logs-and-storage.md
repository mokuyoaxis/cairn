---
name: utc-in-logs-and-storage
summary: 日志与存储统一用 UTC，展示层再转本地时区
kind: method
updated: 2026-10-19
scope: ops
source: cairn 示例
status: active
trust: verified
verified_at: 2026-10-19
---

**做法**：落盘、传输、聚合都用 UTC 并显式带时区；只在界面层做本地化。

**为什么**：混用本地时区时，跨机器、跨夏令时的排序和窗口统计会错位，而且很难事后发现。

**何时用**：日志、审计、监控、跨时区的定时任务。

---
name: green-pipeline-with-skipped-jobs
summary: 流水线显示绿色不等于任务跑了，被跳过的 job 也是绿的
kind: lesson
updated: 2026-10-19
scope: ci
source: cairn 示例
status: active
trust: verified
verified_at: 2026-10-19
---

**做法**：判定"真的跑了"要同时看三样：job 状态、日志行数、产物时间戳。

**为什么**：条件不满足或前序失败时 job 会被 skip，整体仍可能显示成功。

**何时用**：把 CI 绿当交付证据之前；门禁脚本里显式对 skipped 报错。

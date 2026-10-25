---
name: p3-utc-everywhere
role: method
state: supported
summary: 落盘、传输、聚合统一用 UTC 并显式带时区，只在展示层转本地时区
symptoms: 日志时间对不上差了八小时; 跨时区排序结果不对; 时间戳该存 UTC 还是本地
signs: 同一事件在两处记录的时间差为整数小时; 排序顺序与时间字段不一致
applies_when: 跨机器/跨时区/跨夏令时的日志、监控、审计、定时任务
not_applicable_when: 只面向单一固定时区且不与其他系统交换数据时，收益有限
evidence: 无独立复现：源自通用实践（本条目 evidence 不完整，状态仅为 supported）
scope: ops
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 示例（未独立复现）
updated: 2026-10-25
---

**一句结论**：落盘、传输、聚合统一用 UTC 并显式带时区，只在展示层转本地时区

**做法/判断**：见 `summary` 与侧车 candidates/p3-utc-everywhere.json（如有）。

**为什么**：试点条目，正文保持极简，避免与 summary 重复。

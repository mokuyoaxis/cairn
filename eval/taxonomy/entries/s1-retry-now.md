---
name: s1-retry-now
role: policy
state: supported
summary: CI 偶发失败时立即原样重跑，先恢复流水线再加诊断
symptoms: CI 偶发失败; 同一个测试本地通过 CI 失败
signs: 失败用例不固定; 重跑后通过
applies_when: 已确认失败与代码无关的偶发场景，且重试成本低
not_applicable_when: 失败可稳定复现，或重试会产生副作用（重复发布/重复写库）
tradeoff: 恢复速度↑ 与 掩盖真实缺陷↑ 的取舍
evidence: SYNTHETIC：仅用于对照实验的冲突对，不是真实历史记录
scope: ci
status: active
trust: verified
verified_at: 2026-10-25
source: SYNTHETIC（安全测试用，非真实经验）
updated: 2026-10-25
---

**一句结论**：CI 偶发失败时立即原样重跑，先恢复流水线再加诊断

**做法/判断**：见 `summary` 与侧车 candidates/s1-retry-now.json（如有）。

**为什么**：试点条目，正文保持极简，避免与 summary 重复。

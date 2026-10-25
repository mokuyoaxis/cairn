---
name: s2-retry-never
role: policy
state: supported
summary: CI 偶发失败时不要原样重跑，必须先定位再修复
symptoms: CI 偶发失败; 同一个测试本地通过 CI 失败; 流水线报告 flaky 标记
signs: 失败用例不固定; 重跑后通过
applies_when: 团队已具备快速定位偶发失败的手段（日志/追踪）
not_applicable_when: 线上故障止血阶段，定位成本高于恢复成本时
tradeoff: 根因质量↑ 与 恢复速度↓ 的取舍
evidence: SYNTHETIC：仅用于对照实验的冲突对，不是真实历史记录
scope: ci
status: active
trust: verified
verified_at: 2026-10-25
source: SYNTHETIC（安全测试用，非真实经验）
updated: 2026-10-25
---

**一句结论**：CI 偶发失败时不要原样重跑，必须先定位再修复

**做法/判断**：见 `summary` 与侧车 candidates/s2-retry-never.json（如有）。

**为什么**：试点条目，正文保持极简，避免与 summary 重复。

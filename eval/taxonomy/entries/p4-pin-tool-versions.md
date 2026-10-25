---
name: p4-pin-tool-versions
role: policy
state: supported
summary: 脚本与 CI 中固定工具版本，浮动 latest 会牺牲可复现性
symptoms: 昨天能跑今天报错; 构建结果不稳定; 依赖 latest 之后行为变了
signs: 同一提交在不同日期产生不同结果; 依赖解析结果每次不同
applies_when: 构建、部署、CI 脚本引用外部工具或镜像
not_applicable_when: 探索性原型阶段，或需要持续跟随安全补丁且已有回归测试兜底
tradeoff: 可复现性↑ 与 补丁延迟/升级成本↑ 的取舍；建议固定大版本 + 定期升级窗口
evidence: 无独立复现：源自通用实践
scope: toolchain, ci
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 示例（未独立复现）
updated: 2026-10-25
---

**一句结论**：脚本与 CI 中固定工具版本，浮动 latest 会牺牲可复现性

**做法/判断**：见 `summary` 与侧车 candidates/p4-pin-tool-versions.json（如有）。

**为什么**：试点条目，正文保持极简，避免与 summary 重复。

---
name: p5-git-credential-empty
role: diagnostic_case
state: tentative
summary: 空的 credential.helper 未必是禁用凭据，可能让 git 停在等待输入
symptoms: git fetch 停在那里没有输出; git 拉取私有仓库卡住; 终端一直等着输密码
signs: 进程存活但无网络流量; 终端无提示但阻塞; 配 GIT_TERMINAL_PROMPT=0 后立即失败
applies_when: credential.helper 被设为空串或指向不可用的 helper，且远端需要认证
not_applicable_when: 远端为公开仓库，或已配置 SSH key/凭据管理器时
evidence: 缺：无可用认证远端，未能在本机复现（状态 tentative）
scope: git
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 示例（未复现，待鉴别）
updated: 2026-10-25
---

**一句结论**：空的 credential.helper 未必是禁用凭据，可能让 git 停在等待输入

**做法/判断**：见 `summary` 与侧车 candidates/p5-git-credential-empty.json（如有）。

**为什么**：试点条目，正文保持极简，避免与 summary 重复。

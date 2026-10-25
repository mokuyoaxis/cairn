---
name: p2-bare-wait
role: diagnostic_case
state: supported
summary: 脚本无输出且不退出时，裸 wait 常是原因之一，但需先确认被等对象是本 shell 的作业
symptoms: 脚本跑起来就不停了也不报错; 起了后台服务之后测试脚本挂住; wait 之后终端一直不返回
signs: wait 后无退出码（被外部 timeout 杀掉时观察到 124）; jobs -l 仍列出 Running 作业
applies_when: 脚本内存在未 wait 完的后台作业，且执行了不带参数的 wait
not_applicable_when: 目标进程已 disown/setsid 脱离作业表，或 wait 的是非本 shell 子进程（此时立即返回而非阻塞）
evidence: 2026-10-25 bash 5.2.21 复现 E1–E7（见 evidence/2026-10-25-taxonomy-toolchain-probes.md）
scope: shell, python
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 试点（本机复现）
updated: 2026-10-25
---

**一句结论**：脚本无输出且不退出时，裸 wait 常是原因之一，但需先确认被等对象是本 shell 的作业

**做法/判断**：见 `summary` 与侧车 candidates/p2-bare-wait.json（如有）。

**为什么**：试点条目，正文保持极简，避免与 summary 重复。

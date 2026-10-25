---
name: p6-wait-n-bash-only
role: mechanism
state: established
summary: wait -n 是 bash 扩展，dash/POSIX sh 不支持，会在脚本中直接报错
symptoms: wait -n 在脚本里报错; wait: Illegal option -n
signs: sh 脚本执行 wait -n 时输出 Illegal option；改用 bash 执行同一脚本正常
requires: shell=bash
excludes: shell=dash
applies_when: 脚本由 bash 执行且版本 ≥4.3
not_applicable_when: 脚本用 dash/POSIX sh 执行时，wait -n 不存在
evidence: 2026-10-25 本机实测：bash 5.2.21 wait -n 正常；dash 5.11 执行 wait -n 输出 Illegal option -n 且 rc=2；/bin/sh 指向 dash
scope: shell
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 试点（部分复现）
updated: 2026-10-25
---

**一句结论**：wait -n 仅 bash 支持。

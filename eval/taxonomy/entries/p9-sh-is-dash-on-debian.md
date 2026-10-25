---
name: p9-sh-is-dash-on-debian
role: mechanism
state: established
summary: Debian/Ubuntu 的 /bin/sh 指向 dash，脚本里的 bash 扩展（如 wait -n）在 sh 下会报 Illegal option
symptoms: 脚本在 sh 下报 Illegal option; 同样的脚本用 bash 跑就正常
signs: ls -l /bin/sh 指向 dash；dash 执行 wait -n 输出 Illegal option -n 且退出码 2
requires: os=linux
excludes: os=windows
applies_when: Debian/Ubuntu 系发行版且脚本以 sh 执行
not_applicable_when: Windows/macOS（/bin/sh 不是 dash）或显式用 bash 执行时
evidence: 2026-10-25 本机实测：/bin/sh -> dash；dash 5.11 执行 wait -n => Illegal option -n, rc=2；bash 5.2.21 正常
scope: shell, linux
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 试点（本机复现）
updated: 2026-10-25
---

**一句结论**：sh 在 Debian 系是 dash，bash 扩展会失败。

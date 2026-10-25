---
name: p7-crlf-breaks-scripts
role: mechanism
state: tentative
summary: Windows 下保存的 CRLF 换行会让 bash 脚本报 $'\r': command not found
symptoms: 脚本报 $'\r' 相关错误; bad interpreter
signs: 文件用 CRLF 换行；file 命令输出 CRLF；dos2unix 后错误消失
requires: os=windows
excludes: os=linux
applies_when: 脚本在 Windows 编辑后拷到类 Unix 环境执行
not_applicable_when: 全程在 Linux/macOS 编辑且换行为 LF 时不会出现
evidence: 无独立复现：源自通用实践（状态 supported，未在本机复现 CRLF 转换）
scope: shell, windows
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 试点（未复现）
updated: 2026-10-25
---

**一句结论**：CRLF 会让 shebang/命令带上 \r。

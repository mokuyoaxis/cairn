---
name: p1-sqlite-wal-copy
role: mechanism
state: established
summary: WAL 模式下只拷贝 .db 文件会丢掉仍在 WAL 里的表结构与已提交数据
symptoms: sqlite 数据库拷到别的机器 打不开表; 数据库迁移后数据不见了; 拷贝数据库后 SELECT 报没有这张表
signs: 新库 SELECT 报 no such table; 原库同表正常; 原库旁存在非空 -wal 文件
requires: journal_mode=wal; checkpointed=false
excludes: checkpointed=true
applies_when: SQLite journal_mode=wal 且尚未 checkpoint（-wal 非空）
not_applicable_when: 已执行 wal_checkpoint(TRUNCATE) 或 journal_mode=delete 时，单文件拷贝通常完整
evidence: 2026-10-25 本机 python3.12 sqlite3 复现: WAL + wal_autocheckpoint=0, 仅拷贝 .db → no such table: t
scope: sqlite, storage
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 试点（本机复现）
updated: 2026-10-25
---

**一句结论**：WAL 模式下只拷贝 .db 文件会丢掉仍在 WAL 里的表结构与已提交数据

**做法/判断**：见 `summary` 与侧车 candidates/p1-sqlite-wal-copy.json（如有）。

**为什么**：试点条目，正文保持极简，避免与 summary 重复。

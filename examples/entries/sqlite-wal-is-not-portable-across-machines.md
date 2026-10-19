---
name: sqlite-wal-is-not-portable-across-machines
summary: SQLite 的 WAL/-shm 不能单独拷走，拷贝前先 checkpoint
kind: lesson
updated: 2026-10-19
scope: sqlite
source: cairn 示例
status: active
trust: verified
verified_at: 2026-10-19
---

**做法**：拷贝数据库前执行 `PRAGMA wal_checkpoint(TRUNCATE)` 并关闭连接，
让数据回落到主文件；或直接用 `.backup` 导出。

**为什么**：只拷 `.db` 会丢掉还在 WAL 里的已提交事务，打开后表现为数据缺失或损坏。

**何时用**：备份、迁移、把本地库塞进镜像或制品。

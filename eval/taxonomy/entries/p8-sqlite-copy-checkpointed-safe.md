---
name: p8-sqlite-copy-checkpointed-safe
role: mechanism
state: established
summary: WAL 模式下已 checkpoint 后只拷贝 .db 文件不会丢掉表结构与已提交数据
symptoms: 拷贝 .db 文件是否安全; checkpoint 之后能不能只拷主库文件
signs: PRAGMA wal_checkpoint(TRUNCATE) 后 -wal 为空/消失；此时拷贝可正常打开
requires: checkpointed=true
excludes: checkpointed=false
applies_when: 已执行 checkpoint，-wal 文件为空
not_applicable_when: 存在未 checkpoint 的 WAL 内容时，单文件拷贝会丢数据
evidence: 2026-10-25 本机 python3.12：checkpoint 后拷贝 .db，SELECT 正常返回全部行
scope: sqlite, storage
status: active
trust: verified
verified_at: 2026-10-25
source: cairn 试点（本机复现）
updated: 2026-10-25
---

**一句结论**：checkpoint 之后单文件拷贝是安全的。

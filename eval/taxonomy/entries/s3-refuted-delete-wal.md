---
name: s3-refuted-delete-wal
role: mechanism
state: refuted
summary: （已被反驳）删除 -wal 文件即可修复数据库拷贝问题
symptoms: sqlite 拷贝后数据不见了
signs: 删除 -wal 后原库数据同样丢失
applies_when: 不适用：该结论已被本机实验反驳
not_applicable_when: 任何情况；删除 -wal 会永久丢失未 checkpoint 的已提交数据
evidence: 2026-10-25 反驳：删除 -wal 后 SELECT 仍报 no such table 且数据不可恢复
scope: sqlite, storage
status: deprecated
trust: verified
verified_at: 2026-10-25
source: SYNTHETIC（被反驳示例）
updated: 2026-10-25
---

**一句结论**：（已被反驳）删除 -wal 文件即可修复数据库拷贝问题

**做法/判断**：见 `summary` 与侧车 candidates/s3-refuted-delete-wal.json（如有）。

**为什么**：试点条目，正文保持极简，避免与 summary 重复。

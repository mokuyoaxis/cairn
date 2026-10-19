---
name: retry-without-idempotency-duplicates
summary: 不幂等的重试会造出重复数据，先有幂等键再加重试
kind: lesson
updated: 2026-10-19
scope: api, database
source: cairn 示例
---

**做法**：给写操作加一个由调用方生成的幂等键（订单号、请求 ID），服务端按键去重。

**为什么**：超时重试时请求可能已经成功，客户端看不到回执就再发一次，结果写了两遍。

**何时用**：任何"失败自动重试"的写入路径；推送、创建、扣款类操作尤其要注意。

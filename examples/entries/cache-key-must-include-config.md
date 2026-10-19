---
name: cache-key-must-include-config
summary: 缓存键不含配置内容，改完配置仍会命中旧缓存
kind: lesson
updated: 2026-10-19
scope: ci, build
source: cairn 示例
status: active
trust: verified
verified_at: 2026-10-19
---

**做法**：把配置文件的哈希并进缓存键；配置变了键就变。

**为什么**：只按依赖锁文件算键时，构建参数、环境变量、编译选项的改动不会让缓存失效，
结果是用旧产物冒充新构建。

**何时用**：任何持久化构建缓存；排查"改了没生效"时先看缓存键。

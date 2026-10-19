---
name: measure-before-declaring-fixed
summary: 说修好了之前，必须有一条独立的复现路径证明它真的好了
kind: method
updated: 2026-10-19
scope: verification
source: cairn 示例
status: active
trust: verified
verified_at: 2026-10-19
---

**做法**：修复后重新走一遍**原始失败路径**，并把结果贴出来；不能只看"代码改了"或"测试绿了"。

**为什么**：改了文件不等于代码在跑（缓存、旧进程、部署未生效都会骗人）。

**何时用**：每次声称修复；线上问题尤其要用同一入口复现一次。

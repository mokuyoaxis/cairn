---
name: pin-tool-versions-in-scripts
summary: 脚本里要固定工具版本，浮动 latest 会让昨天能跑的今天挂
kind: method
updated: 2026-10-19
scope: toolchain
source: cairn 示例
---

**做法**：镜像、CLI、依赖都写明确版本；升级用独立提交，不要跟业务改动混在一起。

**为什么**：浮动版本随时可能改变行为或输出格式，故障出现在与你无关的时间点。

**何时用**：CI 配置、一次性脚本、容器基础镜像。

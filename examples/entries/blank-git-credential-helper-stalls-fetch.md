---
name: blank-git-credential-helper-stalls-fetch
summary: 空的 credential.helper 不是禁用，而是让 git 停在原地等输入
kind: lesson
updated: 2026-10-19
scope: git
source: cairn 示例
---

**做法**：`git config credential.helper ""` 不是关闭凭据助手，而是留下一个空条目。
用 `git config --unset-all credential.helper` 删掉它。

**为什么**：非交互环境里表现为 `git fetch` 永久挂起，没有错误信息。

**何时用**：CI 或脚本里出现"网络没问题的 fetch 卡住"时，先 `git config --get-all credential.helper` 看一眼。

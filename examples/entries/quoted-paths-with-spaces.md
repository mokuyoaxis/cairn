---
name: quoted-paths-with-spaces
summary: 路径含空格不加引号会被拆成多个参数，且失败方式因平台而异
kind: lesson
updated: 2026-10-19
scope: windows, shell
source: cairn 示例
---

**做法**：所有路径参数一律加引号；传给子进程时用参数数组而不是拼接字符串。

**为什么**：有的平台报错，有的平台静默截断到第一个空格，写出"看起来成功"的错误文件。

**何时用**：脚本里出现用户目录、程序目录、文件名时；Windows 上尤其常见。

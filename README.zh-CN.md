# Cairn

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/mokuyoaxis/cairn/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mokuyoaxis/cairn/actions/workflows/ci.yml)

**面向 AI Coding Agent 的本地优先经验检索层。**

Cairn 是一个本地优先、确定性的 **Experience Retrieval Layer（经验检索层）**。每次提问时，它在本地 Markdown 经验库中检索，把少量高信号的「经验卡片」放进上下文；它不要求 Agent 记得去查，也不把整篇文档塞进 prompt。

零第三方依赖、默认零网络、单文件核心。Python 3.9+。

[English](README.md) | **简体中文**

> “走过的人添一颗石子，后来的人少迷一次路。”

---

## 一览

| 项目 | 内容 |
|---|---|
| 状态 | `v0.1.0` Internal Alpha |
| 核心 | `cairn.py`，1200 行，零第三方依赖 |
| 存储 | 本地 Markdown 条目；缓存可重建 |
| 检索 | 中文 2-gram + 英文词元，BM25，三道门 |
| 测试 | 58 项单元测试 |
| 评测 | 12 条示例库上的 24 条正例 + 25 条负例 |
| 延迟 | 冷启动 hook p95 约 70ms（单机样本） |
| 许可证 | MIT © 2026 Messia |

---

## 为什么需要 Cairn

同一个坑被踩第二次，通常不是因为没记录，而是因为**记录没有在需要它的那一刻出现**。

Cairn 针对三种失败：

1. **经验遗失**：在一个项目/会话里解决的问题，换一个上下文就归零。
2. **经验沉睡**：经验存在于文件里，但 Agent 真正需要时没有检索。
3. **经验误用**：检索到了，但过时、作用域不对、不可信，或与当前任务冲突。

目标不是让 Agent 记住更多，而是：**在合适的时刻，提供少量相关、来源可追溯、适用条件明确、可以撤回的经验；不适用时保持沉默。**

---

## Cairn 是什么，不是什么

Cairn 是：

- 一个面向可复用经验的**检索层**；
- 默认本地优先、确定性；
- 可审计：每次注入都有分数、门控决策和路径；
- 运行时只读：不执行条目、不改写经验库；
- 刻意保持小：Markdown 存储、单文件核心、无默认外部模型依赖。

Cairn 不是：

- 通用 Memory、用户画像或会话存储；
- 自动 Skill 生成器、发布器或执行器；
- Markdown 知识管理平台或文件树 UI；
- Agent 安全边界，也不是 Prompt Injection 的解决方案；
- 向量数据库或默认 embedding 管线。

这些边界是刻意的：只有足够窄，才足够可信。

---

## 快速开始

```bash
git clone https://github.com/mokuyoaxis/cairn.git
cd cairn

# 演示只写 examples/cache 和 examples/log，两者已 gitignore
CAIRN_HOME=./examples python3 cairn.py recall "docker compose config 密钥"
```

输出示例：

```text
【cairn】可能有用的既往经验（按相关度排序）：
- config-dump-reveals-secret-values：docker compose config 会把 env_file 里的密钥展开成明文 → entries/...
需要全文用 `cairn show <name>`；都不相关就忽略本提示。
```

需要全文时：

```bash
CAIRN_HOME=./examples python3 cairn.py show config-dump-reveals-secret-values
```

Cairn 返回卡片，不返回整篇文档。没有条目过门时，它保持沉默。

---

## 工作原理

1. **切词**：中文按 2-gram；英文和标识符按词。
2. **打分**：BM25，字段加权 `summary ×3 > name ×2 > body ×1`；分母只算库内真实存在的 query 词。
3. **过门**：候选必须通过三道独立门：归一化分数、query 词覆盖率、相对第二名的领先幅度。
4. **去抖**：同一会话同一张卡片最多注入一次。
5. **渲染**：最多三张卡片，名字 + summary + 路径；全文按需显式读取。

运行时只读；检索、统计与校验不发起网络请求。

---

## 接进 Agent

Claude Code（`~/.claude/settings.json`）：

```json
{"hooks":{"UserPromptSubmit":[{"hooks":[{
  "type":"command",
  "command":"python3 /path/to/cairn/cairn.py hook --format claude",
  "timeout":10}]}]}}
```

Codex CLI 使用 `--format codex`；`--format text` 用于本地测试；`--format json` 输出 `{"cairn": "..."}`。完整 Hook 契约见 [docs/usage.md](docs/usage.md)。

---

## 隐私与安全

- **本地优先**：检索、存储、评测在本地完成；Hook 与检索链路不联网。
- **日志不落原始 prompt**：只记录 UTC 时间、会话指纹、查询/笔记指纹与长度、注入条目 ID、门控原因。调试预览需显式设置 `CAIRN_LOG_QUERY_PREVIEW=1`，且仍会脱敏。
- **audit 覆盖受管数据**：`cairn audit` 扫描 entries、日志、会话文件与派生缓存；输出只显示脱敏样本。
- **sanitize 有边界**：拒绝写入源库，默认不覆盖已有目标，使用原子写入。
- **经验是证据，不是指令权威**：条目不能覆盖系统/开发者指令；权限、沙箱和危险操作审批仍由宿主 Agent 负责。
- **不宣称解决 Prompt Injection**：Cairn 减少内容面，但不替代宿主安全边界。

威胁模型与发布检查见 [docs/security.md](docs/security.md)。

---

## 当前状态

| 指标 | 数值 |
|---|---|
| 单元测试 | 58 项通过 |
| 示例库 | 12 条 |
| 评测集 | 24 条正例 + 25 条负例 |
| 召回@1 / @3 | 91.7% / 100% |
| 注入@1 / @3 | 75% / 75% |
| 误触发 | 4.0% |
| 平均注入（每 query / 每次注入） | 145 / 194 字符 |
| Hook p95 | 约 70ms（单机样本） |

这些数字是**回归基线**，不是 benchmark。评测集很小，阈值是手工定的；Recall@3 100% 不代表经验真的被注入。

已知限制：

- 阈值手工调；`cairn calibrate` 未实现；
- 同义词无感（`密码` 不会自动检索 `密钥`，需要别名表）；
- 评测集太小，不足以证明泛化；
- 2-gram 对很短 query 较粗；
- 没有捕获闭环；`add` 是手动的；
- `import` 会把文件名归一为 kebab-case 并自动跑 `lint`，但只解析顶层标量 frontmatter，不解析嵌套 YAML；
- 显式的 trust/quarantine 契约是近期交付项，尚未 ship；
- 技术文档目前为简体中文。

平均注入长度同时按「每 query（未注入计 0）」与「每次实际注入」报告。它是诊断指标，不是成本承诺；详见 [docs/evaluation.md](docs/evaluation.md)。

---

## 路线图

近期重点是**契约、信任与度量**，不是功能数量：

- Phase 0 正确性修复与首个 Git 基线已完成；
- 定义 **Experience Contract v0**（source、verification、lifecycle、applicability、admission）；
- 统一 **Recall / Explain** 的候选、门控与拒绝理由；
- 建立 **Trust & Applicability Evaluation**，覆盖恶意、过期、scope 不匹配、冲突与 quarantine 条目；
- 在声称用户收益前，先做真实任务评测。

之后：

- `cairn calibrate`、80+ 评测集、别名表；
- 显式提议 + 人工审核的捕获流程；
- 可选的 Git 共享。

暂缓：

- 完整 Web 控制台；未来如果做，Ask 页面优先于 Library 管理界面；
- Decision-time Recall 作为长期方向，暂不新增 Hook 或平台矩阵。

---

## 文档

技术文档目前为简体中文：

- [docs/README.md](docs/README.md) — 文档索引
- [docs/usage.md](docs/usage.md) — 安装、数据目录、命令、Hook 接入、排障
- [docs/architecture.md](docs/architecture.md) — 检索、门控、缓存、渲染与设计取舍
- [docs/evaluation.md](docs/evaluation.md) — 指标、当前结果、评测方法与局限
- [docs/security.md](docs/security.md) — 信任边界、隐私、audit/sanitize、发布检查
- [docs/development.md](docs/development.md) — 目录、测试、约束、贡献流程

---

## 许可证

MIT License，Copyright (c) 2026 Messia。见 [LICENSE](LICENSE)。

Cairn 是独立项目，不依赖外部记忆服务、向量数据库或模型 Provider。

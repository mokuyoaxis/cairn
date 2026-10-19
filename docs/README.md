# Cairn 文档

> Cairn 是 **Local-first Experience Retrieval Layer**：在需要时提供少量、可追溯、适用、可撤回的经验；不适用时保持沉默。  
> 它不是通用 Memory、自动 Skill 生成器或 Markdown 知识管理平台。

**入口**：[English README](../README.md) · [简体中文 README](../README.zh-CN.md)  
**状态**：v0.1.0 Internal Alpha · 技术文档目前以简体中文为主。

## 文档地图

| 文档 | 内容 | 适合谁 |
|---|---|---|
| [usage.md](usage.md) | 安装、数据目录、条目格式、全部命令、Hook 接入、排障 | 使用者 |
| [architecture.md](architecture.md) | 无索引、2-gram/BM25、三道门、缓存、卡片渲染、设计取舍 | 想改检索的人 |
| [evaluation.md](evaluation.md) | 指标定义、24+25 评测集、当前结果、已知口径问题、评测路线 | 想验证效果的人 |
| [security.md](security.md) | 信任边界、日志隐私、audit/sanitize、注入风险、发布检查 | 维护者/安全审查 |
| [development.md](development.md) | 目录、测试、基线复现、CI、编码约束、贡献流程 | 贡献者 |

## 阅读顺序

1. 第一次使用：先看根目录 [README](../README.md)，跑通 30 秒示例，再看 [usage.md](usage.md)。
2. 想理解“为什么能命中”：看 [architecture.md](architecture.md)。
3. 想判断“到底有没有用”：看 [evaluation.md](evaluation.md)，不要只看单个指标。
4. 准备公开/共享：先看 [security.md](security.md) 的发布检查清单。
5. 准备改代码：看 [development.md](development.md)，先跑基线和测试。

## 文档原则

- 只写可复现的行为与命令；未验证的判断明确标注。
- 评测数字用于回归，不用于排名；样本量不足时直接说明。
- 安全文档不承诺“绝对安全”，只描述已实现的边界与仍需人工判断的部分。
- 维护者本地材料默认不随仓库发布，公开文档不依赖它们。

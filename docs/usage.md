# 使用指南

本文是 Cairn 的操作手册，覆盖安装、数据目录、条目格式、全部命令、Hook 接入与排障。

> Cairn 是 Local-first Experience Retrieval Layer。它只负责“在需要时提供经验卡片”，不负责通用记忆、自动 Skill 或 Markdown 知识管理。

## 0. 摘要

Cairn 的日常使用只有三条主线：

| 目标 | 入口 |
|---|---|
| 看效果 | `CAIRN_HOME=./examples python3 cairn.py recall "..."` |
| 写入经验 | `python3 cairn.py add ...`，然后 `lint` |
| 接进 Agent | `python3 cairn.py hook --format claude`（或 `codex`） |

本文不覆盖：控制台、自动经验抽取、向量检索、团队服务端。

## 1. 运行要求

- Python 3.9+
- 零第三方依赖
- 默认不联网

仓库里有两个入口，行为相同：

```bash
python3 cairn.py --version
./cairn --version
```

## 2. 数据目录

默认数据目录是 `~/.cairn/`，可用 `CAIRN_HOME` 覆盖：

```bash
export CAIRN_HOME="$HOME/.cairn"
```

目录结构：

```text
$CAIRN_HOME/
├── entries/           # Markdown 经验条目；唯一权威数据源
├── log/               # inject / miss / show / feedback 日志、会话去抖文件
└── cache/
    └── index.pkl      # 可随时删除，下次检索自动重建
```

示例库可以这样直接跑（运行时数据写入 `examples/cache`、`examples/log`，两者已 gitignore）：

```bash
CAIRN_HOME=./examples python3 cairn.py ls
CAIRN_HOME=./examples python3 cairn.py recall "compose 密钥"
```

相关环境变量：

| 变量 | 作用 |
|---|---|
| `CAIRN_HOME` | 覆盖数据目录；默认 `~/.cairn` |
| `CAIRN_SESSION` | Hook 没有收到 `session_id` 时使用的会话标识 |
| `CAIRN_LOG_QUERY_PREVIEW` | 设为 `1` 时，日志额外保存**脱敏后**的查询/笔记预览；默认关闭 |

## 3. 条目格式

一条经验一个 Markdown 文件，四个基础必填字段 + Experience Contract v0 字段：

```markdown
---
name: config-dump-reveals-secret-values   # 必填，kebab-case，必须等于文件名
summary: docker compose config 会把 env_file 里的密钥展开成明文   # 必填，检索全靠它
kind: lesson                              # 必填：lesson（教训）| method（方法）
updated: 2026-10-19                       # 必填，最近一次确认
scope: docker, security                   # 可选，适用范围
source: 某次线上排查                        # 可选；trust=verified 时必填
status: active                            # 可选：active | deprecated | archived，默认 active
trust: verified                           # 可选：verified | unverified | quarantined，默认 unverified
verified_at: 2026-10-19                   # trust=verified 时必填，YYYY-MM-DD
evidence: docs/incidents/2026-10-19.md    # 可选，验证依据
---

**做法**：直接说怎么做。
**为什么**：不这样做会怎样。
**何时用**：什么场景下想起来。
```

约定：

- `name` 必须匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$`，且文件名必须是 `<name>.md`；
- `summary` 是检索面，写成“别人会怎么描述这个问题”，建议 ≤200 字符；
- 一事实一文件，正文建议 ≤80 行；
- 只对某个平台/版本成立的结论，在 `summary` 里点名（例：`【仅 Windows】`）；
- 双链使用 `[[条目名]]`，`lint` 会检查死链。

### 3.1 Experience Contract v0 准入规则

自动注入必须同时满足：

1. `status: active`；
2. `trust: verified`；
3. `source` 非空；
4. `verified_at` 是 `YYYY-MM-DD`。

不满足条件的条目仍可用 `recall --raw` 或 `show` 查看，但不会进入 Hook 上下文。
`trust: verified` 是**条目声明的验证状态**，不是加密证明，也不等于跨项目适用；
人工写入/批准不等于技术验证。导入的条目默认 `trust: quarantined`，需要人工复核后
显式改为 `verified`。

旧库/旧条目如果没有这些字段，按 `active + unverified` 处理：升级后会**停止自动注入**，
需要逐条复核并补 `source`、`trust: verified`、`verified_at`。

## 4. 命令

### 4.1 `add`

```bash
python3 cairn.py add \
  --name verify-after-config-change \
  --summary "修改配置后必须从实际消费路径验证生效" \
  --kind method \
  --scope deployment \
  "**做法**：保留可恢复状态，并从实际消费端验证配置已生效。"
```

- `--name` 省略时，用 summary 的 SHA-1 生成 `entry-xxxxxxxx`；
- `--summary` 必填；
- `--kind` 只能是 `lesson` 或 `method`，默认 `lesson`；
- `--status` 默认 `active`；`--trust` 默认 `unverified`；`--verified-at` 接受 `YYYY-MM-DD`；
- `--trust verified` 必须同时提供 `--source` 与有效 `--verified-at`，否则返回 2；
- 正文可以用位置参数、`-` 或管道传入；
- 目标已存在时拒绝覆盖，`--force` 显式覆盖；
- 写入后立刻自检；有 ERROR 时返回非零；未验证条目会打印“不会自动注入”警告。

### 4.2 `recall`

```bash
python3 cairn.py recall "docker exec 里写 heredoc 完全没反应"
python3 cairn.py recall "..." --raw          # 看原始分数与命中词数
python3 cairn.py recall "..." --limit 3      # 最多几张卡片
```

- 默认只返回通过 Experience Contract 与三道门的可注入条目；
- 没有条目过门时输出 `[无相关条目]`，退出码 1；
- `--raw` 绕过契约与门控，显示所有候选、分数及 `[status/trust]`，用于调试和复核；
- `--min-score` / `--min-cover` / `--min-margin` 可临时调整三道门。

### 4.3 `show` / `ls`

```bash
python3 cairn.py show config-dump-reveals-secret-values
python3 cairn.py ls
python3 cairn.py ls --md        # 输出自动生成的索引文本
```

`show` 打印全文并记一次 `show` 日志；`ls --md` 生成的索引仅供阅读/导出，不是运行时权威索引。

### 4.4 `lint`

```bash
python3 cairn.py lint
```

检查：必填字段、kebab-case、name↔文件名、kind、日期、`status`/`trust` 枚举、
`verified_at` 格式、`trust=verified` 的 source/日期要求、双链死链、重名、NUL。
发现问题返回 1；可注入性不足只产生 `[warn]`，不阻断。

空库或错误的 `CAIRN_HOME` 会输出 `[FAIL] 0 条` 并返回 1，不再给出虚假 PASS；排查时同时确认 `ls` 与 `CAIRN_HOME`。

### 4.5 `import` / `prune-links`

```bash
python3 cairn.py import ./old-notes --dry-run   # 只看计划，不写库
python3 cairn.py import ./old-notes
python3 cairn.py import ./old-notes --exclude "private|secret"
python3 cairn.py import ./old-notes --force
python3 cairn.py prune-links
```

`import` 递归读取 `*.md`，跳过 README/INDEX/CHANGELOG，并做字段归一：

- `description` → `summary`
- `type: pitfall` → `kind: lesson`
- `type: tool/workflow` → `kind: method`
- `date/verified` → `updated`
- `topic` → `scope`

文件名会自动归一为 kebab-case（如 `Bad Name.md` → `bad-name.md`）；纯非 ASCII 文件名会退化为 `entry-<hash>`，避免空 slug。非法日期会被跳过并列入 `[SKIP]`。所有导入条目统一写为 `status: active`、`trust: quarantined`，不复制来源里的 `trust/verified_at`；复核后再手工改为 `verified`。写入后自动跑 `lint`，返回码反映校验结果。`prune-links` 用于删除指向不存在条目的 `[[双链]]`。

### 4.6 `hook`

```bash
python3 cairn.py hook --format claude
python3 cairn.py hook --format codex
python3 cairn.py hook --format text
python3 cairn.py hook --format json
```

- stdin：JSON；会从 `prompt` / `user_prompt` / `userPrompt` / `message` / `content` / `text` 等字段提取；
- stdout：对应平台的 JSON；
- 需要摘要时从 stdin 的 `session_id` 或 `CAIRN_SESSION` 取会话标识；
- 只有 `active + verified + source + verified_at` 的条目可能被注入；契约不满足时保持沉默；
- 任何异常都静默返回 0，不阻塞宿主会话；无命中/已去抖时不输出正文；
- Hook 日志默认不保存原始 prompt，只记指纹、长度、命中条目和门控原因（含 `ineligible`）。

### 4.7 `eval`

```bash
CAIRN_HOME=./examples python3 cairn.py eval
CAIRN_HOME=./examples python3 cairn.py eval --queries eval/queries.jsonl --negatives eval/negatives.jsonl
```

退出码：0 过门槛；1 未过；2 参数/评测集错误。默认门槛：注入@3 ≥70%，误触发 ≤10%。

`--min-score` / `--min-cover` / `--min-margin` 会同时作用于正例与负例门控。
注入指标只统计通过 Experience Contract 的条目；召回指标仍基于全部候选，因此
两者差距可能同时来自门控与契约。平均注入会分别报告「每 query（未注入计 0）」与
「每次实际注入」，口径见 [evaluation.md](evaluation.md)。

### 4.8 `audit` / `sanitize`

```bash
python3 cairn.py audit
python3 cairn.py sanitize --out /tmp/cairn-clean
python3 cairn.py sanitize --out /tmp/cairn-clean --force
```

`audit`：

- 扫描 `entries/*.md`、`log/*.jsonl`、`log/session-*.json`、`cache/index.pkl`；
- 检查私钥、云凭据、API key、Bearer、邮箱、含用户名的绝对路径、内网 IP、业务数字；
- `critical`/`high` 返回 1；`medium` 返回 0 但提示；
- 输出只显示脱敏样本；文件读不出时返回非零。

`sanitize`：

- 生成 `DIR/entries/`，不修改源库；
- 拒绝 `DIR` 等于或位于源 `entries/` 内（含符号链接解析）；
- 默认拒绝覆盖已有目标，`--force` 显式覆盖；
- 用临时文件 + 原子替换写入；
- 替换路径/邮箱/业务数字，以及私钥、云凭据、API key、Bearer。

`sanitize` 是**尽力而为的文本替换**，不能替代人工复核。公开前请对输出再跑一次 `CAIRN_HOME=DIR cairn audit`。

### 4.9 `stats` / `feedback` / `nudge`

```bash
python3 cairn.py stats
python3 cairn.py stats --show-queries
python3 cairn.py feedback config-dump-reveals-secret-values --helpful --note "这次很有用"
python3 cairn.py nudge --format claude
```

- `stats` 默认只显示 miss 查询指纹；`--show-queries` 才显示脱敏预览；旧日志里的原始 query 不会默认打印；
- `feedback` 只记录信号、条目名、note 指纹/长度；note 原文不落日志；
- `nudge` 用于 Stop Hook，提醒“若有可复用教训，考虑 add”，不自动写入。

## 5. 接进 Claude Code

`~/.claude/settings.json`：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/cairn/cairn.py hook --format claude",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

自测：

```bash
python3 /path/to/cairn/cairn.py hook --format claude <<<'{"prompt":"compose 密钥","session_id":"demo"}'
```

## 6. 接进 Codex CLI

使用 `--format codex`，输出 `{"systemMessage": "..."}`：

```bash
python3 /path/to/cairn/cairn.py hook --format codex <<<'{"prompt":"...","session_id":"..."}'
```

`--format text` 输出纯文本，适合本地调试；`--format json` 输出 `{"cairn": "..."}`。

## 7. 日志、去抖与隐私

- 日志默认只记：UTC 时间、事件类型、会话指纹、命中条目、门控原因、查询/笔记指纹与长度；
- 不记原始 prompt、原始 `session_id`、原始 feedback note；
- `CAIRN_LOG_QUERY_PREVIEW=1` 时额外记脱敏预览（最多 120 字符）；
- 同一会话同一张卡片只注入一次；会话文件默认 12 小时后失效；
- `log/` 与 `cache/` 都可以删除；`entries/` 是唯一需要备份的目录。

## 8. 排障

**`[无相关条目]` 是正常的。**

说明没有条目同时通过契约与门控；可用 `--raw` 看候选、分数与 `[status/trust]`，或检查 `summary` 是否覆盖了用户会用的说法。不要为了“有输出”盲目降低阈值或伪造 `verified`。

**Hook 没有输出。**

依次检查：`CAIRN_HOME` 是否指向正确的库；库是否为空；是否无命中；条目是否满足 `active + verified + source + verified_at`；是否同一会话已去抖。Hook 无输出时退出码仍是 0，这是非阻塞设计。

**有条目命中了，但仍不注入。**

先跑 `lint` 看 `[warn] 不会自动注入`，再跑 `recall "..." --raw` 看 `[status/trust]`。补 `source`、`verified_at`，并把 `trust` 改为 `verified`；导入条目默认是 `quarantined`。不要直接把 `trust` 改成 `verified` 而不做复核。

**`lint`/`audit` 显示 `0 条` 并 FAIL。**

说明 `CAIRN_HOME` 指向了空目录或错误路径；先 `ls` 确认条目数与 `CAIRN_HOME`，再跑 `eval`。

**`sanitize` 报“输出目录不能等于或位于 entries/ 内”。**

换一个库外的空目录；它不会原地修改源库。

**`sanitize` 报“目标已存在”。**  
默认不覆盖；确认目标内容后可加 `--force`。

**旧日志里可能有历史原始 prompt。**  
新版本不再写入，但旧文件不会自动清理。先跑 `audit` 确认，再人工轮转/删除 `log/*.jsonl`；不要直接分享 `log/`。

## 9. 相关文档

- [architecture.md](architecture.md) — 检索、门控、缓存、渲染
- [evaluation.md](evaluation.md) — 指标与评测方法
- [security.md](security.md) — 信任边界与发布检查
- [development.md](development.md) — 测试与贡献

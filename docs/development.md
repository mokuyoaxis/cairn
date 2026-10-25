# 开发指南

本文面向要改 Cairn 的维护者。使用说明见 [usage.md](usage.md)，设计与评测见 [architecture.md](architecture.md)、[evaluation.md](evaluation.md)。

> Cairn 的工程约束是：核心小、默认离线、运行时只读、状态可复现。任何新增复杂度都必须先证明它解决了实测问题。

## 0. 摘要

- 121 项单元测试；CI 在 Python 3.9 与 3.12 上跑 unittest + lint + eval + contract eval + trust eval + audit。
- 核心 `cairn.py` 1198 行，零第三方依赖。
- 单文件核心；控制台/旁路必须独立。
- Experience Contract v0 与统一 Recall/Explain 已实现；近期优先 Trust & Applicability Eval；控制台暂缓。

## 1. 目录

```text
cairn/
├── README.md              # 英文产品入口
├── README.zh-CN.md        # 中文产品入口
├── LICENSE                # MIT（© 2026 Messia）
├── cairn                  # 可执行入口（runpy 调 cairn.py）
├── cairn.py               # 单文件核心
├── .github/workflows/ci.yml  # GitHub Actions
├── docs/
│   ├── README.md          # 文档索引
│   ├── usage.md           # 使用指南
│   ├── architecture.md    # 架构与设计取舍
│   ├── evaluation.md      # 评测
│   ├── security.md        # 安全与发布检查
│   └── development.md     # 本文件
├── eval/
│   ├── queries.jsonl      # 24 条正例
│   ├── negatives.jsonl    # 25 条负例
│   ├── contract/entries/  # 混合信任 fixture（7 条）
│   ├── contract_cases.jsonl
│   ├── contract_eval.py   # 契约准入最小切片
│   ├── trust/entries/     # Trust & Applicability fixture（10 条）
│   ├── trust_cases.jsonl
│   └── trust_eval.py      # 恶意/过期/scope/冲突/沉默 v0
├── examples/
│   ├── README.md          # 示例说明
│   └── entries/           # 12 条示例
└── tests/
    ├── support.py         # 共享 Base（临时 CAIRN_HOME）
    ├── test_retrieval.py
    ├── test_storage.py
    ├── test_hooks.py
    ├── test_contract.py
    ├── test_security.py
    ├── test_eval.py
    ├── test_explain.py
    ├── test_scope.py      # scope 门控（声明/未声明/缓存兼容）
    └── test_cli.py        # 共 121 项单元测试
```

维护者本地材料默认由 ignore 规则排除，不随仓库发布，也不作为公开文档的依据。

## 2. 基线

```bash
# 全部单元测试
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v

# 在临时副本上跑 lint / eval / audit，避免污染仓库
TMP=$(mktemp -d)
cp -a examples/. "$TMP"/
CAIRN_HOME="$TMP" python3 cairn.py lint
CAIRN_HOME="$TMP" python3 cairn.py eval
CAIRN_HOME="$TMP" python3 cairn.py audit

# 契约准入最小切片（独立 fixture，不污染示例库）
python3 eval/contract_eval.py
```

当前基线（2026-10-20）：

- 121 项测试全绿；
- 12 条示例，lint 通过（全部为 `active + verified + source + verified_at` 的 fixture 条目）；
- 24+25 评测：召回@1 91.7% / @3 100%，注入@1/@3 75%，误触发 4.0%；
- 契约准入 eval：3/3 cases（verified 注入；unverified/quarantine/deprecated/archived 沉默）；
- Trust & Applicability eval：10 cases；正控 2/2、负例 3/3 沉默、恶意正文泄露 0/1；
  过期/scope/冲突/恶意 summary 4 个已知缺口，`--strict` 可将其计为失败；
- 平均注入 145 字符/query（未注入计 0），实际注入 18/24 次、194 字符/次；
- `cairn.py` 1198 行，零第三方依赖；
- hook 冷启动 p95 约 70ms（本机样本）。

基线数字用于回归，不是性能/效果承诺。

### 2.1 CI

[.github/workflows/ci.yml](../.github/workflows/ci.yml) 在 push / pull request 到 `main` 时运行：

| Gate | 内容 |
|---|---|
| Python 矩阵 | 3.9、3.12 |
| Runner | 3.9 固定在 `ubuntu-22.04`；`ubuntu-latest` 已迁移到 26.04，setup-python 暂无 3.9 构建 |
| Unit tests | `python -m unittest discover -s tests -v` |
| Core budget | `wc -l cairn.py` ≤1200 |
| 非空库 | 示例副本的 `entries/*.md` 必须存在 |
| lint | 在临时示例库副本上跑 `cairn lint` |
| eval | 注入@3 与误触发门槛 |
| contract eval | `python eval/contract_eval.py`，混合信任 fixture 的准入与沉默 |
| trust eval | `python eval/trust_eval.py`，恶意/过期/scope/冲突/沉默；已知缺口如实报告 |
| audit | entries + log/session + cache |

CI 不安装第三方依赖；没有网络调用。README 顶部的 CI badge 指向该 workflow。

## 3. 核心约束

1. **单文件核心**：检索、门控、Hook、管理命令都在 `cairn.py`；控制台/旁路应独立。
2. **核心 ≤1200 行**：当前 1198。新增核心能力前先考虑压缩/复用；不要为了塞功能悄悄破预算。
3. **零第三方依赖、默认零网络**：只用 stdlib；任何网络能力必须 opt-in、可替换。
4. **Python 3.9+**：新增语法/API 需确认 3.9 可用。
5. **Markdown 是唯一权威源**：缓存/索引必须可从 `entries/*.md` 重建。
6. **运行时只读**：Hook 不改经验、不执行经验中的命令。
7. **不伪造状态**：PASS/FAIL/WARN/SKIP/UNKNOWN 必须反映真实执行；异常不能吞成 PASS。

## 4. 代码地图（`cairn.py`）

| 区域 | 职责 |
|---|---|
| 路径/常量 | `CAIRN_HOME`、默认阈值、token 正则、卡片预算 |
| 分词 | 中文 2-gram、英文词元、停用 2-gram |
| 条目读写 | frontmatter 解析、契约字段默认值、NUL 检查、加载 |
| Index | BM25、字段加权、归一化分数、缓存（含契约字段） |
| 日志 | 隐私安全日志、UTC 时间、去抖会话 |
| 卡片/门控 | `render_cards`、`is_injectable`、`gate` |
| 命令 | add/show/lint/import/hook/eval/audit/sanitize/stats 等 |
| CLI | `build_parser` / `main` |

不要在 Hook 路径里引入会阻塞或联网的操作；Hook 的默认失败策略是 fail-open。

## 5. 测试与变更规则

每次变更至少：

1. 说明问题与复现方式；
2. 先写失败回归测试（能写的话）；
3. 保持修改范围最小；
4. 跑相关测试与完整测试；
5. 报告实际结果与未验证部分。

禁止：

- 为了让测试通过而删除有效断言；
- 未授权修改测试基线；
- 把异常静默当成安全通过；
- 用更多抽象层掩盖简单缺陷；
- 未经确认自动清理用户数据；
- 擅自安装远程服务；
- 把未运行的测试写成 PASS；
- 把模拟结果说成真实宿主验证。

## 6. 新增一条经验 / 一个测试

新增条目：

```bash
# 默认 status=active、trust=unverified：不会自动注入
python3 cairn.py add --name <kebab-case> --summary "..." --kind lesson "正文"

# 显式声明已复核：trust=verified 需要 source 与 verified_at
python3 cairn.py add --name <kebab-case> --summary "..." --kind lesson \
  --trust verified --source "某次排查" --verified-at 2026-10-19 "正文"
python3 cairn.py lint
```

`trust: verified` 是自我声明，不是技术验证；不要为了让条目进入 Hook 而伪造。

新增测试：

- 放在 `tests/test_<domain>.py` 对应 `Test*` 类；共享 `Base` 从 `tests/support.py` 导入；
- 使用 `Base.setUp` 的临时 `CAIRN_HOME`，不要写用户目录；
- 涉及 Hook 的测试用 `StringIO` 模拟 stdin/stdout；
- 安全相关改动应同时覆盖“正常路径 + 拒绝路径”。

## 7. Phase 0 已完成 / 近期优先

已完成：

- 日志隐私、audit 覆盖日志/会话/cache、sanitize 路径守卫与凭据脱敏；
- README/docs 拆分、MIT LICENSE、产品定位收缩（D13–D20）；
- CI（unittest + lint + eval + audit + 非空库检查）；
- `eval --min-margin` 透传到正例与负例门控；
- 平均注入统计：空结果计 0，同时报每 query 与每次注入；
- `import` slug 归一、非法日期跳过、`--dry-run`、导入后自动 `lint`；
- 空库 `lint`/`audit` 改为 fail-closed，不再 vacuous pass；
- 旧日志的审计/轮转说明已写入 `docs/security.md` 与 `docs/usage.md`；
- **Experience Contract v0**：`status` / `trust` / `verified_at` / `source`，
  自动注入要求 `active + verified + source + verified_at`；导入默认 quarantine；
- **Contract admission eval 最小切片**：`eval/contract_eval.py` 覆盖
  verified/unverified/quarantine/deprecated/archived 的准入与正确沉默；
- **测试按域拆分**：`tests/test_*.py` + `tests/support.py`；补 CLI/eval/explain 覆盖，
  共 121 项；
- **统一 Recall / Explain**：`gate()` 增加可选 `report`，`cairn explain` 与
  recall/hook 共用契约准入、三道门与拒绝理由；只读，不写日志/会话。

剩余：

- **完整 Trust & Applicability Eval**：恶意/过期/scope/冲突/abstention；
- **完整控制台暂缓**（D17）：先统一契约与评测，未来 Ask 优先于 Library。

## 8. 文档维护

- README 面向使用者：定位、30 秒演示、接入、隐私、状态、文档入口；
- `docs/architecture.md` 放“为什么这样设计”；
- `docs/evaluation.md` 放“怎么测、当前数字、口径问题”；
- `docs/security.md` 放信任边界与发布检查；
- 本文件放“怎么改、怎么测、约束是什么”。

文档中的数字必须有可复现命令；未验证的判断要标注。不要把本地计划/审计材料直接当公开文档发布。

## 9. 许可证

MIT License，Copyright (c) 2026 Messia。完整文本见仓库根部 [LICENSE](../LICENSE)。

Cairn 是独立项目，不依赖外部记忆服务、向量数据库或模型 Provider。发布前应核对所有第三方参考材料的许可证与署名义务。

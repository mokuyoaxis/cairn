# Taxonomy v2 试点材料（研究用，非生产）

> 这些文件**不参与** `cairn` 的运行时：核心不认识 `role`/`state`/`symptoms`/`signs`。
> 它们只服务于 `eval/schema_check.py` 与 `eval/taxonomy_ab.py` 两个研究工具。

## 目录

| 路径 | 内容 |
|---|---|
| `entries/` | 8 条 v2 试点条目（5 条来自现有经验改写 + 3 条显式合成的安全测试条目） |
| `candidates/` | 诊断案例的**离线侧车**（候选原因 / 检查 / 正反结果解释 / 局限 / 是否实测） |

条目还可声明 **机器可判定的适用条件**（Phase 3 为事实加了来源级别：`@verified` 才允许行动性交付）：`requires: k=v; k2=v2`（全满足才适用）与 `excludes: k=v`（命中即不适用）。
判定器见 `eval/applicability_gate.py`；事实必须由调用方声明，**不从查询文本推断**。
| `cases.jsonl` | Phase 1：23 条对照用例（派生 / 盲写 / 安全） |
| `cases_phase3.jsonl` | Phase 3：24 条**留出**用例（规则冻结后运行），字段含 `facts`（带 @verified/@asserted/@age）、`expect_actionable`、`forbid_actionable`、`expect_diagnostic`、`expect_nothing` |
| `cases_phase2.jsonl` | Phase 2：18 条**独立**用例，含 `forbid_deliver`（应召回但不得作为适用建议交付）与 `context`（声明事实） |

## 合成条目的标注

`s1-retry-now`、`s2-retry-never`、`s3-refuted-delete-wal` 的 `source` 字段均写明
`SYNTHETIC（...非真实经验）`。它们只用于制造“结论相反的候选对”和“已被反驳的知识”，
**不得**被当作真实历史记录引用，也不得进入 `examples/`。

## 用法

```bash
# 结构校验（library 区更严格）
python3 eval/schema_check.py eval/taxonomy/entries
python3 eval/schema_check.py eval/taxonomy/entries --zone research
python3 eval/schema_check.py eval/taxonomy/entries --json

# A/B/C 对照（A=现行 Contract，B=仅检索面，C=v2）
python3 eval/taxonomy_ab.py
python3 eval/taxonomy_ab.py --verbose
python3 eval/taxonomy_ab.py --json
```

## 字段约定

- 列表字段用 `;` 或 `；` 分隔（`symptoms` / `signs`）；`scope` 用逗号分隔；
- `role` ∈ `diagnostic_case` / `mechanism` / `method` / `policy`；
- `state` ∈ `tentative` / `supported` / `established` / `refuted`；
- `diagnostic_case` 必须在 `candidates/` 有同名 `.json` 侧车，且候选 ≥2；
- v1 的 `discriminator` / `differential` 会被校验器判为 error（改用侧车）；
- `workaround` 会被判为 warn（属展示用途，写正文）。

## 已知局限

- 语料与用例均为探索性样本（8 条 / 23 条），结论不可统计推广；
- `signs` 未参与检索，其权重未做实验；
- 侧车与条目的原子性（改条目忘改侧车）尚无检测；
- 适用性（`not_applicable_when`）目前只被校验、不被执行。

详细结论见仓库内部记录：`.internal/rfcs/2026-10-25-entry-taxonomy-v2.md`
与 `.internal/evidence/2026-10-25-taxonomy-ab-experiment.md`（`.internal/` 不随仓库发布）。

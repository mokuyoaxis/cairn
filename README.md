# Cairn

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/mokuyoaxis/cairn/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mokuyoaxis/cairn/actions/workflows/ci.yml)

**Local-first experience retrieval for AI coding agents.**

Cairn is a local-first, deterministic **Experience Retrieval Layer**. At prompt time, it searches a local Markdown library and places a small number of high-signal experience cards into the agent's context. It does not ask the agent to remember to search, and it does not inject entire documents.

Zero third-party dependencies. No network by default. Single-file core. Python 3.9+.

**English** | [简体中文](README.zh-CN.md)

> “A stone added by those who passed; one less wrong turn for those who follow.”

---

## At a glance

| Item | Value |
|---|---|
| Status | `v0.1.0` Internal Alpha |
| Core | `cairn.py`, 1195 lines, zero third-party dependencies |
| Storage | Local Markdown entries with Experience Contract v0 metadata; rebuildable cache |
| Retrieval | Chinese 2-gram + English tokens, BM25, contract admission, three gates |
| Tests | 95 unit tests |
| Evaluation | 80 positive + 60 negative queries on a 12-entry example library; contract admission fixture |
| Latency | ~70 ms p95 for a cold hook process (single-machine sample) |
| License | MIT © 2026 Messia |

---

## Why Cairn

The same lesson is often learned twice—not because it was never written down, but because it was not available at the moment it mattered.

Cairn addresses three failure modes:

1. **Lost experience.** A problem solved in one project or session is unavailable in the next.
2. **Dormant experience.** A lesson exists in a file, but the agent never retrieves it when needed.
3. **Misapplied experience.** A lesson is retrieved but is stale, out of scope, untrusted, or in conflict with the task.

The goal is not to make the agent remember more. It is to provide **a small number of relevant, traceable, applicable, retractable experiences at the right moment—and to stay silent otherwise.**

---

## What Cairn is—and is not

Cairn is:

- a **retrieval layer** for reusable experience;
- local-first and deterministic by default;
- auditable: every injection has a score, a gate decision, and a path;
- read-only at runtime: it never executes entries or edits the library;
- deliberately small: Markdown storage, a single core file, no external model dependency.

Cairn is **not**:

- a general memory layer, user profile, or conversation store;
- an automatic Skill generator, publisher, or executor;
- a Markdown knowledge-management platform or file-tree UI;
- an Agent security boundary or a solution to prompt injection;
- a vector database or a default embedding pipeline.

These boundaries are intentional. They keep Cairn narrow enough to be trustworthy.

---

## Quick start

```bash
git clone https://github.com/mokuyoaxis/cairn.git
cd cairn

# The demo writes only to examples/cache and examples/log, both gitignored.
CAIRN_HOME=./examples python3 cairn.py recall "docker compose config 密钥"
CAIRN_HOME=./examples python3 cairn.py explain "docker compose config 密钥"
```

Example output:

```text
【cairn】可能有用的既往经验（按相关度排序）：
- config-dump-reveals-secret-values：docker compose config 会把 env_file 里的密钥展开成明文 → entries/...
需要全文用 `cairn show <name>`；都不相关就忽略本提示。
```

Read the full entry only when needed:

```bash
CAIRN_HOME=./examples python3 cairn.py show config-dump-reveals-secret-values
```

Cairn returns cards, not documents. If nothing passes the gates, it stays silent.

---

## How it works

1. **Tokenize.** Chinese is split into 2-grams; English and identifiers are split into words.
2. **Score.** BM25 with field weights: `summary ×3 > name ×2 > body ×1`. Only query terms that exist in the library contribute to the denominator.
3. **Admit.** Only entries with `status: active`, `trust: verified`, a non-empty `source`, and a valid `verified_at` may be injected. Imported entries start as `quarantined`.
4. **Gate.** A candidate must pass three independent gates: normalized score, query-term coverage, and a margin over the second candidate.
5. **Deduplicate.** The same card is injected at most once per session.
6. **Render.** At most three cards, name + summary + path. Full text is fetched explicitly.

The runtime is read-only. Retrieval, statistics, and validation make no network calls. `cairn explain` runs the same admission and gate pipeline and prints why each candidate was injected or refused.

---

## Integrate with an agent

Claude Code (`~/.claude/settings.json`):

```json
{"hooks":{"UserPromptSubmit":[{"hooks":[{
  "type":"command",
  "command":"python3 /path/to/cairn/cairn.py hook --format claude",
  "timeout":10}]}]}}
```

Codex CLI uses `--format codex`; `--format text` is for local testing; `--format json` emits `{"cairn": "..."}`. See [docs/usage.md](docs/usage.md) for the complete hook contract.

---

## Privacy and security

- **Local-first.** Retrieval, storage, and evaluation run locally; the hook and retrieval path make no network requests.
- **No raw prompts in logs.** Logs record UTC time, a session fingerprint, query/note fingerprints and lengths, injected entry IDs, and gate reasons. Debug previews require `CAIRN_LOG_QUERY_PREVIEW=1` and are still redacted.
- **Audit covers managed data.** `cairn audit` scans entries, logs, session files, and the derived cache; samples are masked.
- **Sanitize has boundaries.** It refuses to write into the source library, refuses to overwrite existing targets by default, and uses atomic writes.
- **Experience is evidence, not authority.** Entries cannot override system or developer instructions. The host agent remains responsible for permissions, sandboxing, and approval of dangerous actions.
- **Trust is explicit.** Automatic injection requires `active + verified + source + verified_at`; imported entries are `quarantined` until reviewed. `verified` is a self-declared state, not a signature.
- **No claim of solving prompt injection.** Cairn reduces the content surface; it does not replace the host's security boundary.

See [docs/security.md](docs/security.md) for the threat model and release checklist.

---

## Current status

| Metric | Value |
|---|---|
| Unit tests | 109 passing |
| Seed library | 12 entries |
| Evaluation set | 24 positive + 25 negative queries |
| Recall@1 / @3 | 91.7% / 100% |
| Injection@1 / @3 | 75% / 75% |
| False injection rate | 4.0% |
| Contract admission eval | 3/3 cases |
| Trust & applicability eval | 10 cases; 4 known gaps |
| Avg injection (per query / per injection) | 145 / 194 chars |
| Hook p95 | ~70 ms (single-machine sample) |

These numbers are a **regression baseline**, not a benchmark. The evaluation set is small, thresholds are manual, and a 100% Recall@3 does not mean an experience was injected.

Known limitations:

- thresholds are hand-tuned; `cairn calibrate` is not implemented;
- synonyms are not understood (`password` does not retrieve `secret` without an alias);
- the evaluation set is too small to establish generalization;
- 2-gram tokenization is coarse for very short queries;
- there is no capture loop; `add` is manual;
- `import` normalizes file names to kebab-case and runs `lint`, but only parses top-level scalar frontmatter (not nested YAML);
- Experience Contract v0 is metadata, not cryptographic proof; `scope` is not yet used for admission, `verified_at` does not expire automatically, and conflict detection is not implemented;
- technical documentation is currently in Simplified Chinese.

Injection length is reported both per query (a no-hit query counts as zero) and per actual injection. It is a diagnostic, not a cost guarantee; see [docs/evaluation.md](docs/evaluation.md).

---

## Roadmap

Near-term work is about **contracts, trust, and measurement**, not feature count:

- Phase 0 correctness fixes, the first Git baseline, and **Experience Contract v0** are complete;
- **Recall / Explain** now share one admission/gate pipeline; `cairn explain` reports per-candidate refusal reasons without changing hook behavior;
- a **contract-admission eval** and **Trust & Applicability Eval v0** are in place; stale, out-of-scope, and conflicting injection is measured but not yet gated;
- add real-task evaluation before claiming user benefit.

Later:

- `cairn calibrate`, an 80+ query evaluation set, and alias tables;
- a capture workflow with explicit proposals and human review;
- optional Git-based sharing.

Deferred:

- a full web console; if built, an Ask page comes before a Library admin UI;
- Decision-time Recall, as a long-term direction without new hooks or a platform matrix.

---

## Documentation

Technical documentation is currently written in Simplified Chinese:

- [docs/README.md](docs/README.md) — documentation index
- [docs/usage.md](docs/usage.md) — installation, data layout, commands, hook integration, troubleshooting
- [docs/architecture.md](docs/architecture.md) — retrieval, gates, cache, rendering, and design trade-offs
- [docs/evaluation.md](docs/evaluation.md) — metrics, current results, methodology, limitations
- [docs/security.md](docs/security.md) — trust boundaries, privacy, audit/sanitize, release checklist
- [docs/development.md](docs/development.md) — layout, tests, constraints, contribution workflow

---

## License

MIT License, Copyright (c) 2026 Messia. See [LICENSE](LICENSE).

Cairn is an independent project. It does not require an external memory service, vector database, or model provider.

# Changelog

Notable changes to Cairn. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
version numbers follow semver, with an explicit *experimental* label while the project is pre-1.0.

## [0.1.0] — 2026-10-25 — First experimental stable baseline

First frozen baseline: behaviour, contract and test set are now fixed for real-world trial.
Published release notes (English with a Chinese summary): [`docs/release-notes/v0.1.0.md`](docs/release-notes/v0.1.0.md).
This is **experimental software** — read *Known limitations* before relying on it.

### Added

- **Prompt-time retrieval**: local Markdown library, BM25 over Chinese 2-grams and English words,
  field weights `summary ×3 > name ×2 > body ×1`. No index files, no trigger words, no model calls.
- **Experience Contract v0 admission**: only entries with `status: active`, `trust: verified`,
  a non-empty `source` and a valid `verified_at` may be injected; imported entries start `quarantined`.
- **Three independent gates**: normalized score, query-term coverage, and a margin over the runner-up.
- **Declared-scope filter**: `--scope` / `CAIRN_SCOPE` drops entries whose `scope` does not intersect
  the declared context (`out_of_scope`). With no declared scope, behaviour is unchanged.
- **`cairn explain`**: prints every candidate with score, coverage and refusal reason
  (`ineligible` / `out_of_scope` / `low_score` / `low_cover` / `low_margin` / `over_limit`). Read-only.
- **Hook entry**: `cairn hook --format claude|codex|json|text`. Fail-open: empty input, malformed JSON
  or an empty library produce no output and exit 0.
- **Library operations**: `add`, `show`, `ls`, `import` (quarantined, dry-run, name normalisation),
  `lint`, `audit` (masked samples), `sanitize` (refuses to write into the source library),
  `stats`, `feedback`, `nudge`, `prune-links`.
- **Evaluation suites**: 80 positive / 60 negative retrieval regression; contract admission (3/3 cases);
  trust & applicability (13 cases, 4 reported gaps).
- **Tests**: 224 (121 core + 103 research-fixture tests).

### Changed

- `eval` passes `--min-margin` to both the positive and negative gates, and reports injection length
  both per query and per actual injection.
- `import` normalises file names to kebab-case, skips invalid dates, supports `--dry-run`,
  and runs `lint` afterwards.
- Empty library is fail-closed for `lint`, `eval` and `audit`.
- `show` accepts only kebab-case slugs.
- CI pins Python 3.9 to `ubuntu-22.04` (newer runners no longer provide a 3.9 build).

### Research (archived — **not** shipped as a feature)

- A four-phase feasibility study of diagnostic-style experience classification
  (symptoms / signs / differential / applicability / trusted facts) is **archived with a NO-GO**
  for built-in applicability gating under the current host contract.
  Summary: [docs/research/taxonomy-feasibility-2026.md](docs/research/taxonomy-feasibility-2026.md).
- Offline prototypes and fixtures remain in `eval/` for reproducibility and audit.
  They are **not** wired into `cairn.py`, and their interfaces are **not** a stable public API.
- `cairn.py` did not change as a result of that study.

### Known limitations

- Thresholds are hand-tuned; there is no `cairn calibrate`.
- No synonym handling: `password` does not retrieve `secret` without an alias.
- The evaluation set is small (12-entry seed library, 80/60 queries); recall@3 100% does not mean a
  card was injected, and none of these numbers are a benchmark.
- Entries are evidence, not authority: a retrieved card can still be wrong for the current task.
  `verified` is a self-declared state, not a signature; `verified_at` does not expire automatically;
  conflicts between entries are not detected.
- `scope` gates only when the caller declares it — Cairn never infers scope from the prompt.
- `import` parses top-level scalar frontmatter only (no nested YAML).
- Technical documentation is currently written in Simplified Chinese.
- Not verified on Windows or macOS; CI covers Linux with Python 3.9 and 3.12.

### Security

- Default zero network: hook, retrieval, stats, lint, eval and audit make no network calls.
- Read-only runtime: the hook never adds, edits, deletes or renames entries and never executes entries.
- Logs contain UTC time, a session fingerprint, query/note fingerprints and lengths, injected IDs and
  gate reasons — never raw prompts unless `CAIRN_LOG_QUERY_PREVIEW=1` (still redacted).
- Cairn is **not** a prompt-injection defence and does not replace the host's sandbox.

[0.1.0]: https://github.com/mokuyoaxis/cairn/releases/tag/v0.1.0

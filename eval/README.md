# Evaluation fixtures

Two separate fixtures live here:

## 1. Retrieval / injection baseline

- `queries.jsonl` — 24 positive queries (`query` + `expect` slug list).
- `negatives.jsonl` — 25 unrelated queries.
- The library is `examples/entries/` (12 entries). Run with:

```bash
TMP=$(mktemp -d)
cp -a examples/. "$TMP"/
CAIRN_HOME="$TMP" python3 cairn.py lint
CAIRN_HOME="$TMP" python3 cairn.py eval
```

`cairn eval` reports Recall and Injection separately. It is a regression
baseline, not a benchmark.

## 2. Contract admission eval

- `contract/entries/` — small mixed-trust fixture:
  - `verified-active` (must inject)
  - `unverified-active`, `quarantined-active` (must abstain)
  - `deprecated-verified`, `archived-verified` (must abstain)
  - `imported-quarantine` (quarantined duplicate; must abstain)
  - `unverified-only` (only an unverified entry matches; abstain)
- `contract_cases.jsonl` — query plus `expect_injected` slugs (empty list means
  the system must stay silent).
- `contract_eval.py` — runs the real `cairn.gate()` against the fixture in a
  temporary `CAIRN_HOME`:

```bash
python3 eval/contract_eval.py
```

It fails if a non-injectable entry appears in context, or if an injectable
entry is silently dropped. The fixture is deliberately lint-warning-only:
ineligible entries are valid library content, they just must not be injected.

This is the first slice of the planned **Trust & Applicability Eval**. It does
not yet cover malicious instructions, stale `verified_at`, scope mismatch,
conflicting entries, or real agent task outcomes.

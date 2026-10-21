# Evaluation fixtures

Three separate fixtures live here:

## 1. Retrieval / injection baseline

- `queries.jsonl` — 80 positive queries (`query` + `expect` slug list).
- `negatives.jsonl` — 60 challenging negative queries (unrelated + domain-adjacent traps).
- The library is `examples/entries/` (12 entries). Run with:

```bash
TMP=$(mktemp -d)
cp -a examples/. "$TMP"/
CAIRN_HOME="$TMP" python3 cairn.py lint
CAIRN_HOME="$TMP" python3 cairn.py eval
```

`cairn eval` reports Recall and Injection separately. It is a regression
baseline, not a benchmark. Expanded from 24/25 to 80/60 in 2026-10-21.

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

## 3. Trust & Applicability Eval v0

- `trust/entries/` — 10 synthetic-token entries: fresh positive controls,
  unverified/quarantined negatives, stale `verified_at`, out-of-scope,
  a conflicting pair, a malicious body, and an instruction in `summary`.
- `trust_cases.jsonl` — case kind + expected behavior.
- `trust_eval.py` — runs the real `Index.search()` + `cairn.gate()` in a
  temporary `CAIRN_HOME`:

```bash
python3 eval/trust_eval.py           # hard constraints only
python3 eval/trust_eval.py --strict  # known gaps also fail
```

Hard constraints: positive controls must inject; contract-ineligible and
unrelated queries must stay silent; a malicious body must not appear in cards.
Stale, out-of-scope, conflicting, and malicious-summary injections are reported
as `[KNOWN]` gaps (they are not gated by the core yet), so the eval cannot be
gamed by rejecting everything: positive controls must still inject.

Synthetic tokens (`freshtoken`, `staletoken`, ...) keep queries independent of
the example library and make the fixture deterministic.

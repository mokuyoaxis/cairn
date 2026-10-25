# Evaluation fixtures

> ## Research code is not a product feature
>
> Everything in this directory that is **not** `contract_eval.py`, `trust_eval.py`,
> `queries.jsonl` or `negatives.jsonl` is **offline research**: fixtures, ablations and
> prototypes produced while evaluating a taxonomy/applicability proposal. They are kept
> for reproducibility and audit, they are **not** wired into `cairn.py`, and **their
> interfaces are not a stable public API** — they may change or disappear.
>
> The production surface is: `cairn.py` (single-file core) plus the two regression
> evals above. The core does **not** implement `role`/`state`, `symptoms` indexing,
> `requires`/`excludes`, fact contexts, applicability gating or diagnostic lanes.
> Those were studied and are **archived as NO-GO** under the current host contract.
>
> Asset classes in this directory:
>
> | class | what | files |
> |---|---|---|
>| **A. maintained offline tooling** | still useful, tested, run on demand | `schema_check.py`, `fact_context.py`, `host_facts.py` + their tests |
> | **B. historical experiment assets** | datasets, harnesses, metrics, failures | `taxonomy/`, `taxonomy_ab.py`, `taxonomy_phase2.py`, `taxonomy_phase3.py`, `phase4_chain.py`, `phase4_diagnostic.py` |
> | **C. product features not adopted** | formally rejected for now | applicability gating in core, diagnostic lane, `role`/`state` migration, `symptoms` indexing, `requires`/`excludes` in the contract |
> | **D. private material** | decisions, evidence, handoff — **not tracked** | `.internal/` (git-ignored by design) |

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
not yet cover malicious instructions, stale `verified_at`, undeclared-scope mismatch,
conflicting entries, or real agent task outcomes.

## 3. Trust & Applicability Eval v0

- `trust/entries/` — 10 synthetic-token entries: fresh positive controls,
  unverified/quarantined negatives, stale `verified_at`, out-of-scope,
  a conflicting pair, a malicious body, and an instruction in `summary`.
- `trust_cases.jsonl` — case kind + expected behavior (13 cases).
- `trust_eval.py` — runs the real `Index.search()` + `cairn.gate()` in a
  temporary `CAIRN_HOME`:

```bash
python3 eval/trust_eval.py           # hard constraints only
python3 eval/trust_eval.py --strict  # known gaps also fail
```

Hard constraints: positive controls must inject; contract-ineligible and
unrelated queries must stay silent; a malicious body must not appear in cards;
when a case declares `scope`, out-of-scope entries must abstain and in-scope
ones must still inject.
Stale, out-of-scope, conflicting, and malicious-summary injections are reported
as `[KNOWN]` gaps (they are not gated by the core yet), so the eval cannot be
gamed by rejecting everything: positive controls must still inject.

Synthetic tokens (`freshtoken`, `staletoken`, ...) keep queries independent of
the example library and make the fixture deterministic.

## 5. Taxonomy v2 research tools

Standalone, offline, and **not wired into the core**: the runtime knows nothing
about `role`/`state`/`symptoms`/`signs`.

- `schema_check.py` — validates taxonomy-v2 frontmatter: role/state consistency,
  scope width, evidence traceability, candidate completeness, refuted-vs-active
  contradictions, same-scope conflicts, and fabricated-evidence markers.
  Emits `error` / `warn` / `review`; `--zone library|research` decides whether
  “not yet confirmed” is an error or a review item.

```bash
python3 eval/schema_check.py eval/taxonomy/entries
python3 eval/schema_check.py eval/taxonomy/entries --json
```

- `taxonomy_ab.py` — A/B/C comparison over the pilot corpus:
  A = current contract, B = symptoms added to the retrieval surface only,
  C = B plus role/state injection rules. Reports coverage, correct rejection,
  uncertainty disclosure, wrong-certainty injection, differential provision,
  card chars, and per-arm denominators (a 0% with an empty denominator is not
  evidence of safety).

```bash
python3 eval/taxonomy_ab.py
python3 eval/taxonomy_ab.py --verbose
```

Pilot fixtures and field conventions: `eval/taxonomy/README.md`.

## 6. Applicability gate (Phase 2 research)

`applicability_gate.py` — three-valued applicability over **declared** facts:
the caller passes `key=value` context (like `--scope`), entries declare
`requires:` / `excludes:` predicates. No query-text inference.

| verdict | meaning | default action |
|---|---|---|
| `applicable` | all predicates declared and satisfied | existing gates decide |
| `inapplicable` | a predicate is declared and contradicted | not delivered |
| `unknown` | a predicate is undeclared | not delivered (`silent`) or delivered with `[前提未确认]` (`labeled`) |

`taxonomy_phase2.py` — ablation over `taxonomy/cases_phase2.jsonl` (18 cases):
A current contract, B +symptoms, C +state labels, D +gate(silent), D2 +gate(labeled).
It reports recall **separately** from delivery, and every safety rate with its
numerator/denominator (`未定义` when the denominator is zero).

```bash
python3 eval/taxonomy_phase2.py
python3 eval/taxonomy_phase2.py --verbose
```

## 7. Credible facts and delivery ordering (Phase 3 research)

`fact_context.py` — typed, whitelisted facts with two trust levels:

| source | who can claim it | what it unlocks |
|---|---|---|
| `verified` | host adapter / trusted tool only | `actionable` delivery |
| `asserted` | user or caller | `diagnostic_only` (a hint, never an action) |

Conflicting facts of the same trust level become `unknown` (nothing is silently
overwritten); a low-trust fact never overrides a high-trust one; stale facts are
treated as missing (`@age=<seconds>`). No expressions are evaluated and the
verdict function has no query parameter by design.

`taxonomy_phase3.py` — ordering × margin sweep over `taxonomy/cases_phase3.jsonl`:

| scheme | order |
|---|---|
| S1 | score/margin/cover first, applicability second (≈ current core) |
| S2 | applicability first, margin among survivors |
| S3 | S2 with a wider candidate pool (20) |

```bash
python3 eval/taxonomy_phase3.py
python3 eval/taxonomy_phase3.py --verbose
python3 eval/taxonomy_phase3.py --json
```

## 8. Host fact trust boundary (Phase 4 research)

`host_facts.py` — only observers registered in `OBSERVERS` can mint `verified`
facts. Anything a caller passes is forced to `asserted`; a claimed source is
discarded, `verified` values cannot be overridden, an observer that raises
yields no fact, and facts live in a per-request object (no cross-request reuse).

`phase4_chain.py` — end-to-end: real observation -> typed fact -> verdict ->
delivery, covering applicable / inapplicable / unknown / observation-failed.

`phase4_diagnostic.py` — compares three diagnostic-hint designs (silent /
shared margin / independent lane) on: hint hits, hints for contradicted
entries (must be 0), noise on unrelated queries (must be 0), one-card cap.

```bash
python3 eval/phase4_chain.py
python3 eval/phase4_diagnostic.py
```

> Phase 4 verdict: **NO-GO** for core integration — see
> `.internal/rfcs/2026-10-25-host-facts-phase4.md` (not published).

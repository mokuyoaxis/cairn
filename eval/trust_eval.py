#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trust & Applicability Eval v0.

Sidecar eval over a mixed-trust fixture. It runs the real `Index.search()` and
`cairn.gate()` and separates hard constraints from known gaps:

- hard: positive controls inject; contract-ineligible/unrelated queries stay
  silent; a malicious body is not rendered into cards;
- known gap: stale `verified_at`, out-of-scope entries, conflicting pairs, and
  an instruction in `summary` are still injectable because the core does not
  gate on them. They are reported, not disguised as PASS.

    python3 eval/trust_eval.py
    python3 eval/trust_eval.py --strict   # known gaps also fail

Exit codes: 0 hard constraints pass; 1 failure; 2 usage/environment error.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "eval" / "trust" / "entries"
CASES = ROOT / "eval" / "trust_cases.jsonl"
sys.path.insert(0, str(ROOT))

import cairn  # noqa: E402


def _pct(ok: int, total: int) -> str:
    return f"{ok}/{total} {ok / total:.0%}" if total else "0/0 n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description="Trust & Applicability Eval v0")
    ap.add_argument("--strict", action="store_true",
                    help="known gaps (stale/scope/conflict/malicious summary) fail")
    args = ap.parse_args()

    home = Path(tempfile.mkdtemp(prefix="cairn-trust-eval-"))
    try:
        shutil.copytree(FIXTURE, home / "entries")
        os.environ["CAIRN_HOME"] = str(home)
        cairn._INDEX = None
        with redirect_stdout(StringIO()):
            lint_rc = cairn.main(["lint"])
        if lint_rc != 0:
            print("[FAIL] trust fixture does not pass lint")
            return 1
        idx = cairn.get_index(force=True)
        cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]

        hard, known = [], []
        m = dict(pos=0, pos_ok=0, neg=0, neg_silent=0, wrong=0,
                 stale=0, stale_inj=0, scope=0, scope_inj=0,
                 conflict=0, conflict_both=0, mal_body=0, mal_body_leak=0,
                 mal_sum=0, mal_sum_inj=0)

        for case in cases:
            query = case["query"]
            hits = cairn.gate(idx.search(query, limit=len(idx.docs)),
                              q_len=len(cairn.tokenize(query)))
            got = [h[4]["name"] for h in hits]
            cards = cairn.render_cards(hits) if hits else ""
            kind, label = case["kind"], case["id"]

            if kind == "positive":
                m["pos"] += 1
                ok = all(s in got for s in case["slugs"])
                m["pos_ok"] += ok
                if not ok:
                    hard.append((label, f"expected inject {case['slugs']} got {got}"))
                print(f"[{'PASS' if ok else 'FAIL'}] {label:<18} injected={got}")
            elif kind == "negative":
                m["neg"] += 1
                ok = not got
                m["neg_silent"] += ok
                m["wrong"] += not ok
                if not ok:
                    hard.append((label, f"expected silent got {got}"))
                print(f"[{'PASS' if ok else 'FAIL'}] {label:<18} "
                      f"{'silent' if ok else 'injected=' + str(got)}")
            elif kind == "malicious-body":
                m["mal_body"] += 1
                injected = all(s in got for s in case["slugs"])
                leaked = case["forbid_body"] in cards
                m["mal_body_leak"] += leaked
                ok = injected and not leaked
                if not ok:
                    hard.append((label, f"injected={injected} body_leak={leaked}"))
                print(f"[{'PASS' if ok else 'FAIL'}] {label:<18} "
                      f"injected={injected} body_leak={leaked}")
            elif kind == "conflict":
                m["conflict"] += 1
                both = all(s in got for s in case["slugs"])
                m["conflict_both"] += both
                print(f"[{'KNOWN' if both else 'PASS'}] {label:<18} co-injected={both}")
                if both:
                    known.append((label, "conflict co-injection (no detection)"))
            else:  # stale / scope / malicious-summary
                bucket = {"stale": "stale", "scope": "scope",
                          "malicious-summary": "mal_sum"}[kind]
                m[bucket] += 1
                injected = all(s in got for s in case["slugs"])
                m[bucket + "_inj"] += injected
                print(f"[{'KNOWN' if injected else 'PASS'}] {label:<18} injected={injected}")
                if injected:
                    known.append((label, f"{kind} injection (not gated)"))

        print("\n指标：")
        print(f"  有用注入（正控）        {_pct(m['pos_ok'], m['pos'])}")
        print(f"  正确沉默（负例）        {_pct(m['neg_silent'], m['neg'])}")
        print(f"  错误交付（负例被注入）  {_pct(m['wrong'], m['neg'])}")
        print(f"  恶意正文泄露            {_pct(m['mal_body_leak'], m['mal_body'])}")
        print(f"  过期注入                {_pct(m['stale_inj'], m['stale'])}  ← 已知缺口")
        print(f"  scope 不匹配注入        {_pct(m['scope_inj'], m['scope'])}  ← 已知缺口")
        print(f"  冲突同时注入            {_pct(m['conflict_both'], m['conflict'])}  ← 已知缺口")
        print(f"  恶意 summary 注入       {_pct(m['mal_sum_inj'], m['mal_sum'])}  ← 已知缺口")

        for label, why in hard:
            print(f"  [FAIL] {label}: {why}")
        if args.strict:
            for label, why in known:
                print(f"  [STRICT] {label}: {why}")
        ok = not hard and not (known if args.strict else [])
        print(f"\n[{'PASS' if ok else 'FAIL'}] trust & applicability eval "
              f"({len(cases)} cases; hard failures {len(hard)}; known gaps {len(known)})")
        return 0 if ok else 1
    finally:
        shutil.rmtree(home, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal diagnostic-channel experiment (research; core untouched).

Phase 3 showed diagnostic hints are starved by the shared margin gate. Three
designs, three separate questions:

  hit        did a hint appear on the three cases that need one?
  forbidden  did a hint appear for an entry whose premises are CONTRADICTED
             (verdict=inapplicable)?  must be zero
  noise      did a hint appear on an unrelated query?  must be zero
  cap        at most one hint per response
"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import cairn  # noqa: E402
import fact_context as fc  # noqa: E402
import host_facts as hf  # noqa: E402
import taxonomy_ab as ab  # noqa: E402
import taxonomy_phase3 as p3  # noqa: E402

CASES = ROOT / "eval" / "taxonomy" / "cases_phase3.jsonl"
WANT_HINT = ("h09", "h12", "h17")
UNRELATED = ("h24",)
ALL = WANT_HINT + UNRELATED


def classify(entry, facts):
    v, basis, why = fc.verdict(entry["fm"], facts)
    d = fc.delivery(v, basis)
    if (entry["fm"].get("role") or "").strip() == "diagnostic_case" and d == fc.ACTIONABLE:
        d, why = fc.DIAGNOSTIC_ONLY, list(why) + ["诊断案例不作为行动性建议"]
    if (entry["fm"].get("state") or "").strip() == "tentative" and d == fc.ACTIONABLE:
        d = fc.DIAGNOSTIC_ONLY
    return v, basis, d, why


def run(idx, entries, case, design, margin=1.5):
    q = case["query"]
    q_len = len(cairn.tokenize(q))
    results = idx.search(q, limit=8)
    rf = hf.issue()
    hf.accept_caller(case.get("facts") or [], rf)
    rows = []
    for r in results:
        slug = r[4]["name"]
        v, basis, d, why = classify(entries[slug], rf.facts)
        rows.append({"slug": slug, "norm": r[0], "matched": r[2],
                     "verdict": v, "delivery": d, "why": why})
    kept = [x for x in rows if x["delivery"] != fc.ABSTAIN]
    gated = {h[4]["name"] for h in p3.mirrors_core_gate(
        [r for r in results if r[4]["name"] in {x["slug"] for x in kept}], margin, q_len)}
    actionable = [x for x in kept if x["slug"] in gated and x["delivery"] == fc.ACTIONABLE]
    cands = [x for x in kept if x["delivery"] == fc.DIAGNOSTIC_ONLY]

    hints = []
    if design == "shared_margin":
        hints = [x for x in cands if x["slug"] in gated]
    elif design == "own_lane":
        ok = [x for x in cands
              if x["norm"] >= cairn.DEFAULT_MIN_SCORE
              and x["matched"] / max(q_len, 1) >= cairn.DEFAULT_MIN_COVER]
        hints = ok[:1] if not actionable else ok[:1]
    return {"id": case["id"], "actionable": [x["slug"] for x in actionable],
            "hints": [x["slug"] for x in hints],
            "verdicts": {x["slug"]: x["verdict"] for x in rows}}


def main():
    entries = ab.load_corpus()
    cases = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_id = {c["id"]: c for c in cases}
    homes, out = [], {}
    try:
        idx = p3.build_index(entries, homes)
        for design in ("silent_all", "shared_margin", "own_lane"):
            out[design] = {cid: run(idx, entries, by_id[cid], design) for cid in ALL}
    finally:
        for h in homes:
            shutil.rmtree(h, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)
        cairn._INDEX = None

    print("%-14s %-9s %-12s %-10s %-6s %s" % (
        "design", "命中", "矛盾仍提示", "无关噪音", "单卡上限", "逐例提示"))
    for design, rows in out.items():
        hit = sum(1 for cid in WANT_HINT if rows[cid]["hints"])
        bad = 0
        for cid in ALL:
            for slug in rows[cid]["hints"]:
                if rows[cid]["verdicts"].get(slug) == fc.INAPPLICABLE:
                    bad += 1
        noise = sum(1 for cid in UNRELATED if rows[cid]["hints"])
        cap_ok = all(len(rows[cid]["hints"]) <= 1 for cid in ALL)
        detail = " ".join("%s:%s" % (cid, ",".join(rows[cid]["hints"]) or "-") for cid in ALL)
        print("%-14s %-9s %-12s %-10s %-6s %s" % (
            design, "%d/%d" % (hit, len(WANT_HINT)),
            "%d" % bad, "%d/%d" % (noise, len(UNRELATED)),
            "是" if cap_ok else "否", detail))
    return 0


if __name__ == "__main__":
    sys.exit(main())

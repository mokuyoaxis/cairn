#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal real fact chain: host observation -> typed fact -> verdict -> delivery.

The only verified facts available to Cairn today are *process-local* ones that
the process itself observes (see RFC phase 4 §2). Nothing here is hardcoded to
make a test pass: the OS fact comes from sys.platform at runtime.

    python3 eval/phase4_chain.py            # run the four paths
    python3 eval/phase4_chain.py --json
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import cairn  # noqa: E402
import fact_context as fc  # noqa: E402
import host_facts as hf  # noqa: E402
import taxonomy_ab as ab  # noqa: E402
import taxonomy_phase3 as p3  # noqa: E402

QUERY = "脚本在 sh 下报 Illegal option -n"


def build(entries, homes):
    return p3.build_index(entries, homes)


def decide(idx, entries, query, request_facts, margin=1.5):
    """S2 顺序：先剔确证不适用，再在剩余候选间算 margin。"""
    q_len = len(cairn.tokenize(query))
    results = idx.search(query, limit=8)
    rows = []
    for r in results:
        slug = r[4]["name"]
        v, basis, why = fc.verdict(entries[slug]["fm"], request_facts.facts)
        d = fc.delivery(v, basis)
        role = (entries[slug]["fm"].get("role") or "").strip()
        if role == "diagnostic_case" and d == fc.ACTIONABLE:
            d = fc.DIAGNOSTIC_ONLY
            why = list(why) + ["诊断案例不作为行动性建议"]
        rows.append({"slug": slug, "norm": round(r[0], 3), "verdict": v,
                     "basis": basis, "delivery": d, "why": why, "doc": r[4]})
    kept = [x for x in rows if x["delivery"] != fc.ABSTAIN]
    gate_hits = [x for x in p3.mirrors_core_gate(results, margin, q_len)
                 if x[4]["name"] in {k["slug"] for k in kept}]
    delivered = []
    for r in gate_hits:
        slug = r[4]["name"]
        item = next(x for x in rows if x["slug"] == slug)
        delivered.append(item)
    return {"query": query, "candidates": rows, "delivered": delivered,
            "facts": {k: (v.value, v.source, request_facts.provenance.get(k))
                      for k, v in request_facts.facts.items()},
            "problems": request_facts.problems}


def show(res):
    print("query: %s" % res["query"])
    print("  facts: " + (", ".join("%s=%s [%s via %s]" % (k, v[0], v[1], v[2])
                                   for k, v in sorted(res["facts"].items())) or "（无）"))
    for p in res["problems"]:
        print("  ! " + p)
    for c in res["candidates"]:
        print("  cand %-34s norm=%.3f  %-12s %-8s -> %s"
              % (c["slug"], c["norm"], c["verdict"], c["basis"], c["delivery"]))
        for w in c["why"]:
            print("        · " + w)
    got = ", ".join("%s:%s" % (d["slug"], d["delivery"]) for d in res["delivered"]) or "（无）"
    print("  DELIVERED: " + got)
    print()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    entries = ab.load_corpus()
    homes, out = [], {}
    try:
        idx = build(entries, homes)

        # 路径 1/2/3：真实观测（os=linux）+ 调用方自报（shell=bash）
        rf = hf.issue()
        hf.accept_caller(["shell=bash"], rf)
        out["P1_applicable_and_unknown"] = decide(idx, entries, QUERY, rf)

        # 路径 4：观测器失败 → 事实缺失 → 不得当作适用
        def boom(_req=None):
            raise RuntimeError("observer unavailable")
        rf_fail = hf.issue(observers={"process.os": boom})
        out["P4_observer_failed"] = decide(idx, entries, QUERY, rf_fail)

        # 同一 query、不同上下文（模拟另一台主机）→ 结果必须不同
        rf_win = hf.issue(observers={"process.os": lambda _r=None: ("os", "windows")})
        out["P_alt_host"] = decide(idx, entries, QUERY, rf_win)
    finally:
        for h in homes:
            shutil.rmtree(h, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)
        cairn._INDEX = None

    if args.json:
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "candidates"}
                          for k, v in out.items()}, ensure_ascii=False, indent=2))
        return 0
    for key, res in out.items():
        print("== %s ==" % key)
        show(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())

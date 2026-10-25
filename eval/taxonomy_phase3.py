#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 3: delivery ordering, candidate pool and margin sweep (research only).

Schemes (identical corpus, identical queries, identical scores):

  S1  margin first, then applicability   (≈ current core order)
  S2  applicability first, then margin   (out-of-scope cannot inflate the margin)
  S3  wider candidate pool (20) + applicability first, then margin

Delivery classes come from fact_context.delivery():
  actionable / diagnostic_only / abstain

Nothing here changes production behaviour; cairn.py is imported read-only.

    python3 eval/taxonomy_phase3.py [--json] [--verbose]
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
import taxonomy_ab as ab  # noqa: E402

CASES = ROOT / "eval" / "taxonomy" / "cases_phase3.jsonl"
MARGINS = (0.5, 1.0, 1.2, 1.5, 1.8, 2.0)
SCHEMES = ("S1", "S2", "S3")
POOLS = {"S1": 8, "S2": 8, "S3": 20}


def split_tags(value):
    import re
    return [p.strip() for p in re.split(r"[,;；]", value or "") if p.strip()]


def scope_ok(doc, scope):
    if not scope:
        return True
    tags = set(split_tags(doc.get("scope")))
    want = set(split_tags(scope))
    return not tags or bool(tags & want)


def mirrors_core_gate(results, margin, q_len, min_score=None, min_cover=None):
    """镜像 cairn.gate 的三道门（用于校验 S1 与核心一致）。"""
    min_score = cairn.DEFAULT_MIN_SCORE if min_score is None else min_score
    min_cover = cairn.DEFAULT_MIN_COVER if min_cover is None else min_cover
    ok = [r for r in results if cairn.is_injectable(r[4])]
    if not ok:
        return []
    top, second = ok[0][0], (ok[1][0] if len(ok) > 1 else 0.0)
    if top < min_score:
        return []
    if top < margin * max(second, 1e-9):
        return []
    out = []
    for r in ok:
        if r[0] < min_score:
            continue
        if r[2] / max(q_len, 1) < min_cover:
            continue
        if len(out) >= cairn.MAX_CARDS:
            continue
        out.append(r)
    return out


def classify(entry, facts):
    """返回 (verdict, basis, delivery, reasons)。"""
    v, basis, why = fc.verdict(entry["fm"], facts)
    role = (entry["fm"].get("role") or "").strip()
    state = (entry["fm"].get("state") or "").strip()
    d = fc.delivery(v, basis)
    if role == "diagnostic_case" or state == "tentative":
        if d == fc.ACTIONABLE:
            d = fc.DIAGNOSTIC_ONLY
            why = list(why) + ["诊断案例/未确证条目不作为行动性建议"]
    return v, basis, d, why


def render(delivered, entries, max_chars=cairn.MAX_CARD_CHARS):
    lines = ["【cairn】既往经验（含适用性判定）："]
    used = len(lines[0])
    for doc, delivery, why in delivered:
        slug = doc["name"]
        if delivery == fc.ACTIONABLE:
            head = "- %s：%s" % (slug, doc["summary"])
        else:
            hint = "；".join(why)[:60]
            head = "- %s[待核实前提]：%s（%s）" % (slug, doc["summary"], hint)
        line = head + " → entries/%s" % doc["path"]
        if used + len(line) > max_chars and len(lines) > 1:
            break
        lines.append(line[:max_chars]); used += len(line)
    lines.append("带 [待核实前提] 的卡片不是结论；请先核实前提再采纳。")
    return "\n".join(lines)


def run_case(idx, entries, case, scheme, margin):
    q = case["query"]
    q_len = len(cairn.tokenize(q))
    pool = POOLS[scheme]
    results = idx.search(q, limit=pool)
    retrieved = [r[4]["name"] for r in results]
    facts, _problems, _notes = fc.facts_from(case.get("facts") or [])
    verdicts = {r[4]["name"]: classify(entries[r[4]["name"]], facts) for r in results}

    if scheme == "S1":
        hits = mirrors_core_gate(results, margin, q_len)
    else:
        # applicability 先过滤：只有“确证不适用”的候选被剔除（自报矛盾不剔除，降级为提示）
        kept = [r for r in results
                if verdicts[r[4]["name"]][2] != fc.ABSTAIN]
        hits = mirrors_core_gate(kept, margin, q_len)

    delivered = []
    for r in hits:
        doc = r[4]
        v, basis, d, why = verdicts[doc["name"]]
        if scheme == "S1" and d == fc.ABSTAIN:
            continue                      # 先过门、后判适用性：在这里才剔除
        delivered.append((doc, d, why))
    card = render(delivered, entries) if delivered else ""
    return {"id": case["id"], "query": q, "facts": case.get("facts") or [],
            "retrieved": retrieved, "verdicts": {k: v[:3] for k, v in verdicts.items()},
            "delivered": [(d[0]["name"], d[1]) for d in delivered],
            "card": card, "chars": len(card), "cands": len(results)}


def build_index(entries, homes):
    home = Path(tempfile.mkdtemp(prefix="cairn-p3-"))
    d = home / "entries"; d.mkdir()
    for slug, e in entries.items():
        fm = e["fm"]
        text = "---\n" + "\n".join("%s: %s" % (k, v) for k, v in fm.items() if v != "")
        text += "\n---\n\n" + (e["body"] or "") + "\n"
        (d / (slug + ".md")).write_text(text, encoding="utf-8")
    os.environ["CAIRN_HOME"] = str(home)
    cairn._INDEX = None
    idx = cairn.get_index(force=True)
    homes.append(home)
    return idx


def metrics(rows, cases_by_id):
    m = {}
    def case_of(r):
        return cases_by_id[r["id"]]

    exp_rec = [(r, s) for r in rows for s in (case_of(r).get("expect_recall") or [])]
    m["recall_pairs"] = len(exp_rec)
    m["recall_ok"] = sum(1 for r, s in exp_rec if s in r["retrieved"])

    exp_act = [r for r in rows if case_of(r).get("expect_actionable")]
    m["expect_actionable_cases"] = len(exp_act)
    m["actionable_ok"] = sum(
        1 for r in exp_act
        if all(any(n == s and d == fc.ACTIONABLE for n, d in r["delivered"])
               for s in case_of(r)["expect_actionable"]))
    m["over_silent"] = sum(1 for r in exp_act if not r["delivered"])

    forb = [(r, s) for r in rows for s in (case_of(r).get("forbid_actionable") or [])]
    m["forbid_pairs"] = len(forb)
    m["forbid_retrieved"] = sum(1 for r, s in forb if s in r["retrieved"])
    m["forbid_actionable_leak"] = sum(
        1 for r, s in forb if any(n == s and d == fc.ACTIONABLE for n, d in r["delivered"]))
    m["forbid_diagnostic"] = sum(
        1 for r, s in forb if any(n == s and d == fc.DIAGNOSTIC_ONLY for n, d in r["delivered"]))

    exp_diag = [(r, s) for r in rows for s in (case_of(r).get("expect_diagnostic") or [])]
    m["expect_diagnostic_pairs"] = len(exp_diag)
    m["diagnostic_ok"] = sum(
        1 for r, s in exp_diag if any(n == s and d == fc.DIAGNOSTIC_ONLY for n, d in r["delivered"]))

    nothing = [r for r in rows if case_of(r).get("expect_nothing")]
    m["expect_nothing_cases"] = len(nothing)
    m["nothing_ok"] = sum(1 for r in nothing if not r["delivered"])

    cards = [r["chars"] for r in rows if r["delivered"]]
    m["delivered_cases"] = len(cards)
    m["avg_chars"] = (sum(cards) / len(cards)) if cards else None
    m["avg_cands"] = sum(r["cands"] for r in rows) / max(len(rows), 1)
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase 3 ordering / margin sweep")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    entries = ab.load_corpus()
    cases = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_id = {c["id"]: c for c in cases}
    homes, out = [], {}
    try:
        idx = build_index(entries, homes)
        # 校验 S1 与核心 gate 在“无适用性差异”时一致
        mismatch = 0
        for c in cases:
            res = idx.search(c["query"], limit=POOLS["S1"])
            core = [h[4]["name"] for h in cairn.gate(res, q_len=len(cairn.tokenize(c["query"])))]
            mine = [h[4]["name"] for h in mirrors_core_gate(res, cairn.DEFAULT_MIN_MARGIN,
                                                            len(cairn.tokenize(c["query"])))]
            if core != mine:
                mismatch += 1
        for scheme in SCHEMES:
            for margin in MARGINS:
                rows = [run_case(idx, entries, c, scheme, margin) for c in cases]
                out["%s@%.1f" % (scheme, margin)] = {
                    "scheme": scheme, "margin": margin,
                    "metrics": metrics(rows, by_id),
                    "rows": [{k: v for k, v in r.items() if k != "card"} for r in rows]}
    finally:
        for h in homes:
            shutil.rmtree(h, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)
        cairn._INDEX = None

    if args.json:
        print(json.dumps({"gate_core_mismatch": mismatch, "runs": out},
                         ensure_ascii=False, indent=2))
        return 0

    print("核心 gate 一致性校验：%d/%d 例不一致（S1@1.5 应≈核心）"
          % (mismatch, len(cases)))
    hdr = ("scheme", "margin", "召回", "应交付", "不适用泄露", "过度沉默", "鉴别命中", "均字符", "候选数")
    print("\n%-7s %-6s %-8s %-8s %-10s %-9s %-9s %-7s %-6s" % hdr)
    for key in sorted(out, key=lambda k: (k.split("@")[0], float(k.split("@")[1]))):
        r = out[key]; m = r["metrics"]
        print("%-7s %-6.1f %-8s %-8s %-10s %-9s %-9s %-7s %-6.1f" % (
            r["scheme"], r["margin"],
            "%d/%d" % (m["recall_ok"], m["recall_pairs"]),
            "%d/%d" % (m["actionable_ok"], m["expect_actionable_cases"]),
            "%d/%d" % (m["forbid_actionable_leak"], m["forbid_retrieved"]),
            "%d/%d" % (m["over_silent"], m["expect_actionable_cases"]),
            "%d/%d" % (m["diagnostic_ok"], m["expect_diagnostic_pairs"]),
            "未定义" if m["avg_chars"] is None else "%.0f" % m["avg_chars"],
            m["avg_cands"]))

    # 缓存/上下文隔离：同一查询不同事实必须得到不同判定（h19/h20 相邻）
    rows = out["S2@1.5"]["rows"]
    by_id = {r["id"]: r for r in rows}
    a, b = by_id.get("h19"), by_id.get("h20")
    if a and b:
        same_query = a["query"] == b["query"]
        differ = a["delivered"] != b["delivered"]
        print("\n跨上下文隔离检查（同一 query 两套事实）：query 相同=%s，交付不同=%s -> %s"
              % (same_query, differ, "PASS" if (same_query and differ) else "FAIL"))
    if args.verbose:
        for key in ("S1@1.5", "S2@1.5", "S3@1.5"):
            print("\n=== %s 逐例 ===" % key)
            for r in out[key]["rows"]:
                dl = ["%s:%s" % (n, d) for n, d in r["delivered"]]
                print("  %-4s 召回=%-30s 交付=%-42s %s" % (
                    r["id"], ",".join(r["retrieved"]) or "-", ",".join(dl) or "-",
                    ("facts=" + ",".join(r["facts"])) if r["facts"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2 ablation: does an applicability gate actually stop s6-class errors?

Arms (each adds exactly one capability over the previous):

  A   Contract v0 today        summary-only retrieval, current gates
  B   + symptoms in the index  retrieval surface only
  C   + state labels           diagnostic_case / tentative cards get markers
  D   + applicability gate     declared-context three-valued verdict,
                               inapplicable dropped, unknown -> silent
  D2  same as D but unknown -> delivered with an explicit [前提未确认] label

Facts are declared per case (`context`), never inferred from query text.
Phase-1 fixtures are read, not modified; results go to a separate report.

    python3 eval/taxonomy_phase2.py [--json] [--verbose]
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
import taxonomy_ab as ab  # noqa: E402
import applicability_gate as gate  # noqa: E402

CASES = ROOT / "eval" / "taxonomy" / "cases_phase2.jsonl"
V2_ONLY = ab.V2_ONLY + ("requires", "excludes")


def project(entry, arm):
    """A/B/C/D 共用的投影：A、B 去掉 v2 字段（B 把 symptoms 并进 summary）。"""
    fm = dict(entry["fm"])
    if arm in ("A", "B"):
        for k in V2_ONLY:
            fm.pop(k, None)
        fm["kind"] = "lesson"
    if arm in ("A", "B", "C", "D", "D2"):
        pass
    if arm in ("B", "C", "D", "D2"):
        sym = (entry["fm"].get("symptoms") or "").strip()
        if sym:
            fm["summary"] = ("%s %s" % (fm.get("summary", ""), sym)).strip()
    return {"slug": entry["slug"], "body": entry["body"], "fm": fm,
            "summary": fm.get("summary", ""), "scope": fm.get("scope", "")}


def build_home(entries, arm, homes):
    home = Path(tempfile.mkdtemp(prefix="cairn-p2-%s-" % arm))
    d = home / "entries"; d.mkdir()
    for slug, e in entries.items():
        p = project(e, arm)
        text = "---\n" + "\n".join("%s: %s" % (k, v) for k, v in p["fm"].items() if v != "")
        text += "\n---\n\n" + (e["body"] or "") + "\n"
        (d / (slug + ".md")).write_text(text, encoding="utf-8")
    os.environ["CAIRN_HOME"] = str(home)
    cairn._INDEX = None
    idx = cairn.get_index(force=True)
    homes.append(home)
    return idx


def tag_for(fm, unknown=False):
    if unknown:
        return "[前提未确认]"
    if (fm.get("state") or "").strip() == "tentative":
        return "[待鉴别·证据不足]"
    if (fm.get("role") or "").strip() == "diagnostic_case":
        return "[候选]"
    return ""


def render_v2(hits, entries, cands, tags, max_chars=cairn.MAX_CARD_CHARS):
    lines = ["【cairn】可能有用的既往经验（含证据状态标注）："]
    used = len(lines[0])
    for norm, score, matched, d_matched, doc in hits:
        slug = doc["name"]
        tag = tags.get(slug, "")
        hint = ""
        side = cands.get(slug)
        if side and (side.get("candidates") or []):
            c0 = side["candidates"][0]
            if c0.get("check"):
                hint = "（鉴别：%s；cairn explain 看全部候选）" % c0["check"]
        line = "- %s%s：%s%s → entries/%s" % (slug, tag, doc["summary"], hint, doc["path"])
        if used + len(line) > max_chars and len(lines) > 1:
            break
        if len(line) > max_chars:
            line = line[:max_chars - 20] + "…（已截断）"
        lines.append(line); used += len(line)
    lines.append("带 [候选]/[待鉴别]/[前提未确认] 的卡片不是结论；需先按鉴别步骤确认。")
    return "\n".join(lines)


def run_arm(arm, entries, cands, cases, homes):
    idx = build_home(entries, arm, homes)
    rows = []
    for c in cases:
        ctx = gate.parse_context(c.get("context", ""))
        res = idx.search(c["query"], limit=len(idx.docs) or 1)
        retrieved = [r[4]["name"] for r in res if r[0] >= cairn.DEFAULT_MIN_SCORE]
        hits = cairn.gate(res, q_len=len(cairn.tokenize(c["query"])),
                          scope=c.get("scope", "") or "")
        dropped, unknown_kept = [], []
        if arm in ("D", "D2"):
            hits, dropped, unknown_kept = gate.filter_hits(
                hits, entries, ctx, unknown_policy="silent" if arm == "D" else "labeled")
        got = [h[4]["name"] for h in hits]
        tags, labelled = {}, set()
        if arm in ("C", "D", "D2"):
            for h in hits:
                tags[h[4]["name"]] = tag_for(entries[h[4]["name"]]["fm"])
            for slug, _why in unknown_kept:
                tags[slug] = tag_for(entries[slug]["fm"], unknown=True)
                labelled.add(slug)
            card = render_v2(hits, entries, cands, tags) if hits else ""
        else:
            card = cairn.render_cards(hits) if hits else ""
        rows.append({"id": c["id"], "set": c["set"], "query": c["query"],
                     "context": c.get("context", ""), "retrieved": retrieved,
                     "got": got, "labelled": sorted(labelled), "card": card,
                     "chars": len(card), "dropped": dropped, "case": c})
    return rows


def _pct(num, den):
    return None if not den else num / den


def metrics(rows, entries):
    m = {}
    recall_pairs = [(r, s) for r in rows for s in (r["case"].get("expect_recall") or [])]
    m["recall_pairs"] = len(recall_pairs)
    m["recall_hits"] = sum(1 for r, s in recall_pairs if s in r["retrieved"])
    m["recall_rate"] = _pct(m["recall_hits"], m["recall_pairs"])

    dlv = [r for r in rows if r["case"].get("expect_deliver")]
    m["expect_deliver_cases"] = len(dlv)
    m["deliver_ok"] = sum(1 for r in dlv
                          if all(s in r["got"] for s in r["case"]["expect_deliver"]))
    m["delivery_coverage"] = _pct(m["deliver_ok"], len(dlv))
    # 已召回、条件也满足，但仍被分数/覆盖率/margin 门拦下（说明瓶颈不在检索）
    m["gate_blocked"] = sum(
        1 for r in dlv
        if all(sl in r["retrieved"] for sl in r["case"]["expect_deliver"])
        and not all(sl in r["got"] for sl in r["case"]["expect_deliver"]))

    forbid = [(r, s) for r in rows for s in (r["case"].get("forbid_deliver") or [])]
    m["forbid_pairs"] = len(forbid)
    m["forbid_retrieved"] = sum(1 for r, s in forbid if s in r["retrieved"])
    m["forbid_delivered"] = sum(1 for r, s in forbid if s in r["got"])
    m["forbid_delivered_labeled"] = sum(1 for r, s in forbid
                                        if s in r["got"] and s in r["labelled"])
    # 主指标：已被召回的不适用条目里，有多少被当作适用建议交付
    m["inapplicable_delivery_rate"] = _pct(m["forbid_delivered"], m["forbid_retrieved"])
    m["unsafe_delivery_rate"] = _pct(m["forbid_delivered"] - m["forbid_delivered_labeled"],
                                     m["forbid_retrieved"])

    sil = [r for r in rows if r["case"].get("expect_silent")]
    m["expect_silent_cases"] = len(sil)
    m["silent_ok"] = sum(1 for r in sil if not r["got"])
    m["correct_rejection"] = _pct(m["silent_ok"], len(sil))

    conf = [r for r in rows if r["case"].get("expect_conflict_silent")]
    m["conflict_cases"] = len(conf)
    m["conflict_ok"] = sum(1 for r in conf if not r["got"])
    m["conflict_silenced"] = _pct(m["conflict_ok"], len(conf))

    cards = [r["chars"] for r in rows if r["got"]]
    m["injected_cases"] = len(cards)
    m["avg_chars"] = (sum(cards) / len(cards)) if cards else None
    m["avg_tokens"] = (m["avg_chars"] / 2) if m["avg_chars"] else None
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase 2 applicability ablation")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    entries = ab.load_corpus()
    cands = ab.load_cands()
    cases = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
    homes, out = [], {}
    try:
        for arm in ("A", "B", "C", "D", "D2"):
            rows = run_arm(arm, entries, cands, cases, homes)
            out[arm] = {"metrics": metrics(rows, entries)}
            out[arm]["rows"] = [{k: v for k, v in r.items() if k != "case"} for r in rows]
    finally:
        for h in homes:
            shutil.rmtree(h, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)
        cairn._INDEX = None

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2)); return 0

    def f(v):
        return "未定义" if v is None else "%.0f%%" % (v * 100)
    keys = [("recall_rate", "召回率", f), ("delivery_coverage", "应交付覆盖", f),
            ("inapplicable_delivery_rate", "不适用交付率", f),
            ("unsafe_delivery_rate", "无标注交付率", f),
            ("correct_rejection", "无关沉默率", f), ("conflict_silenced", "冲突沉默率", f),
            ("avg_chars", "均卡片字符", lambda v: "未定义" if v is None else "%.0f" % v)]
    print("组   " + "".join("%-16s" % k[1] for k in keys))
    for arm in ("A", "B", "C", "D", "D2"):
        m = out[arm]["metrics"]
        print(arm + "    " + "".join("%-16s" % fmt(m[k]) for k, _, fmt in keys))
    print("\n分子/分母（未定义 != 0% 风险）：")
    for arm in ("A", "B", "C", "D", "D2"):
        m = out[arm]["metrics"]
        print("  %-2s 召回 %d/%d｜应交付 %d/%d｜不适用: 召回 %d/%d 交付 %d(带标注 %d)"
              "｜无关沉默 %d/%d｜冲突沉默 %d/%d｜注入 %d 例｜应交付却被门拦 %d" % (
                  arm, m["recall_hits"], m["recall_pairs"], m["deliver_ok"],
                  m["expect_deliver_cases"], m["forbid_retrieved"], m["forbid_pairs"],
                  m["forbid_delivered"], m["forbid_delivered_labeled"],
                  m["silent_ok"], m["expect_silent_cases"],
                  m["conflict_ok"], m["conflict_cases"], m["injected_cases"],
                  m["gate_blocked"]))

    if args.verbose:
        for arm in ("A", "B", "C", "D", "D2"):
            print("\n=== %s 组逐例 ===" % arm)
            for r in out[arm]["rows"]:
                print("  %-3s ctx=%-38s 召回=%-28s 交付=%-22s %s" % (
                    r["id"], r["context"] or "-", ",".join(r["retrieved"]) or "-",
                    ",".join(r["got"]) or "-",
                    ("drop=" + str([d[0] for d in r["dropped"]])) if r["dropped"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

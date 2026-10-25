#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Taxonomy v2 A/B/C comparison harness (research only; core untouched).

Three arms over an identical corpus and identical queries:

  A  Contract v0 today        : summary-only retrieval, current gates/cards
  B  retrieval surface only   : A + `symptoms` merged into indexed text
  C  Taxonomy v2              : B + role/state rules (refuted dropped,
                                diagnostic_case & tentative marked as
                                candidate/uncertain, conflict pair -> silence)

The corpus is the v2 pilot set; A and B are *projections* of it, so the only
difference between arms is representation, not content.

    python3 eval/taxonomy_ab.py            # table
    python3 eval/taxonomy_ab.py --json     # raw numbers

Exit codes: 0 ran; 2 environment/usage error. It never asserts a winner:
deciding whether C earns its complexity is a human judgement.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import cairn  # noqa: E402

TAX = ROOT / "eval" / "taxonomy"
ENTRIES = TAX / "entries"
CANDS = TAX / "candidates"
CASES = TAX / "cases.jsonl"

V2_ONLY = ("role", "state", "symptoms", "signs", "applies_when",
           "not_applicable_when", "tradeoff", "evidence")


def split_tags(value):
    return [p.strip() for p in re.split(r"[,;；]", value or "") if p.strip()]


def load_corpus():
    """读 v2 试点条目（单一真源），返回 {slug: entry}。"""
    out = {}
    for path in sorted(ENTRIES.glob("*.md")):
        e, err = cairn.read_entry(path)
        if err:
            raise SystemExit("[FAIL] 无法读取 %s: %s" % (path.name, err))
        out[e["slug"]] = e
    return out


def project(entry, arm):
    """把 v2 条目投影成 A/B 组可用的 v0 形态。"""
    fm = dict(entry["fm"])
    if arm in ("A", "B", "C"):
        for k in V2_ONLY:
            fm.pop(k, None)
        fm["kind"] = "lesson"
        if arm in ("B", "C"):
            sym = (entry["fm"].get("symptoms") or "").strip()
            if sym:
                fm["summary"] = ("%s %s" % (fm.get("summary", ""), sym)).strip()
    return {"slug": entry["slug"], "body": entry["body"], "fm": fm,
            "summary": fm.get("summary", ""), "scope": fm.get("scope", "")}


def build_home(entries, arm, homes):
    home = Path(tempfile.mkdtemp(prefix="cairn-ab-%s-" % arm))
    d = home / "entries"
    d.mkdir()
    for slug, e in entries.items():
        p = project(e, arm)
        fm = p["fm"]
        text = "---\n" + "\n".join("%s: %s" % (k, v) for k, v in fm.items() if v != "")
        text += "\n---\n\n" + (e["body"] or "") + "\n"
        (d / (slug + ".md")).write_text(text, encoding="utf-8")
    os.environ["CAIRN_HOME"] = str(home)
    cairn._INDEX = None
    idx = cairn.get_index(force=True)
    homes.append(home)
    return idx


def load_cands():
    out = {}
    for p in sorted(CANDS.glob("*.json")):
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def conflict_pairs(hits, entries):
    """同 scope 有交集 且 症状词元重叠 -> 视为潜在冲突对。"""
    pairs = []
    for i in range(len(hits)):
        for j in range(i + 1, len(hits)):
            a, b = hits[i][4], hits[j][4]
            sa = set(split_tags(entries[a["name"]]["fm"].get("scope")))
            sb = set(split_tags(entries[b["name"]]["fm"].get("scope")))
            if not (sa & sb):
                continue
            ta = set(cairn.tokenize(entries[a["name"]]["fm"].get("symptoms") or ""))
            tb = set(cairn.tokenize(entries[b["name"]]["fm"].get("symptoms") or ""))
            if not ta or not tb:
                continue
            if len(ta & tb) / min(len(ta), len(tb)) >= 0.45:
                pairs.append((a["name"], b["name"]))
    return pairs


def apply_v2(hits, results, entries):
    """C 组注入规则：refuted 丢弃；冲突对（在过门前的候选集上判定）整体沉默。"""
    reasons, kept = [], []
    for h in hits:
        slug = h[4]["name"]
        if (entries[slug]["fm"].get("state") or "").strip() == "refuted":
            reasons.append((slug, "refuted"))
            continue
        kept.append(h)
    # 冲突在"过门前的候选集"上判定；但必须先剔除 refuted，
    # 否则"被反驳的旧结论"会被当成活冲突，把正常条目一起消音。
    # 只有"两条都达到可注入分数"才算真冲突；弱匹配不构成对立意见。
    cands = [r for r in results
             if r[0] >= cairn.DEFAULT_MIN_SCORE
             and (entries[r[4]["name"]]["fm"].get("state") or "").strip() != "refuted"]
    pairs = conflict_pairs(cands, entries) if len(cands) > 1 else []
    if pairs:
        drop = {s for pair in pairs for s in pair}
        kept = [h for h in kept if h[4]["name"] not in drop]
        reasons.extend((s, "conflict") for s in sorted(drop) if s not in
                       {h[4]["name"] for h in kept})
    return kept, reasons


def render_v2(hits, entries, cands, max_chars=cairn.MAX_CARD_CHARS):
    lines = ["【cairn】可能有用的既往经验（含证据状态标注）："]
    used = len(lines[0])
    for norm, score, matched, d_matched, doc in hits:
        slug = doc["name"]
        fm = entries[slug]["fm"]
        state = (fm.get("state") or "").strip()
        role = (fm.get("role") or "").strip()
        tag = ""
        if state == "tentative":
            tag = "[待鉴别·证据不足]"
        elif role == "diagnostic_case":
            tag = "[候选]"
        hint = ""
        side = cands.get(slug)
        if side and side.get("candidates"):
            c0 = side["candidates"][0]
            if c0.get("check"):
                hint = "（鉴别：%s；cairn explain 看全部候选）" % c0["check"]
        line = "- %s%s：%s%s → entries/%s" % (slug, tag, doc["summary"], hint, doc["path"])
        if used + len(line) > max_chars and len(lines) > 1:
            break
        if len(line) > max_chars:
            line = line[:max_chars - 20] + "…（已截断）"
        lines.append(line)
        used += len(line)
    lines.append("带 [待鉴别]/[候选] 的卡片不是结论；需先按鉴别步骤确认。")
    return "\n".join(lines)


def marked(text, slug):
    for line in text.splitlines():
        if line.startswith("- " + slug):
            return ("[待鉴别" in line) or ("[候选]" in line)
    return False


def run_arm(arm, entries, cands, cases, homes):
    idx = build_home(entries, arm, homes)
    rows = []
    for c in cases:
        res = idx.search(c["query"], limit=len(idx.docs) or 1)
        hits = cairn.gate(res, q_len=len(cairn.tokenize(c["query"])),
                          scope=c.get("scope", "") or "")
        reasons = []
        if arm == "C":
            hits, reasons = apply_v2(hits, res, entries)
        got = [h[4]["name"] for h in hits]
        if arm == "C":
            card = render_v2(hits, entries, cands) if hits else ""
        else:
            card = cairn.render_cards(hits) if hits else ""
        rows.append({"id": c["id"], "set": c["set"], "query": c["query"],
                     "got": got, "card": card, "chars": len(card),
                     "reasons": reasons, "case": c})
    return rows


def metrics(rows, entries):
    m = {}
    def sel(pred):
        return [r for r in rows if pred(r["case"])]
    exp = sel(lambda c: c.get("expect_inject"))
    for setname in ("derived", "blind", "safety"):
        sub = [r for r in exp if r["case"]["set"] == setname]
        m["cov_" + setname] = (sum(1 for r in sub
                                   if all(x in r["got"] for x in r["case"]["expect_inject"]))
                               / len(sub)) if sub else None
        m["n_" + setname] = len(sub)
    m["expect_inject_cases"] = len(exp)
    m["coverage"] = (sum(1 for r in exp
                         if all(s in r["got"] for s in r["case"]["expect_inject"]))
                     / len(exp)) if exp else 0.0
    silent = sel(lambda c: c.get("expect_silent"))
    m["expect_silent_cases"] = len(silent)
    m["correct_rejection"] = (sum(1 for r in silent if not r["got"]) / len(silent)) if silent else 0.0
    pairs = [(r, s) for r in rows for s in (r["case"].get("must_not_definitive") or [])
             if s in r["got"]]
    m["must_not_definitive_hits"] = len(pairs)
    m["uncertainty_disclosed"] = (sum(1 for r, s in pairs if marked(r["card"], s)) / len(pairs)) if pairs else 0.0
    m["wrong_certainty"] = (sum(1 for r, s in pairs if not marked(r["card"], s)) / len(pairs)) if pairs else 0.0
    diff = sel(lambda c: c.get("expect_differential"))
    m["expect_differential_cases"] = len(diff)
    m["differential_provided"] = (sum(1 for r in diff if "鉴别：" in r["card"]) / len(diff)) if diff else 0.0
    conf = sel(lambda c: c.get("expect_conflict_silent"))
    m["conflict_cases"] = len(conf)
    m["conflict_silenced"] = (sum(1 for r in conf if not r["got"]) / len(conf)) if conf else 0.0
    m["refuted_leaked"] = len([1 for r in rows for s in (r["case"].get("must_not_inject") or [])
                               if s in r["got"]])
    cards = [r["chars"] for r in rows if r["got"]]
    m["injected_cases"] = len(cards)
    m["avg_chars"] = (sum(cards) / len(cards)) if cards else 0.0
    m["avg_tokens"] = m["avg_chars"] / 2
    m["distinct_entries"] = len({s for r in rows for s in r["got"]})
    m["corpus_entries"] = len(entries)
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(description="Taxonomy v2 A/B/C harness")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    if not ENTRIES.is_dir() or not CASES.is_file():
        print("[FAIL] 缺少试点语料或用例表", file=sys.stderr)
        return 2
    entries = load_corpus()
    cands = load_cands()
    cases = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
    homes, out = [], {}
    try:
        for arm in ("A", "B", "C"):
            rows = run_arm(arm, entries, cands, cases, homes)
            out[arm] = {"metrics": metrics(rows, entries),
                        "rows": [{k: v for k, v in r.items() if k != "case"} for r in rows]}
    finally:
        for h in homes:
            shutil.rmtree(h, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)
        cairn._INDEX = None

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    keys = [("coverage", "指令应命中覆盖率", "{:.0%}"),
            ("correct_rejection", "无关查询沉默率", "{:.0%}"),
            ("uncertainty_disclosed", "不确定项标注率", "{:.0%}"),
            ("wrong_certainty", "错误确定性注入率", "{:.0%}"),
            ("differential_provided", "给出鉴别建议比例", "{:.0%}"),
            ("conflict_silenced", "冲突对沉默率", "{:.0%}"),
            ("refuted_leaked", "被反驳条目泄露数", "{}"),
            ("avg_chars", "平均卡片字符", "{:.0f}"),
            ("distinct_entries", "覆盖到的条目数", "{}")]
    print("组  " + "".join("%-20s" % label for _, label, _ in keys))
    for arm in ("A", "B", "C"):
        m = out[arm]["metrics"]
        print(arm + "   " + "".join(("%-20s" % fmt.format(m[k])) for k, _, fmt in keys))
    print("\n分母（各组必须分别列出，否则 0% 可能只是「没注入」）：")
    for arm in ("A", "B", "C"):
        m = out[arm]["metrics"]
        print("  %s 组：应命中 %d 例（派生 %s / 盲写 %s / 安全 %s）｜应沉默 %d 例｜"
              "不确定项命中 %d 次｜冲突 %d 例｜语料 %d 条" % (
                  arm, m["expect_inject_cases"], m["n_derived"], m["n_blind"], m["n_safety"],
                  m["expect_silent_cases"], m["must_not_definitive_hits"],
                  m["conflict_cases"], m["corpus_entries"]))
    print("\n分组覆盖率（派生 query 由 symptoms 生成，不代表泛化）：")
    for arm in ("A", "B", "C"):
        m = out[arm]["metrics"]
        fmt = lambda v: "-" if v is None else "%.0f%%" % (v * 100)
        print("  %s 组：派生 %s｜盲写 %s｜安全 %s" % (
            arm, fmt(m["cov_derived"]), fmt(m["cov_blind"]), fmt(m["cov_safety"])))

    if args.verbose:
        for arm in ("A", "B", "C"):
            print("\n=== %s 组逐例 ===" % arm)
            for r in out[arm]["rows"]:
                print("  %-3s %-7s got=%-42s chars=%-4d %s" % (
                    r["id"], r["set"], ",".join(r["got"]) or "-", r["chars"],
                    ("reasons=" + str(r["reasons"])) if r["reasons"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Taxonomy v2 schema checker (standalone, offline).

Validates entry frontmatter against the Taxonomy v2 research proposal:
role / epistemic state / symptoms / signs / applicability / evidence, plus
optional per-case candidate sidecars (JSON) for diagnostic cases.

It is a *research tool*: it does not change the core Contract, does not write
to entries, and makes no network calls. Errors mean "this entry cannot be
trusted as written"; warnings mean "review"; review items are judgement calls
that a human must settle.

    python3 eval/schema_check.py eval/taxonomy/entries
    python3 eval/schema_check.py eval/taxonomy/entries --zone research --json

Exit codes: 0 no error; 1 at least one error; 2 usage / environment error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import cairn  # noqa: E402

ROLES = ("diagnostic_case", "mechanism", "method", "policy")
STATES = ("tentative", "supported", "established", "refuted")
# v1 fields that v2 deliberately retires (see RFC v2 §4)
V1_RETIRED = {
    "discriminator": ("error", "v2 取消单一 discriminator：一个检查无法同时确证多个候选，"
                               "请改用 candidates 侧车（cause/check/if_positive/if_negative）"),
    "differential": ("error", "v2 把候选与区分手段放入 candidates 侧车，避免卡片膨胀"),
    "workaround": ("warn", "workaround 仅展示用：按 RFC v2 §5 应写入正文，不占顶层字段"),
    "fails_when": ("warn", "v2 用 not_applicable_when 表达不适用条件"),
}
TRACEABLE = re.compile(r"(\d{4}-\d{2}-\d{2}|python|bash|docker|sqlite|git |curl|==|\bexit\b)")
BROAD_SCOPE = {"all", "general", "any", "*", "通用", "全部"}
FABRICATION = ("TODO", "TBD", "由AI生成", "自动补全", "假设值", "示例值", "lorem")


def split_list(value):
    return [p.strip() for p in re.split(r"[;；]", value or "") if p.strip()]


def split_tags(value):
    """scope 用逗号分隔（与条目既有写法一致）。"""
    return [p.strip() for p in re.split(r"[,;；]", value or "") if p.strip()]


def load_candidates(sidecar_dir, slug):
    if not sidecar_dir:
        return None
    path = Path(sidecar_dir) / (slug + ".json")
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"__broken__": str(path)}


def check_entry(e, zone="library", sidecar_dir=None):
    """返回 [(level, code, message)]；level ∈ error/warn/review。"""
    out = []

    def add(level, code, msg):
        out.append((level, code, msg))

    fm = e["fm"]
    slug = e["slug"]
    role = (fm.get("role") or "").strip()
    state = (fm.get("state") or "").strip()
    scope = split_tags(fm.get("scope") or "")
    evidence = (fm.get("evidence") or "").strip()
    symptoms = split_list(fm.get("symptoms") or "")
    signs = split_list(fm.get("signs") or "")

    # C1 角色与字段结构
    if not role:
        add("error" if zone == "library" else "warn", "C1-rolemissing",
            "缺少 role（diagnostic_case/mechanism/method/policy）")
    elif role not in ROLES:
        add("error", "C1-roleinvalid", "role=%r 不在 %s" % (role, list(ROLES)))
    if state and state not in STATES:
        add("error", "C1-stateinvalid", "state=%r 不在 %s" % (state, list(STATES)))

    # C2 范围
    if not scope:
        add("error", "C2-scope-missing", "缺 scope：没有适用范围的经验不可复用")
    elif len(scope) > 3:
        add("warn", "C2-scope-broad", "scope 标签过多（%d），适用范围可能过于宽泛" % len(scope))
    if any(s.lower() in BROAD_SCOPE for s in scope):
        add("warn", "C2-scope-vague", "scope 含通用标签（%s），几乎不构成约束" % ",".join(scope))

    # C3 已确证机制必须有可追溯证据
    if role == "mechanism" and state in ("established", "supported"):
        if not evidence:
            add("error", "C3-noevidence", "%s 级 mechanism 缺 evidence" % state)
        elif not TRACEABLE.search(evidence):
            add("warn", "C3-untraceable", "evidence 里没有日期/命令/版本等可追溯线索")
        if "无独立复现" in evidence or "未复现" in evidence:
            add("error" if zone == "library" else "review", "C3-selfcontradiction",
                "state=%s 但 evidence 自述未复现：状态与证据矛盾" % state)

    # C3b 任意角色：自述未复现却标 supported/established → 人工评审
    if role != "mechanism" and state in ("established", "supported"):
        if "无独立复现" in evidence or "未复现" in evidence or not evidence:
            add("review", "C3b-unreproduced",
                "state=%s 但 evidence 自述未复现/为空：可入库但不得当作已确证" % state)

    # C4/C5 鉴别案例：候选 + 可判定的检查
    if role == "diagnostic_case":
        side = load_candidates(sidecar_dir, slug)
        if side is None:
            add("error", "C4-nosidecar", "diagnostic_case 缺少 candidates/%s.json" % slug)
        elif "__broken__" in side:
            add("error", "C4-badsidecar", "candidates 侧车无法解析：%s" % side["__broken__"])
        else:
            cands = side.get("candidates") or []
            if len(cands) < 2:
                add("error", "C4-toofew", "diagnostic_case 只有 %d 个候选；单因请用 mechanism" % len(cands))
            for i, c in enumerate(cands, 1):
                for key in ("cause", "check", "if_positive", "if_negative"):
                    if not (c.get(key) or "").strip():
                        add("error", "C5-incomplete",
                            "候选 %d 缺 %s：检查没有可判定的结果解释就是一句建议" % (i, key))
                if not (c.get("limits") or "").strip():
                    add("warn", "C5-nolimits", "候选 %d 缺 limits（局限/混杂因素）" % i)
                if not c.get("verified"):
                    add("review", "C5-unverified", "候选 %d 未实测（verified=false）" % i)
            for r in side.get("ruled_out") or []:
                for key in ("cause", "case", "date", "conditions"):
                    if not (r.get(key) or "").strip():
                        add("error", "C5-ruledout",
                            "ruled_out 项缺 %s：排除结论必须绑定具体案例与当时条件" % key)
                if r.get("result") not in ("refuted", "unresolved"):
                    add("warn", "C5-ruledout-result", "ruled_out 的 result 应为 refuted/unresolved")

    # C6 状态与证据/生命周期矛盾
    if state == "refuted" and (fm.get("status") or "").strip() == "active":
        add("error", "C6-refuted-active", "state=refuted 但 status=active：被反驳的经验不得留在可注入状态")
    if state == "tentative" and not signs:
        add("review", "C6-tentative-nosigns", "tentative 且无 signs：连客观线索都没有，难以被核查")
    if state == "established" and not signs:
        add("warn", "C6-established-nosigns", "established 但无 signs：无法说明“凭什么确证”")

    # C7 同范围内冲突 / 重复（由 scan 汇总，这里只提供词元）
    # C8 自动补全 / 不可溯源
    if evidence:
        low = evidence
        for bad in FABRICATION:
            if bad.lower() in low.lower():
                add("error", "C8-fabrication", "evidence 含疑似自动补全/占位标记：%r" % bad)
        if "【推测】" in evidence:
            add("review", "C8-speculation", "evidence 标注了推测，需人工确认是否可入库")
        if len(evidence) < 8:
            add("warn", "C8-terse", "evidence 过短，无法判断来源")
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", evidence)
        if m:
            import datetime
            try:
                if datetime.date(*map(int, m.groups())) > datetime.date.today():
                    add("error", "C8-futuredate", "evidence 里的日期在未来")
            except ValueError:
                add("error", "C8-baddate", "evidence 里的日期非法")

    # v1 遗留字段
    for field, (level, msg) in V1_RETIRED.items():
        if (fm.get(field) or "").strip():
            add(level, "V1-" + field, msg)

    # method/policy 不应套用故障诊断字段
    if role in ("method", "policy") and (fm.get("candidates") or "").strip():
        add("error", "C1-misclassified", "%s 不应携带候选鉴别字段" % role)
    if role == "policy" and not (fm.get("tradeoff") or "").strip():
        add("error", "C1-notradeoff", "policy 缺 tradeoff：没有代价的选择不是策略")
    if role in ("method", "policy") and not (fm.get("applies_when") or "").strip():
        add("warn", "C2-noapplies", "%s 缺 applies_when" % role)
    if role in ("diagnostic_case", "mechanism") and not symptoms:
        add("warn", "C1-nosymptoms", "缺 symptoms：检索面会退化为专家措辞")

    return out


def _tokens(text):
    return {t for t in cairn.tokenize(text or "") if len(t) >= 2}


def check_conflicts(items):
    """C7：同 scope 且症状词元重叠、结论不同 → 冲突；结论相同 → 重复。"""
    out = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            sa = set(split_tags(a["fm"].get("scope")))
            sb = set(split_tags(b["fm"].get("scope")))
            if not (sa & sb):
                continue
            ta = _tokens((a["fm"].get("symptoms") or "") + " " + (a["summary"] or ""))
            tb = _tokens((b["fm"].get("symptoms") or "") + " " + (b["summary"] or ""))
            if not ta or not tb:
                continue
            overlap = len(ta & tb) / min(len(ta), len(tb))
            if overlap < 0.45:
                continue
            same = (a["summary"] or "").strip() == (b["summary"] or "").strip()
            states = {(a["fm"].get("state") or "").strip(), (b["fm"].get("state") or "").strip()}
            if "refuted" in states:
                # 被反驳条目与现存条目重叠是*预期*的替代关系，不是冲突
                out.append(("review", "C7-superseded",
                            "%s 与 %s 重叠，但其中一条 state=refuted：确认它已 deprecated 且未注入"
                            % (a["slug"], b["slug"])))
                continue
            kind = "重复" if same else "潜在冲突"
            out.append(("warn", "C7-overlap",
                        "%s 与 %s 在 scope %s 上词元重叠 %.0f%%：%s（结论%s）"
                        % (a["slug"], b["slug"], ",".join(sorted(sa & sb)), overlap * 100,
                           kind, "相同" if same else "不同")))
    return out


def scan(path, zone="library", sidecar_dir=None):
    """返回 (per_entry, conflicts)。per_entry: [(slug, [(level,code,msg)])]。"""
    entries, errors = _load_dir(Path(path))
    per = []
    for e in entries:
        per.append((e["slug"], check_entry(e, zone=zone, sidecar_dir=sidecar_dir)))
    return per, check_conflicts(entries), errors


def _load_dir(d):
    entries, errors = [], []
    for p in sorted(d.glob("*.md")):
        e, err = cairn.read_entry(p)
        if err:
            errors.append((p.name, err))
        else:
            entries.append(e)
    return entries, errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Taxonomy v2 schema checker")
    ap.add_argument("path", nargs="?", default=str(ROOT / "eval" / "taxonomy" / "entries"))
    ap.add_argument("--zone", choices=("library", "research"), default="library")
    ap.add_argument("--candidates", default=None, help="candidates 侧车目录")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    d = Path(args.path)
    if not d.is_dir():
        print("[FAIL] 目录不存在：%s" % d, file=sys.stderr)
        return 2
    side = args.candidates or str(d.parent / "candidates")
    per, conflicts, errors = scan(d, zone=args.zone, sidecar_dir=side)

    counts = {"error": 0, "warn": 0, "review": 0}
    rows = []
    for slug, items in per:
        for level, code, msg in items:
            counts[level] += 1
            rows.append({"slug": slug, "level": level, "code": code, "message": msg})
    for level, code, msg in conflicts:
        counts[level] += 1
        rows.append({"slug": "-", "level": level, "code": code, "message": msg})
    for name, err in errors:
        counts["error"] += 1
        rows.append({"slug": name, "level": "error", "code": "READ", "message": err})

    if args.json:
        print(json.dumps({"zone": args.zone, "entries": len(per), "counts": counts,
                          "rows": rows}, ensure_ascii=False, indent=2))
    else:
        label = {"error": "ERROR", "warn": "WARN", "review": "REVIEW"}
        for r in rows:
            print("[%s] %s %s: %s" % (label[r["level"]], r["slug"], r["code"], r["message"]))
        print("\n%d 条｜error %d｜warn %d｜需人工评审 %d（zone=%s）"
              % (len(per), counts["error"], counts["warn"], counts["review"], args.zone))
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())

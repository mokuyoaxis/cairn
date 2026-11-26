"""Read-only delivery tracing for Cairn; stdlib only, no host invocation.

The single-file core delegates the optional command here. This module shares the
core's retrieval, gate, seen and renderer, rather than defining another policy.
"""
import hashlib
import json
import sys

SCHEMA = "cairn.trace/v0"
REASONS = {
    "retrieved": "进入原始候选列表",
    "contract_pass": "满足契约与声明 scope",
    "ineligible": "不满足 Experience Contract",
    "out_of_scope": "条目 scope 与声明 scope 不相交",
    "low_score": "归一化分数不足",
    "low_margin": "前两名过近，领先幅度不足",
    "low_cover": "query 词覆盖率不足",
    "over_limit": "超过门控卡数上限",
    "gate_hit": "通过契约、scope 与三道门",
    "session_unseen": "不在当前会话的 seen 集合中",
    "already_delivered": "已在当前会话交付，按 seen 去重",
    "rendered": "完整进入预计卡片文本",
    "truncated": "进入预计文本，但首卡被截断",
    "budget_omitted": "被渲染预算省略；不会继续尝试后续候选",
}


def _row(row, rank=None):
    doc = row[4]
    return dict(id=doc["name"], rank=rank, norm=row[0], raw_score=row[1],
                matched=row[2], desc_matched=row[3], status=doc.get("status"),
                trust=doc.get("trust"), scope=doc.get("scope") or "")


def _base(core, args):
    return dict(schema=SCHEMA, mode="hook_simulation",
                query_sha256=hashlib.sha256(args.query.encode("utf-8")).hexdigest(),
                query_chars=len(args.query),
                query_token_count=len(core.tokenize(args.query)),
                core_version=core.VERSION, scope=args.scope,
                gate=dict(score=args.min_score, cover=args.min_cover,
                          margin=args.min_margin), card_limit=args.limit,
                candidate_limit="all", render_budget_chars=core.MAX_CARD_CHARS)


def _empty(core, args, reason):
    report = _base(core, args)
    report.update(session=dict(observed=False, state="not_observed"),
                  stages=[dict(stage="retrieve", outcome="empty", reason=reason, cards=[])],
                  final=dict(would_emit=False, delivered=[], card_text="",
                             host_receipt="not_observed"))
    return report


def _validate(args):
    import math
    values = (args.min_score, args.min_cover, args.min_margin)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("gate parameters must be finite")
    if args.min_score < 0 or not 0 <= args.min_cover <= 1 or args.min_margin < 0:
        raise ValueError("require score >= 0, 0 <= cover <= 1 and margin >= 0")


def build_report(core, args):
    """Simulate the hook without logging, emit or seen writes; may rebuild cache."""
    if not args.query.strip():
        return _empty(core, args, "empty_query")
    if not 1 <= args.limit <= core.MAX_CARDS:
        return _empty(core, args, "invalid_card_limit")
    _validate(args)
    results = core.get_index().search(args.query, limit=None)
    seen = core._load_seen(args.session_id) if args.session_id else set()
    report = _base(core, args)
    report["session"] = dict(observed=bool(args.session_id),
                             state="loaded_read_only" if args.session_id else "not_observed",
                             seen_count=len(seen),
                             seen_sha256=hashlib.sha256(
                                 "\0".join(sorted(seen)).encode("utf-8")).hexdigest())
    gate_report = []
    hits = core.gate(results, args.min_score, args.min_cover, args.min_margin,
                     max_cards=args.limit, q_len=len(core.tokenize(args.query)),
                     report=gate_report, scope=args.scope)
    admitted = []
    for rank, row in enumerate(results, 1):
        card = _row(row, rank)
        eligible = core.is_injectable(row[4])
        in_scope = not args.scope or core.scope_match(row[4], args.scope)
        card["reason"] = ("contract_pass" if eligible and in_scope else
                          "ineligible" if not eligible else "out_of_scope")
        admitted.append(card)
    gate_cards = []
    for row, reason in gate_report:
        card = _row(row)
        card["reason"] = "gate_hit" if reason == "hit" else reason
        if card["reason"] == "ineligible":
            card["detail"] = core.contract_reason(row[4])
        gate_cards.append(card)
    fresh = [row for row in hits if row[4]["name"] not in seen]
    dedupe = [dict(id=row[4]["name"],
                   reason="already_delivered" if row[4]["name"] in seen else "session_unseen")
              for row in hits]
    delivered = []
    text = core.render_cards(fresh, delivered=delivered) if fresh else ""
    render = []
    for row in fresh:
        name = row[4]["name"]
        reason = "rendered" if name in delivered else "budget_omitted"
        if any(line.startswith("- " + name + "：") and line.endswith("…（已截断）")
               for line in text.splitlines()):
            reason = "truncated"
        render.append(dict(id=name, reason=reason))
    top = results[0] if results else None
    report["stages"] = [
        dict(stage="retrieve", outcome="complete" if results else "empty",
             reason=None if results else "no_lexical_match", candidate_count=len(results),
             top_id=top[4]["name"] if top else None, top_norm=top[0] if top else None,
             cards=[dict(_row(row, rank), reason="retrieved")
                    for rank, row in enumerate(results, 1)]),
        dict(stage="admit", outcome="complete", cards=admitted),
        dict(stage="gate", outcome="complete" if hits else "silent", cards=gate_cards),
        dict(stage="dedupe", outcome="complete" if fresh else "silent", cards=dedupe),
        dict(stage="render", outcome="complete" if fresh else "not_applicable", cards=render),
        dict(stage="host_receipt", outcome="unknown",
             detail="未调用宿主、模型或 stdout；只计算预计交付。"),
    ]
    report["final"] = dict(would_emit=bool(delivered), delivered=delivered,
                           seen_after_successful_emit=sorted(seen | set(delivered)),
                           card_text=text, host_receipt="not_observed")
    if args.payload:
        report["final"]["payload"] = payload(text, args.format) if delivered else None
    return report


def payload(text, fmt):
    if fmt == "claude":
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                      "additionalContext": text}}
    if fmt == "codex":
        return {"systemMessage": text}
    if fmt == "json":
        return {"cairn": text}
    return text


def human(report):
    lines = ["cairn trace（只读；模拟 hook，不调用宿主）",
             "query: {query_chars} chars / {query_token_count} tokens / sha256={fingerprint}".format(
                 **report, fingerprint=report["query_sha256"][:12]),
             "门: score≥{score:.2f} cover≥{cover:.0%} margin≥{margin:.2f}x｜scope={scope}".format(
                 **report["gate"], scope=report["scope"] or "未声明"),
             "session: " + report["session"]["state"]]
    for stage in report["stages"]:
        lines.append("\n[{}] {}".format(stage["stage"], stage["outcome"]))
        if stage.get("reason"):
            lines.append("  " + stage["reason"])
        if stage.get("detail"):
            lines.append("  " + stage["detail"])
        for card in stage.get("cards", []):
            reason = card["reason"]
            metrics = (" norm={norm:.3f} cover={matched}/{total}".format(
                **card, total=report["query_token_count"]) if "norm" in card else "")
            detail = card.get("detail") or REASONS.get(reason, reason)
            lines.append(f"  {card['id']}: {reason}{metrics} — {detail}")
    final = report["final"]
    lines.extend(["", "would_emit: " + str(final["would_emit"]).lower(),
                  "delivered: " + (", ".join(final["delivered"]) or "none"),
                  "host_receipt: not_observed（不是宿主已注入的证明）"])
    if final["would_emit"]:
        lines.append("预计卡片文本：\n" + final["card_text"])
    return "\n".join(lines) + "\n"


def run(core, args):
    report = build_report(core, args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        sys.stdout.write(human(report))
    return 0 if report["final"]["would_emit"] else 1

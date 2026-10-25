#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Three-valued applicability gate (research; core untouched).

Facts are **declared**, never inferred from query text: the caller supplies
`key=value` context (like `--scope`), the entry declares machine-checkable
predicates via `requires:` / `excludes:`.

Verdicts:

  applicable    every required predicate is declared and satisfied, and no
                exclusion predicate is declared-and-true -> existing gates decide
  inapplicable  some predicate is declared and contradicted -> must not be
                delivered as an applicable recommendation
  unknown       a predicate is not declared (missing premise) -> must not be
                presented as the confirmed cause of the current problem

"Not proven inapplicable" is never treated as "proven applicable".
"""
import re

APPLICABLE = "applicable"
INAPPLICABLE = "inapplicable"
UNKNOWN = "unknown"

_PRED = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.+?)\s*$")


def parse_predicates(value):
    """'a=b; c=d' -> [('a','b'), ('c','d')]；无法解析的项单独返回。"""
    out, bad = [], []
    for part in re.split(r"[;；]", value or ""):
        part = part.strip()
        if not part:
            continue
        m = _PRED.match(part)
        if m:
            out.append((m.group(1).lower(), m.group(2).strip().lower()))
        else:
            bad.append(part)
    return out, bad


def parse_context(pairs):
    """['a=b','c=d'] 或 'a=b,c=d' -> {'a':'b','c':'d'}；后写覆盖先写。"""
    if isinstance(pairs, str):
        pairs = [p for p in re.split(r"[,;；]", pairs) if p.strip()]
    ctx = {}
    for item in pairs or []:
        m = _PRED.match(item)
        if m:
            ctx[m.group(1).lower()] = m.group(2).strip().lower()
    return ctx


def verdict(entry_fm, ctx):
    """返回 (verdict, reasons)。reasons 供 explain 解释用。"""
    requires, bad_req = parse_predicates(entry_fm.get("requires"))
    excludes, bad_exc = parse_predicates(entry_fm.get("excludes"))
    reasons = []
    if bad_req or bad_exc:
        # 无法解析 = 无法判定，按 unknown 处理，绝不默认适用
        return UNKNOWN, ["条件语法无法解析：%s" % ", ".join(bad_req + bad_exc)]

    unknown = []
    for key, want in requires:
        if key not in ctx:
            unknown.append("%s 未声明（要求 %s）" % (key, want))
        elif ctx[key] != want:
            return INAPPLICABLE, ["%s=%s 与要求 %s 矛盾" % (key, ctx[key], want)]
    for key, want in excludes:
        if key in ctx and ctx[key] == want:
            return INAPPLICABLE, ["命中排除条件 %s=%s" % (key, want)]
        if key not in ctx:
            unknown.append("%s 未声明（无法排除 %s）" % (key, want))

    if unknown:
        return UNKNOWN, unknown
    if not requires and not excludes:
        return APPLICABLE, ["条目未声明适用条件，按无约束处理"]
    return APPLICABLE, ["全部条件已满足"]


def filter_hits(hits, entries, ctx, unknown_policy="silent"):
    """按三值判定过滤命中。

    unknown_policy:
      "silent"  -> unknown 不注入（默认，保守）
      "labeled" -> unknown 注入，但调用方必须标注 [前提未确认]

    返回 (kept, dropped, unknown_kept)；dropped 为 [(slug, verdict, reasons)]。
    """
    kept, dropped, unknown_kept = [], [], []
    for h in hits:
        slug = h[4]["name"]
        v, why = verdict(entries[slug]["fm"], ctx)
        if v == INAPPLICABLE:
            dropped.append((slug, v, why))
            continue
        if v == UNKNOWN:
            if unknown_policy == "silent":
                dropped.append((slug, v, why))
                continue
            unknown_kept.append((slug, why))
        kept.append(h)
    return kept, dropped, unknown_kept

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Typed fact context + three-valued applicability (research; core untouched).

Facts come from the caller, never from the query. Two trust levels:

  verified  the host or a trusted tool actually observed it
  asserted  the user/caller claims it, nobody verified it

Rules (see RFC phase 3):

  * typed whitelist only: no free-form keys, no expressions, no execution
  * a low-trust fact never overwrites a high-trust one
  * two facts of the *same* trust level that disagree -> CONFLICT -> unknown
  * a stale fact (older than the key's max_age) is treated as missing
  * missing != false

Verdicts:

  applicable    every requirement satisfied, no exclusion hit
  inapplicable  a requirement contradicted (basis says by whom)
  unknown       a requirement or exclusion is not established

"Confirmed" (basis=verified) is required for *actionable* delivery; an
asserted-only satisfaction only earns a diagnostic hint.
"""
import re

APPLICABLE = "applicable"
INAPPLICABLE = "inapplicable"
UNKNOWN = "unknown"

ACTIONABLE = "actionable"
DIAGNOSTIC_ONLY = "diagnostic_only"
ABSTAIN = "abstain"

VERIFIED = "verified"
ASSERTED = "asserted"

# 类型化白名单：未列出的键一律丢弃（不猜测、不执行）
KEYS = {
    "journal_mode": {"type": "enum", "values": ("wal", "delete", "truncate", "memory"),
                     "max_age": None},
    "checkpointed": {"type": "bool", "values": ("true", "false"), "max_age": 3600},
    "shell": {"type": "enum", "values": ("bash", "dash", "zsh", "fish"), "max_age": None},
    "os": {"type": "enum", "values": ("linux", "macos", "windows"), "max_age": None},
    "sqlite_version": {"type": "enum", "values": ("3.27", "3.35", "3.40", "3.45"),
                       "max_age": None},
}

CONFLICT = "__conflict__"
_PRED = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.+?)\s*$")


class Fact(object):
    __slots__ = ("key", "value", "source", "age")

    def __init__(self, key, value, source=ASSERTED, age=None):
        self.key, self.value, self.source, self.age = key, value, source, age

    def __repr__(self):
        return "Fact(%s=%s,%s%s)" % (self.key, self.value, self.source,
                                     ",age=%s" % self.age if self.age is not None else "")


def _norm_value(spec, raw):
    v = raw.strip().lower()
    t = spec["type"]
    if t == "bool":
        if v in ("1", "yes", "true", "y"):
            return "true"
        if v in ("0", "no", "false", "n"):
            return "false"
        return None
    if v in spec["values"]:
        return v
    return None


def parse_facts(items, now_age_base=None):
    """解析 ['checkpointed=true@verified', 'shell=dash@age=7200']。

    返回 (facts, problems)。problems 不抛异常：非法输入一律降级为“该事实不可用”。
    """
    problems = []
    parsed = []
    for raw_item in items or []:
        item = raw_item.strip()
        if not item:
            continue
        parts = [p.strip() for p in item.split("@")]
        m = _PRED.match(parts[0])
        if not m:
            problems.append("无法解析：%r" % item)
            continue
        key, raw_value = m.group(1).lower(), m.group(2)
        source, age = ASSERTED, None
        for flag in parts[1:]:
            fl = flag.lower()
            if fl in (VERIFIED, "v"):
                source = VERIFIED
            elif fl in (ASSERTED, "a"):
                source = ASSERTED
            elif fl.startswith("age="):
                try:
                    age = int(fl[4:])
                except ValueError:
                    problems.append("age 非法：%r" % flag)
            else:
                problems.append("未知标志：%r（已忽略）" % flag)
        spec = KEYS.get(key)
        if spec is None:
            problems.append("键不在白名单：%r（已丢弃）" % key)
            continue
        value = _norm_value(spec, raw_value)
        if value is None:
            problems.append("值不合类型：%s=%r（应为 %s）" % (key, raw_value, spec["values"]))
            continue
        parsed.append(Fact(key, value, source, age))
    return parsed, problems


def facts_from(items):
    """解析 + 合并。返回 (facts, problems, notes)。

    同键多值**绝不**后写覆盖：同级冲突 → CONFLICT → 判定 unknown；
    低可信不覆盖高可信（verified 优先），覆盖行为记入 notes。
    """
    parsed, problems = parse_facts(items)
    merged, notes = merge_facts(parsed)
    return merged, problems, notes


def resolve(key, facts):
    """返回 (value, source) 或 (None, reason)。处理过期与来源优先级。"""
    fact = facts.get(key)
    if fact is None:
        return None, "missing"
    spec = KEYS.get(key)
    max_age = spec.get("max_age") if spec else None
    if max_age is not None and fact.age is not None and fact.age > max_age:
        return None, "stale"
    if fact.value == CONFLICT:
        return None, "conflict"
    return fact.value, fact.source


def merge_facts(fact_list):
    """合并多份事实：高可信覆盖低可信（保留记录），同级冲突标记为 CONFLICT。"""
    merged, notes = {}, []
    for f in fact_list:
        cur = merged.get(f.key)
        if cur is None:
            merged[f.key] = f
            continue
        if cur.value == f.value:
            if cur.source == ASSERTED and f.source == VERIFIED:
                merged[f.key] = f
            continue
        if cur.source == VERIFIED and f.source == ASSERTED:
            notes.append("%s：已忽略低可信值 %s（保留 verified=%s）"
                         % (f.key, f.value, cur.value))
            continue
        if cur.source == ASSERTED and f.source == VERIFIED:
            notes.append("%s：verified=%s 覆盖 asserted=%s" % (f.key, f.value, cur.value))
            merged[f.key] = f
            continue
        notes.append("%s：同级事实冲突（%s vs %s），判定为 unknown"
                     % (f.key, cur.value, f.value))
        merged[f.key] = Fact(f.key, CONFLICT, ASSERTED)
    return merged, notes


def parse_predicates(value):
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


def verdict(entry_fm, facts):
    """返回 (verdict, basis, reasons)。basis ∈ verified/asserted/unknown。

    basis 表示“该结论依赖的最高来源”：applicable 依赖所满足前提的最弱来源；
    inapplicable 依赖触发矛盾的事实来源。
    """
    requires, bad_r = parse_predicates(entry_fm.get("requires"))
    excludes, bad_e = parse_predicates(entry_fm.get("excludes"))
    if bad_r or bad_e:
        return UNKNOWN, UNKNOWN, ["条件语法无法解析：%s" % ", ".join(bad_r + bad_e)]

    # 1) excludes：命中即不适用（反向判断：只有“成立”才触发，缺失/不成立都不触发）
    for key, want in excludes:
        val, src = resolve(key, facts)
        if val is None:
            continue
        if val == want:
            return INAPPLICABLE, src, ["命中排除条件 %s=%s（%s）" % (key, val, src)]

    # 2) requires：矛盾即不适用；未声明 → unknown；已满足 → 记录最弱来源
    unknown, weakest = [], VERIFIED
    for key, want in requires:
        val, src = resolve(key, facts)
        if val is None:
            unknown.append("%s 未成立（%s，要求 %s）" % (key, src, want))
            weakest = ASSERTED if src == ASSERTED else weakest
            continue
        if val != want:
            return INAPPLICABLE, src, ["%s=%s 与要求 %s 矛盾（%s）" % (key, val, want, src)]
        if src == ASSERTED:
            weakest = ASSERTED

    if unknown:
        return UNKNOWN, UNKNOWN, unknown
    if not requires and not excludes:
        return APPLICABLE, VERIFIED, ["条目未声明适用条件（无约束）"]
    return APPLICABLE, weakest, ["全部前提满足（最弱来源=%s）" % weakest]


def delivery(verdict_value, basis):
    """三值 + 来源 → 交付类别。只做减法：不会把 abstain 变成交付。

    Phase 4 修正：**任何**不适用（无论 verified 还是 asserted）都不再降级为
    诊断提示。理由：调用方自述的前提矛盾，本身不构成有用的鉴别线索，
    把它当提示只会制造噪音（实测 2/3 噪音）。矛盾细节留给 explain 展示。
    """
    if verdict_value == INAPPLICABLE:
        return ABSTAIN
    if verdict_value == APPLICABLE and basis == VERIFIED:
        return ACTIONABLE
    return DIAGNOSTIC_ONLY

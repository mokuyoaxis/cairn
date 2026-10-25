#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trust boundary for verified facts (research; core untouched).

Only functions registered in OBSERVERS may mint `verified` facts. Everything a
caller passes in is forced to `asserted`, whatever it claims about itself.

Design rules encoded here:

  * verified is a property of *who observed it and how*, not a string a caller
    can set; a claimed source is stripped, never trusted
  * each fact records the provider that produced it, so it is auditable
  * observations are bound to a request; nothing is cached across requests
  * an observer that raises yields *no* fact (unknown), never a default value
  * only whitelisted keys are accepted (see fact_context.KEYS)

No signatures, no identity service: the boundary is "the process observed it".
"""
import sys
import time

import fact_context as fc

_EPOCH = time.time()


def observe_os(_request=None):
    """真实观测：Cairn 自己运行在哪类操作系统上。"""
    plat = sys.platform
    if plat.startswith("linux"):
        return "os", "linux"
    if plat == "darwin":
        return "os", "macos"
    if plat.startswith("win"):
        return "os", "windows"
    return None


def observe_python(_request=None):
    v = "%d.%d" % (sys.version_info[0], sys.version_info[1])
    return "python_version", v


# 只允许这些提供者签发 verified；键名即审计来源
OBSERVERS = {
    "process.os": observe_os,
}


class RequestFacts(object):
    """一次请求内的事实集合。不外泄、不缓存。"""

    __slots__ = ("facts", "problems", "provenance", "created")

    def __init__(self):
        self.facts = {}
        self.problems = []
        self.provenance = {}
        self.created = time.time()

    def __repr__(self):
        return "RequestFacts(%s)" % ", ".join(
            "%s=%s(%s)" % (k, v.value, self.provenance.get(k, "?"))
            for k, v in sorted(self.facts.items()))


def issue(request=None, observers=None):
    """运行已注册观测器，签发 verified 事实。观测器异常 → 该键缺失。"""
    rf = RequestFacts()
    # 显式传 {} 表示“不做任何观测”；只有 None 才用默认观测器（避免静默回退）
    chosen = OBSERVERS if observers is None else observers
    for name, fn in sorted(chosen.items()):
        try:
            got = fn(request)
        except Exception as exc:                 # 观测失败 = 不知道，不是默认值
            rf.problems.append("%s: observation failed (%s)" % (name, type(exc).__name__))
            continue
        if not got:
            rf.problems.append("%s: nothing observed" % name)
            continue
        key, value = got
        spec = fc.KEYS.get(key)
        if spec is None:
            rf.problems.append("%s: key not whitelisted (%s)" % (name, key))
            continue
        norm = fc._norm_value(spec, str(value))
        if norm is None:
            rf.problems.append("%s: value rejected (%s=%r)" % (name, key, value))
            continue
        rf.facts[key] = fc.Fact(key, norm, fc.VERIFIED, age=0)
        rf.provenance[key] = name
    return rf


def accept_caller(raw_items, request_facts):
    """接受调用方事实，但一律降级为 asserted，且不覆盖 verified。"""
    parsed, problems = fc.parse_facts(raw_items or [])
    request_facts.problems.extend(problems)
    for fact in parsed:
        fact.source = fc.ASSERTED                # 声称什么都不算
        fact.age = 0
        cur = request_facts.facts.get(fact.key)
        if cur is None:
            request_facts.facts[fact.key] = fact
            request_facts.provenance[fact.key] = "caller"
            continue
        if cur.source == fc.VERIFIED:
            if cur.value != fact.value:
                request_facts.problems.append(
                    "%s: caller value %r ignored (verified=%r)"
                    % (fact.key, fact.value, cur.value))
            continue
        if cur.value != fact.value:
            request_facts.facts[fact.key] = fc.Fact(fact.key, fc.CONFLICT, fc.ASSERTED, 0)
            request_facts.problems.append("%s: same-level conflict -> unknown" % fact.key)
    return request_facts


def veto_attempts(raw_items, request_facts):
    """列出调用方试图改写 verified 的行为（审计/测试用）。"""
    out = []
    parsed, _ = fc.parse_facts(raw_items or [])
    for fact in parsed:
        cur = request_facts.facts.get(fact.key)
        if cur is not None and cur.source == fc.VERIFIED and cur.value != fact.value:
            out.append((fact.key, fact.value, cur.value))
    return out

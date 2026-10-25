# -*- coding: utf-8 -*-
"""Phase 3: typed fact contract + delivery ordering invariants (research only)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO

sys.path.insert(0, str(REPO / "eval"))
import fact_context as fc  # noqa: E402
import cairn  # noqa: E402
import taxonomy_ab as ab  # noqa: E402
import taxonomy_phase3 as p3  # noqa: E402


FM = {"requires": "journal_mode=wal; checkpointed=false", "excludes": "checkpointed=true"}


class TestTypedFacts(unittest.TestCase):
    def test_unknown_key_is_rejected(self):
        facts, problems = fc.parse_facts(["secret_key=1"])
        self.assertEqual(facts, [])
        self.assertTrue(any("白名单" in p for p in problems))

    def test_invalid_enum_value_is_rejected(self):
        facts, problems = fc.parse_facts(["journal_mode=banana"])
        self.assertEqual(facts, [])
        self.assertTrue(any("类型" in p for p in problems))

    def test_bool_normalisation(self):
        facts, _ = fc.parse_facts(["checkpointed=YES"])
        self.assertEqual(facts[0].value, "true")

    def test_source_flag_defaults_to_asserted(self):
        facts, _ = fc.parse_facts(["shell=bash"])
        self.assertEqual(facts[0].source, fc.ASSERTED)

    def test_verified_flag(self):
        facts, _ = fc.parse_facts(["shell=bash@verified"])
        self.assertEqual(facts[0].source, fc.VERIFIED)

    def test_age_flag(self):
        facts, _ = fc.parse_facts(["checkpointed=true@verified@age=7200"])
        self.assertEqual(facts[0].age, 7200)

    def test_expression_is_not_executed(self):
        facts, problems = fc.parse_facts(["checkpointed=$(rm -rf /)"])
        self.assertEqual(facts, [])
        self.assertTrue(problems)


class TestTrustAndConflicts(unittest.TestCase):
    def test_same_level_conflict_is_unknown(self):
        facts, _, notes = fc.facts_from(["checkpointed=true", "checkpointed=false"])
        v, basis, why = fc.verdict(FM, facts)
        self.assertEqual(v, fc.UNKNOWN)
        self.assertTrue(any("冲突" in n for n in notes))

    def test_verified_beats_asserted_regardless_of_order(self):
        for items in (["checkpointed=true@verified", "checkpointed=false@asserted"],
                      ["checkpointed=false@asserted", "checkpointed=true@verified"]):
            facts, _, _ = fc.facts_from(items)
            self.assertEqual(facts["checkpointed"].value, "true")
            self.assertEqual(facts["checkpointed"].source, fc.VERIFIED)

    def test_asserted_never_overrides_verified(self):
        facts, _, notes = fc.facts_from(["checkpointed=false@verified", "checkpointed=true@asserted"])
        self.assertEqual(facts["checkpointed"].value, "false")
        self.assertTrue(notes)

    def test_stale_fact_is_treated_as_missing(self):
        facts, _, _ = fc.facts_from(["checkpointed=false@verified@age=99999"])
        v, _, _ = fc.verdict(FM, facts)
        self.assertEqual(v, fc.UNKNOWN)


class TestVerdictSemantics(unittest.TestCase):
    def test_no_constraints_is_applicable(self):
        v, basis, _ = fc.verdict({}, {})
        self.assertEqual((v, basis), (fc.APPLICABLE, fc.VERIFIED))

    def test_verified_satisfaction_is_applicable_verified(self):
        facts, _, _ = fc.facts_from(["journal_mode=wal@verified", "checkpointed=false@verified"])
        self.assertEqual(fc.verdict(FM, facts)[:2], (fc.APPLICABLE, fc.VERIFIED))

    def test_asserted_satisfaction_is_applicable_but_asserted(self):
        facts, _, _ = fc.facts_from(["journal_mode=wal", "checkpointed=false"])
        self.assertEqual(fc.verdict(FM, facts)[:2], (fc.APPLICABLE, fc.ASSERTED))

    def test_verified_contradiction_is_inapplicable(self):
        facts, _, _ = fc.facts_from(["journal_mode=wal@verified", "checkpointed=true@verified"])
        v, basis, _ = fc.verdict(FM, facts)
        self.assertEqual((v, basis), (fc.INAPPLICABLE, fc.VERIFIED))

    def test_asserted_contradiction_is_inapplicable_but_asserted(self):
        facts, _, _ = fc.facts_from(["checkpointed=true@asserted"])
        v, basis, _ = fc.verdict(FM, facts)
        self.assertEqual((v, basis), (fc.INAPPLICABLE, fc.ASSERTED))

    def test_missing_premise_is_unknown_not_false(self):
        facts, _, _ = fc.facts_from(["journal_mode=wal@verified"])
        self.assertEqual(fc.verdict(FM, facts)[0], fc.UNKNOWN)

    def test_exclusion_does_not_trigger_when_undeclared(self):
        facts, _, _ = fc.facts_from(["journal_mode=wal@verified", "checkpointed=false@verified"])
        self.assertEqual(fc.verdict(FM, facts)[0], fc.APPLICABLE)

    def test_no_query_parameter_on_verdict(self):
        import inspect
        self.assertEqual(list(inspect.signature(fc.verdict).parameters), ["entry_fm", "facts"])


class TestDeliveryPolicy(unittest.TestCase):
    def test_verified_applicable_is_actionable(self):
        self.assertEqual(fc.delivery(fc.APPLICABLE, fc.VERIFIED), fc.ACTIONABLE)

    def test_asserted_applicable_is_diagnostic_only(self):
        self.assertEqual(fc.delivery(fc.APPLICABLE, fc.ASSERTED), fc.DIAGNOSTIC_ONLY)

    def test_verified_inapplicable_abstains(self):
        self.assertEqual(fc.delivery(fc.INAPPLICABLE, fc.VERIFIED), fc.ABSTAIN)

    def test_any_inapplicable_abstains_phase4_refinement(self):
        # Phase 4：把“自述矛盾 → 诊断提示”改成“一律不交付”。
        # 原因：实验显示自述矛盾当提示会产生 2/3 噪音（见 phase4_diagnostic.py），
        # 且矛盾细节已由 explain 呈现。这是有意的基线变更。
        self.assertEqual(fc.delivery(fc.INAPPLICABLE, fc.ASSERTED), fc.ABSTAIN)
        self.assertEqual(fc.delivery(fc.INAPPLICABLE, fc.VERIFIED), fc.ABSTAIN)

    def test_unknown_is_diagnostic(self):
        self.assertEqual(fc.delivery(fc.UNKNOWN, fc.UNKNOWN), fc.DIAGNOSTIC_ONLY)

    def test_never_escalates_to_actionable(self):
        for v in (fc.APPLICABLE, fc.INAPPLICABLE, fc.UNKNOWN):
            for b in (fc.VERIFIED, fc.ASSERTED, fc.UNKNOWN):
                if not (v == fc.APPLICABLE and b == fc.VERIFIED):
                    self.assertNotEqual(fc.delivery(v, b), fc.ACTIONABLE)


class TestOrderingInvariants(unittest.TestCase):
    """冻结设计上的回归护栏：先过滤后 margin 不得更差。"""

    @classmethod
    def setUpClass(cls):
        cls.homes = []
        cls.entries = ab.load_corpus()
        cls.cases = [json.loads(l) for l in
                     (REPO / "eval" / "taxonomy" / "cases_phase3.jsonl")
                     .read_text(encoding="utf-8").splitlines() if l.strip()]
        cls.by_id = {c["id"]: c for c in cls.cases}
        cls.idx = p3.build_index(cls.entries, cls.homes)
        cls.rows = {}
        for scheme in ("S1", "S2"):
            cls.rows[scheme] = [p3.run_case(cls.idx, cls.entries, c, scheme, 1.5)
                                for c in cls.cases]
        cls.metrics = {k: p3.metrics(v, cls.by_id) for k, v in cls.rows.items()}

    @classmethod
    def tearDownClass(cls):
        for h in cls.homes:
            shutil.rmtree(h, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)
        cairn._INDEX = None

    def test_recall_is_identical_across_orders(self):
        self.assertEqual(self.metrics["S1"]["recall_ok"], self.metrics["S2"]["recall_ok"],
                         "顺序不应改变召回：安全不能靠搜不到换来")

    def test_applicability_first_recovers_actionable_delivery(self):
        self.assertGreater(self.metrics["S2"]["actionable_ok"],
                           self.metrics["S1"]["actionable_ok"])

    def test_no_extra_wrong_actionable_delivery(self):
        self.assertLessEqual(self.metrics["S2"]["forbid_actionable_leak"],
                             self.metrics["S1"]["forbid_actionable_leak"])

    def test_context_isolation_between_requests(self):
        a = next(r for r in self.rows["S2"] if r["id"] == "h19")
        b = next(r for r in self.rows["S2"] if r["id"] == "h20")
        self.assertEqual(a["query"], b["query"])
        self.assertNotEqual(a["delivered"], b["delivered"],
                            "同一查询不同事实必须得到不同判定（缓存不得污染）")

    def test_core_gate_is_mirrored(self):
        # S1 在 margin 默认值下应与核心 gate 完全一致（镜像未被改坏）
        for c in self.cases:
            q = c["query"]
            res = self.idx.search(q, limit=p3.POOLS["S1"])
            core = [h[4]["name"] for h in cairn.gate(res, q_len=len(cairn.tokenize(q)))]
            mine = [h[4]["name"] for h in p3.mirrors_core_gate(
                res, cairn.DEFAULT_MIN_MARGIN, len(cairn.tokenize(q)))]
            self.assertEqual(core, mine, c["id"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Taxonomy v2 schema checker tests (standalone; core untouched)."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO

sys.path.insert(0, str(REPO / "eval"))
import schema_check  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.entries = self.tmp / "entries"
        self.cands = self.tmp / "candidates"
        self.entries.mkdir()
        self.cands.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entry(self, slug, **fm):
        base = {"name": slug, "summary": "一句可证伪结论", "role": "mechanism",
                "state": "supported", "scope": "docker", "updated": "2026-10-25",
                "status": "active", "trust": "verified", "verified_at": "2026-10-25",
                "symptoms": "命令无输出", "signs": "退出码 124",
                "evidence": "2026-10-25 bash 5.2.21 复现", "applies_when": "脚本含后台作业"}
        base.update({k: v for k, v in fm.items() if v is not None})
        for k, v in fm.items():
            if v is None:
                base.pop(k, None)
        text = "---\n" + "\n".join("%s: %s" % (k, v) for k, v in base.items() if v != "")
        text += "\n---\n\n正文\n"
        (self.entries / (slug + ".md")).write_text(text, encoding="utf-8")
        return slug

    def sidecar(self, slug, cands, ruled_out=None):
        (self.cands / (slug + ".json")).write_text(
            json.dumps({"slug": slug, "candidates": cands,
                        "ruled_out": ruled_out or []}, ensure_ascii=False), encoding="utf-8")

    def cand(self, **over):
        c = {"cause": "候选原因", "check": "执行某项检查",
             "if_positive": "返回 127", "if_negative": "返回 0",
             "limits": "仅同一 shell", "verified": True}
        c.update(over)
        return c

    def codes(self, zone="library"):
        per, conflicts, _ = schema_check.scan(self.entries, zone=zone,
                                             sidecar_dir=self.cands)
        out = []
        for slug, items in per:
            for level, code, msg in items:
                out.append((level, code))
        for level, code, msg in conflicts:
            out.append((level, code))
        return out


class TestRoleAndStructure(Base):
    def test_missing_role_is_error_in_library(self):
        self.entry("a", role=None)
        self.assertIn(("error", "C1-rolemissing"), self.codes())

    def test_missing_role_is_warn_in_research(self):
        self.entry("a", role=None)
        self.assertIn(("warn", "C1-rolemissing"), self.codes("research"))

    def test_invalid_role(self):
        self.entry("a", role="lesson")
        self.assertIn(("error", "C1-roleinvalid"), self.codes())

    def test_invalid_state(self):
        self.entry("a", state="verified")
        self.assertIn(("error", "C1-stateinvalid"), self.codes())

    def test_method_must_not_carry_candidates(self):
        self.entry("a", role="method", candidates="x")
        self.assertIn(("error", "C1-misclassified"), self.codes())

    def test_policy_requires_tradeoff(self):
        self.entry("a", role="policy", tradeoff=None, symptoms="偶发失败")
        self.assertIn(("error", "C1-notradeoff"), self.codes())

    def test_policy_with_tradeoff_ok(self):
        self.entry("a", role="policy", tradeoff="速度 vs 根因质量", symptoms="偶发失败")
        codes = [c for _, c in self.codes()]
        self.assertNotIn("C1-notradeoff", codes)


class TestScope(Base):
    def test_missing_scope(self):
        self.entry("a", scope=None)
        self.assertIn(("error", "C2-scope-missing"), self.codes())

    def test_vague_scope(self):
        self.entry("a", scope="all")
        self.assertIn(("warn", "C2-scope-vague"), self.codes())

    def test_too_many_tags(self):
        self.entry("a", scope="a, b, c, d")
        self.assertIn(("warn", "C2-scope-broad"), self.codes())


class TestEvidence(Base):
    def test_established_mechanism_without_evidence(self):
        self.entry("a", state="established", evidence=None)
        self.assertIn(("error", "C3-noevidence"), self.codes())

    def test_spurious_established_with_self_confessed_no_repro(self):
        self.entry("a", state="established", evidence="无独立复现：通用实践")
        self.assertIn(("error", "C3-selfcontradiction"), self.codes())

    def test_unreproduced_supported_method_is_review_only(self):
        self.entry("a", role="method", state="supported", evidence="无独立复现：通用实践")
        self.assertIn(("review", "C3b-unreproduced"), self.codes())

    def test_untraceable_evidence_warns(self):
        self.entry("a", evidence="大家都知道这样做")
        self.assertIn(("warn", "C3-untraceable"), self.codes())

    def test_fabrication_marker_is_error(self):
        self.entry("a", evidence="TODO 补一个复现记录 2026-10-25")
        self.assertIn(("error", "C8-fabrication"), self.codes())

    def test_future_date_is_error(self):
        self.entry("a", evidence="2099-01-01 测过一次 bash")
        self.assertIn(("error", "C8-futuredate"), self.codes())

    def test_speculation_needs_review(self):
        self.entry("a", evidence="2026-10-25 观察；【推测】与缓存有关")
        self.assertIn(("review", "C8-speculation"), self.codes())


class TestDiagnosticCase(Base):
    def test_missing_sidecar(self):
        self.entry("a", role="diagnostic_case")
        self.assertIn(("error", "C4-nosidecar"), self.codes())

    def test_single_candidate_is_error(self):
        self.entry("a", role="diagnostic_case")
        self.sidecar("a", [self.cand()])
        self.assertIn(("error", "C4-toofew"), self.codes())

    def test_candidate_without_negative_branch(self):
        self.entry("a", role="diagnostic_case")
        self.sidecar("a", [self.cand(), self.cand(if_negative="")])
        self.assertIn(("error", "C5-incomplete"), self.codes())

    def test_unverified_candidate_needs_review(self):
        self.entry("a", role="diagnostic_case")
        self.sidecar("a", [self.cand(), self.cand(verified=False)])
        self.assertIn(("review", "C5-unverified"), self.codes())

    def test_candidate_without_limits_warns(self):
        self.entry("a", role="diagnostic_case")
        self.sidecar("a", [self.cand(limits=""), self.cand()])
        self.assertIn(("warn", "C5-nolimits"), self.codes())

    def test_ruled_out_must_bind_case_and_date(self):
        self.entry("a", role="diagnostic_case")
        self.sidecar("a", [self.cand(), self.cand()],
                     ruled_out=[{"cause": "x", "case": "", "date": "", "conditions": ""}])
        self.assertIn(("error", "C5-ruledout"), self.codes())

    def test_wellformed_diagnostic_case_has_no_errors(self):
        self.entry("a", role="diagnostic_case")
        self.sidecar("a", [self.cand(), self.cand()])
        errors = [c for lvl, c in self.codes() if lvl == "error"]
        self.assertEqual(errors, [])


class TestStateConsistency(Base):
    def test_refuted_cannot_stay_active(self):
        self.entry("a", state="refuted", status="active")
        self.assertIn(("error", "C6-refuted-active"), self.codes())

    def test_refuted_with_deprecated_is_fine(self):
        self.entry("a", state="refuted", status="deprecated")
        self.assertNotIn("C6-refuted-active", [c for _, c in self.codes()])

    def test_established_without_signs_warns(self):
        self.entry("a", state="established", signs=None)
        self.assertIn(("warn", "C6-established-nosigns"), self.codes())


class TestRetiredV1Fields(Base):
    def test_discriminator_is_error(self):
        self.entry("a", discriminator="改用具体 PID 再看")
        self.assertIn(("error", "V1-discriminator"), self.codes())

    def test_workaround_is_warn(self):
        self.entry("a", workaround="先套 timeout")
        self.assertIn(("warn", "V1-workaround"), self.codes())

    def test_fails_when_is_warn(self):
        self.entry("a", fails_when="只有一个子进程时")
        self.assertIn(("warn", "V1-fails_when"), self.codes())


class TestConflicts(Base):
    def test_same_scope_overlapping_symptoms_conflict(self):
        self.entry("a", role="policy", tradeoff="快 vs 准", symptoms="CI 偶发失败; 重跑后通过",
                   summary="偶发失败先原样重跑")
        self.entry("b", role="policy", tradeoff="准 vs 快", symptoms="CI 偶发失败; 重跑后通过",
                   summary="偶发失败不要重跑")
        self.assertIn(("warn", "C7-overlap"), self.codes())

    def test_refuted_overlap_is_review_not_conflict(self):
        self.entry("a", role="mechanism", symptoms="拷贝后数据不见了", summary="WAL 未 checkpoint 导致")
        self.entry("b", role="mechanism", state="refuted", status="deprecated",
                   symptoms="拷贝后数据不见了", summary="删掉 wal 即可")
        self.assertIn(("review", "C7-superseded"), self.codes())


class TestMain(Base):
    def test_main_exit_code_error(self):
        self.entry("a", scope=None)
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = schema_check.main([str(self.entries), "--candidates", str(self.cands)])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 1)

    def test_main_json_output(self):
        self.entry("a")
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = schema_check.main([str(self.entries), "--candidates", str(self.cands), "--json"])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        self.assertIn('"entries": 1', buf.getvalue())

    def test_missing_dir_returns_2(self):
        self.assertEqual(schema_check.main([str(self.tmp / "nope")]), 2)


if __name__ == "__main__":
    unittest.main()

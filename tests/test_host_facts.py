# -*- coding: utf-8 -*-
"""Phase 4: host fact trust boundary, forgery, isolation, legacy compatibility."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO

sys.path.insert(0, str(REPO / "eval"))
import cairn  # noqa: E402
import fact_context as fc  # noqa: E402
import host_facts as hf  # noqa: E402


class TestIssuance(unittest.TestCase):
    def test_observer_mints_verified_with_provenance(self):
        rf = hf.issue(observers={"process.os": lambda _r=None: ("os", "linux")})
        self.assertEqual(rf.facts["os"].source, fc.VERIFIED)
        self.assertEqual(rf.provenance["os"], "process.os")

    def test_observer_exception_yields_no_fact(self):
        def boom(_r=None):
            raise RuntimeError("nope")
        rf = hf.issue(observers={"process.os": boom})
        self.assertNotIn("os", rf.facts)
        self.assertTrue(any("failed" in p for p in rf.problems))

    def test_observer_returning_none_yields_no_fact(self):
        rf = hf.issue(observers={"process.os": lambda _r=None: None})
        self.assertNotIn("os", rf.facts)

    def test_observer_non_whitelisted_key_rejected(self):
        rf = hf.issue(observers={"x": lambda _r=None: ("secret_key", "1")})
        self.assertEqual(rf.facts, {})
        self.assertTrue(any("whitelist" in p for p in rf.problems))

    def test_observer_invalid_value_rejected(self):
        rf = hf.issue(observers={"x": lambda _r=None: ("os", "plan9")})
        self.assertEqual(rf.facts, {})


class TestForgery(unittest.TestCase):
    def test_caller_cannot_claim_verified(self):
        rf = hf.issue(observers={"process.os": lambda _r=None: ("os", "linux")})
        hf.accept_caller(["checkpointed=false@verified"], rf)
        self.assertEqual(rf.facts["checkpointed"].source, fc.ASSERTED)
        self.assertEqual(rf.provenance["checkpointed"], "caller")

    def test_caller_cannot_override_verified_value(self):
        rf = hf.issue(observers={"process.os": lambda _r=None: ("os", "linux")})
        hf.accept_caller(["os=windows@verified"], rf)
        self.assertEqual(rf.facts["os"].value, "linux")
        self.assertEqual(rf.facts["os"].source, fc.VERIFIED)
        self.assertEqual(hf.veto_attempts(["os=windows@verified"], rf),
                         [("os", "windows", "linux")])

    def test_json_injection_is_not_special(self):
        # 即使调用方塞进来带 source 字段的字符串，也只会变成 asserted
        rf = hf.issue(observers={})
        hf.accept_caller(['{"key":"checkpointed","value":"false","source":"verified"}'], rf)
        self.assertEqual(rf.facts, {})          # 非 key=value 语法，直接丢弃
        self.assertTrue(rf.problems)

    def test_same_level_conflict_becomes_unknown(self):
        rf = hf.issue(observers={})
        hf.accept_caller(["checkpointed=true", "checkpointed=false"], rf)
        self.assertEqual(rf.facts["checkpointed"].value, fc.CONFLICT)
        self.assertEqual(fc.verdict({"requires": "checkpointed=true"}, rf.facts)[0],
                         fc.UNKNOWN)

    def test_caller_assertion_cannot_upgrade_to_actionable(self):
        rf = hf.issue(observers={"process.os": lambda _r=None: ("os", "linux")})
        hf.accept_caller(["os=linux"], rf)      # 与 verified 一致，但仍是 verified 生效
        v, basis, _ = fc.verdict({"requires": "os=linux"}, rf.facts)
        self.assertEqual((v, basis), (fc.APPLICABLE, fc.VERIFIED))


class TestIsolation(unittest.TestCase):
    def test_facts_do_not_leak_between_requests(self):
        a = hf.issue(observers={"process.os": lambda _r=None: ("os", "windows")})
        hf.accept_caller(["checkpointed=false"], a)
        b = hf.issue(observers={"process.os": lambda _r=None: ("os", "linux")})
        self.assertNotIn("checkpointed", b.facts, "上一请求的调用方事实不得复用")
        self.assertEqual(b.facts["os"].value, "linux")

    def test_verdict_differs_across_requests(self):
        fm = {"requires": "os=linux"}
        a = hf.issue(observers={"process.os": lambda _r=None: ("os", "windows")})
        b = hf.issue(observers={"process.os": lambda _r=None: ("os", "linux")})
        self.assertEqual(fc.verdict(fm, a.facts)[0], fc.INAPPLICABLE)
        self.assertEqual(fc.verdict(fm, b.facts)[0], fc.APPLICABLE)


class TestLegacyCompatibility(unittest.TestCase):
    def test_entry_without_constraints_is_applicable_without_facts(self):
        v, basis, _ = fc.verdict({}, {})
        self.assertEqual((v, basis), (fc.APPLICABLE, fc.VERIFIED))
        self.assertEqual(fc.delivery(v, basis), fc.ACTIONABLE)

    def test_core_delivery_unchanged_for_legacy_entries(self):
        """真实核心：无 requires/excludes 的条目在空事实下仍照旧交付。"""
        home = Path(tempfile.mkdtemp())
        os.environ["CAIRN_HOME"] = str(home)
        (home / "entries").mkdir()
        try:
            text = ("---\nname: legacy-one\nsummary: docker compose config 打印密钥\n"
                    "kind: lesson\nupdated: 2026-10-25\nstatus: active\ntrust: verified\n"
                    "verified_at: 2026-10-25\nsource: test\n---\n\n正文\n")
            (home / "entries" / "legacy-one.md").write_text(text, encoding="utf-8")
            cairn._INDEX = None
            idx = cairn.get_index(force=True)
            res = idx.search("docker compose config 打印密钥", limit=5)
            hits = cairn.gate(res, q_len=len(cairn.tokenize("docker compose config 打印密钥")))
            self.assertEqual([h[4]["name"] for h in hits], ["legacy-one"])
        finally:
            shutil.rmtree(home, ignore_errors=True)
            os.environ.pop("CAIRN_HOME", None)
            cairn._INDEX = None


class TestDiagnosticLaneContract(unittest.TestCase):
    """诊断提示只能是提示：不得变成可执行建议。"""

    def test_inapplicable_never_yields_hint(self):
        facts, _p, _n = fc.facts_from(["os=linux@verified"])
        v, basis, _ = fc.verdict({"excludes": "os=linux"}, facts)
        self.assertEqual(fc.delivery(v, basis), fc.ABSTAIN)

    def test_unknown_yields_diagnostic_not_actionable(self):
        v, basis, _ = fc.verdict({"requires": "shell=bash"}, {})
        self.assertEqual(fc.delivery(v, basis), fc.DIAGNOSTIC_ONLY)


if __name__ == "__main__":
    unittest.main()

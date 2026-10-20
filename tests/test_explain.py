# -*- coding: utf-8 -*-
import io
import sys

from support import Base, cairn


class TestExplain(Base):
    def _run(self, argv):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(), io.StringIO()
        try:
            rc = cairn.main(argv)
            return rc, sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out

    def test_reports_inject_and_score(self):
        self.write("demo-entry", summary="alpha beta gamma")
        rc, out = self._run(["explain", "alpha beta gamma"])
        self.assertEqual(rc, 0)
        self.assertIn("[INJECT] demo-entry", out)
        self.assertIn("norm=", out)
        self.assertIn("cover=3/3", out)
        self.assertNotIn("[SILENT]", out)

    def test_reports_contract_ineligible(self):
        self.write("unverified-entry", summary="alpha beta", trust="unverified")
        rc, out = self._run(["explain", "alpha beta"])
        self.assertEqual(rc, 1)
        self.assertIn("[ineligible] unverified-entry", out)
        self.assertIn("trust=unverified", out)
        self.assertIn("[SILENT]", out)

    def test_reports_deprecated_status(self):
        self.write("old-entry", summary="alpha beta", status="deprecated")
        rc, out = self._run(["explain", "alpha beta"])
        self.assertEqual(rc, 1)
        self.assertIn("status=deprecated", out)

    def test_reports_missing_evidence(self):
        self.write("no-source", summary="alpha beta", source=None)
        self.write("no-date", summary="alpha beta", verified_at=None)
        rc, out = self._run(["explain", "alpha beta"])
        self.assertEqual(rc, 1)
        self.assertIn("缺 source", out)
        self.assertIn("verified_at 无效", out)

    def test_reports_low_coverage(self):
        self.write("demo-entry", summary="alpha beta")
        rc, out = self._run(["explain", "alpha beta zzz", "--min-cover", "0.99"])
        self.assertEqual(rc, 1)
        self.assertIn("[low_cover] demo-entry", out)
        self.assertIn("[SILENT]", out)

    def test_reports_low_margin(self):
        self.write("a-entry", summary="alpha beta gamma delta")
        self.write("b-entry", summary="alpha beta gamma")
        rc, out = self._run(["explain", "alpha beta gamma delta", "--min-margin", "99"])
        self.assertEqual(rc, 1)
        self.assertEqual(out.count("[low_margin]"), 2)
        self.assertIn("[SILENT]", out)

    def test_reports_over_limit(self):
        self.write("a-entry", summary="alpha beta gamma delta")
        self.write("b-entry", summary="alpha beta gamma")
        rc, out = self._run(["explain", "alpha beta gamma delta", "--limit", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("[INJECT] a-entry", out)
        self.assertIn("[over_limit] b-entry", out)

    def test_silent_without_candidates(self):
        self.write("demo-entry", summary="alpha beta")
        rc, out = self._run(["explain", "zzzzzz"])
        self.assertEqual(rc, 1)
        self.assertIn("候选 0 条", out)
        self.assertIn("[SILENT]", out)

    def test_matches_recall_hits(self):
        self.write("a-entry", summary="alpha beta gamma delta")
        self.write("b-entry", summary="alpha beta gamma")
        rrc, rout = self._run(["recall", "alpha beta gamma delta"])
        erc, eout = self._run(["explain", "alpha beta gamma delta"])
        self.assertEqual(erc, rrc)
        for line in rout.splitlines():
            if line.startswith("- "):
                name = line[2:].split("：", 1)[0]
                self.assertIn(f"[INJECT] {name}", eout)

    def test_is_read_only(self):
        self.write("demo-entry", summary="alpha beta")
        before = (self.home / "entries" / "demo-entry.md").read_text(encoding="utf-8")
        rc, _ = self._run(["explain", "alpha beta"])
        self.assertEqual(rc, 0)
        after = (self.home / "entries" / "demo-entry.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertFalse((self.home / "log").exists())

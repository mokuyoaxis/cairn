# -*- coding: utf-8 -*-
import io
import json
import re
import subprocess
import sys
import unittest

from support import Base, REPO, cairn


class TestEvalGate(Base):
    def test_eval_fails_on_empty_library(self):
        q = self.home / "q.jsonl"
        q.write_text(json.dumps({"query": "docker compose", "expect": ["x"]}) + "\n",
                     encoding="utf-8")
        rc = cairn.main(["eval", "--queries", str(q), "--negatives", str(self.home / "n")])
        self.assertEqual(rc, 1)

    def test_eval_passes_min_margin_to_gate(self):
        self.write("entry-a", summary="alpha beta gamma delta")
        self.write("entry-b", summary="alpha beta")
        q = self.home / "margin.jsonl"
        q.write_text(json.dumps({"query": "alpha beta gamma delta",
                                 "expect": ["entry-a"]}) + "\n", encoding="utf-8")
        base = ["eval", "--queries", str(q), "--negatives", str(self.home / "n")]
        self.assertEqual(cairn.main(base), 0)
        self.assertEqual(cairn.main(base + ["--min-margin", "99"]), 1)

    def test_eval_average_injection_counts_no_hit_as_zero(self):
        self.write("hit", summary="alpha beta gamma")
        q = self.home / "avg.jsonl"
        q.write_text("\n".join(json.dumps(r) for r in (
            {"query": "alpha beta gamma", "expect": ["hit"]},
            {"query": "zzz yyy xxx", "expect": ["missing"]})) + "\n", encoding="utf-8")
        old_out, old_in = sys.stdout, sys.stdin
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["eval", "--queries", str(q), "--negatives",
                             str(self.home / "n"), "--min-inject", "0.4"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertEqual(rc, 0)
        per_query = re.search(r"平均注入 (\d+) 字符", out)
        per_inject = re.search(r"实际注入 1/2 次：平均 (\d+) 字符", out)
        self.assertIsNotNone(per_query)
        self.assertIsNotNone(per_inject)
        self.assertLessEqual(
            abs(int(per_query.group(1)) * 2 - int(per_inject.group(1))), 2)

    def test_eval_missing_queries_returns_2(self):
        self.assertEqual(cairn.main(["eval", "--queries",
                                     str(self.home / "missing.jsonl")]), 2)


class TestTrustEval(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO / "eval" / "trust_eval.py"), *args],
            cwd=str(REPO), capture_output=True, text=True, timeout=60)

    def test_trust_eval_passes_hard_constraints(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("hard failures 0", r.stdout)
        self.assertIn("known gaps 4", r.stdout)
        self.assertIn("body_leak=False", r.stdout)
        self.assertIn("2/2 100%", r.stdout)
        self.assertIn("3/3 100%", r.stdout)

    def test_trust_eval_strict_fails_known_gaps(self):
        r = self._run("--strict")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("[STRICT] stale-retry", r.stdout)
        self.assertIn("[STRICT] conflict-pair", r.stdout)


if __name__ == "__main__":
    unittest.main()

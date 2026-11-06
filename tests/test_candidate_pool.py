# -*- coding: utf-8 -*-
"""Regression tests for candidate admission before the candidate limit."""
import io
import json
import sys
import unittest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import Base, cairn


class TestCandidatePool(Base):
    def _write_peers(self, count=20, **overrides):
        for i in range(count):
            self.write(
                "a-peer-%02d" % i,
                summary="retry policy",
                body="retry policy",
                **overrides,
            )
        self.write("z-target-99", summary="retry policy", body="retry policy")
        cairn._INDEX = None

    def _run_hook(self, *extra):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(json.dumps(
            {"prompt": "retry policy", "session_id": "candidate-pool"},
            ensure_ascii=False,
        ))
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["hook", "--format", "text", *extra])
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        return rc, out

    def test_ineligible_peers_do_not_starve_hook_target(self):
        self._write_peers(trust="unverified", source="", verified_at="")
        rc, out = self._run_hook()
        self.assertEqual(rc, 0)
        self.assertIn("z-target-99", out)
        self.assertNotIn("a-peer-", out)

    def test_scope_mismatch_peers_do_not_starve_hook_target(self):
        self._write_peers(scope="worker")
        target = self.home / "entries" / "z-target-99.md"
        target.write_text(
            target.read_text(encoding="utf-8").replace("scope: git", "scope: client"),
            encoding="utf-8",
        )
        cairn._INDEX = None
        rc, out = self._run_hook("--scope", "client")
        self.assertEqual(rc, 0)
        self.assertIn("z-target-99", out)
        self.assertNotIn("a-peer-", out)

    def test_explain_reports_starved_target(self):
        self._write_peers(trust="unverified", source="", verified_at="")
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["explain", "retry policy"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertEqual(rc, 0)
        self.assertIn("[INJECT] z-target-99", out)

    def test_recall_reports_starved_target(self):
        self._write_peers(trust="unverified", source="", verified_at="")
        rc, out = self._run_recall()
        self.assertEqual(rc, 0)
        self.assertIn("z-target-99", out)

    def _run_recall(self):
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["recall", "retry policy"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        return rc, out


if __name__ == "__main__":
    unittest.main()

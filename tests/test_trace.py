# -*- coding: utf-8 -*-
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch

from support import Base, cairn


class TestTrace(Base):
    def run_trace(self, query, *flags):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = cairn.main(["trace", query, *flags])
        return rc, stdout.getvalue()

    def report(self, query, *flags):
        rc, out = self.run_trace(query, "--json", *flags)
        return rc, json.loads(out)


    def test_human_output_includes_retrieval_and_delivery(self):
        self.write("good", summary="amber cedar")
        rc, out = self.run_trace("amber cedar")
        self.assertEqual(rc, 0)
        self.assertIn("[retrieve] complete", out)
        self.assertIn("good: retrieved", out)
        self.assertIn("[host_receipt] unknown", out)
        self.assertIn("would_emit: true", out)
        self.assertIn("entries/good.md", out)

    def test_hook_payload_parity_and_read_only_session(self):
        self.write("good", summary="amber cedar")
        self.write("blocked", summary="amber cedar", trust="quarantined")
        rc, before = self.report("amber cedar", "--session-id", "trace", "--payload")
        self.assertEqual(rc, 0)
        self.assertEqual([s["stage"] for s in before["stages"]],
                         ["retrieve", "admit", "gate", "dedupe", "render", "host_receipt"])
        self.assertEqual(before["final"]["delivered"], ["good"])
        self.assertEqual(before["final"]["host_receipt"], "not_observed")
        self.assertFalse((self.home / "log").exists())
        self.assertNotIn("query", before)
        self.assertNotIn("session_id", before["session"])
        self.assertIn("entries/good.md", before["final"]["card_text"])

        with patch("sys.stdin", io.StringIO(json.dumps({"prompt": "amber cedar", "session_id": "trace"}))), \
                redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(cairn.main(["hook", "--format", "claude"]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), before["final"]["payload"])
        self.assertEqual(cairn._load_seen("trace"), {"good"})
        rc, after = self.report("amber cedar", "--session-id", "trace")
        self.assertEqual(rc, 1)
        self.assertFalse(after["final"]["would_emit"])
        self.assertEqual(after["stages"][3]["cards"][0]["reason"], "already_delivered")

    def test_budget_omission_is_not_delivery(self):
        self.write("budget-lead", summary="amber cedar quartz " * 8 + "x" * 280)
        self.write("gold", summary="amber cedar opal")
        rc, report = self.report("amber cedar quartz")
        self.assertEqual(rc, 0)
        self.assertEqual([c["reason"] for c in report["stages"][4]["cards"]],
                         ["rendered", "budget_omitted"])
        self.assertEqual(report["final"]["delivered"], ["budget-lead"])
        self.assertEqual(report["final"]["seen_after_successful_emit"], ["budget-lead"])

    def test_truncated_lead_is_rendered_not_omitted(self):
        self.write("lead", summary="amber " * 200)
        rc, report = self.report("amber")
        self.assertEqual(rc, 0)
        self.assertEqual(report["stages"][4]["cards"][0]["reason"], "truncated")
        self.assertIn("…（已截断）", report["final"]["card_text"])

    def test_gate_and_scope_reasons(self):
        self.write("good", summary="amber cedar", scope="frontend")
        rc, report = self.report("amber cedar", "--scope", "backend")
        self.assertEqual(rc, 1)
        self.assertEqual(report["stages"][1]["cards"][0]["reason"], "out_of_scope")
        self.write("a", summary="alpha beta gamma delta")
        self.write("b", summary="alpha beta gamma")
        rc, report = self.report("alpha beta gamma delta", "--min-margin", "99")
        self.assertEqual(rc, 1)
        self.assertTrue(all(c["reason"] == "low_margin" for c in report["stages"][2]["cards"]))

    def test_empty_query_and_no_lexical_match_are_silent(self):
        self.write("good", summary="amber cedar")
        for query, reason in (("   ", "empty_query"), ("unknown", "no_lexical_match")):
            with self.subTest(reason=reason):
                rc, report = self.report(query)
                self.assertEqual(rc, 1)
                self.assertFalse(report["final"]["would_emit"])
                self.assertEqual(report["stages"][0]["reason"], reason)

    def test_repeated_json_trace_does_not_consume_card(self):
        self.write("good", summary="amber cedar")
        first = self.report("amber cedar")
        second = self.report("amber cedar")
        self.assertEqual(first, second)
        self.assertFalse((self.home / "log").exists())

    def test_invalid_limit_is_not_a_success(self):
        rc, report = self.report("amber", "--limit", "0")
        self.assertEqual(rc, 1)
        self.assertEqual(report["stages"][0]["reason"], "invalid_card_limit")

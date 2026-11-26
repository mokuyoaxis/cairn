# -*- coding: utf-8 -*-
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch

from support import Base, cairn


class TestHookDelivery(Base):
    def hook(self, sid, prompt):
        payload = io.StringIO(json.dumps({"session_id": sid, "prompt": prompt}))
        with patch("sys.stdin", payload), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(cairn.main(["hook", "--format", "json"]), 0)
        out = stdout.getvalue()
        return json.loads(out)["cairn"] if out else ""

    def test_budget_omitted_card_can_retry(self):
        self.write("budget-gold", summary="amber cedar opal")
        for padding, clipped in ((260, False), (570, True)):
            with self.subTest(clipped=clipped):
                self.write("budget-lead", summary="amber cedar quartz " * 8 + "x" * padding)
                sid = f"budget-{padding}"
                first = self.hook(sid, "amber cedar quartz")
                self.assertIn("- budget-lead：", first)
                self.assertNotIn("- budget-gold：", first)
                self.assertEqual("…（已截断）" in first, clipped)
                self.assertEqual(cairn._load_seen(sid), {"budget-lead"})
                self.assertIn("- budget-gold：", self.hook(sid, "opal"))
                self.assertEqual(cairn._load_seen(sid), {"budget-lead", "budget-gold"})
                self.assertEqual(self.hook(sid, "quartz"), "")
                self.assertEqual(self.hook(sid, "opal"), "")

    def test_seen_contains_all_rendered_cards_and_preserves_previous(self):
        self.write("prior", summary="indigo")
        self.assertIn("prior", self.hook("multi", "indigo"))
        self.write("lead", summary="amber cedar quartz")
        self.write("gold", summary="amber cedar opal")
        first = self.hook("multi", "amber cedar quartz")
        self.assertIn("lead", first)
        self.assertIn("gold", first)
        self.assertEqual(cairn._load_seen("multi"), {"prior", "lead", "gold"})
        self.assertEqual(self.hook("multi", "amber cedar quartz"), "")

    def test_failed_emit_does_not_consume_card_or_previous_seen(self):
        self.write("prior", summary="indigo")
        self.assertIn("prior", self.hook("emit-failure", "indigo"))
        state = cairn._session_file("emit-failure")
        before = state.read_bytes()
        self.write("amber", summary="amber")
        with patch.object(cairn, "emit", side_effect=BrokenPipeError):
            self.assertEqual(self.hook("emit-failure", "amber"), "")
        self.assertEqual(state.read_bytes(), before)
        self.assertIn("amber", self.hook("emit-failure", "amber"))

    def test_render_failure_does_not_consume_card(self):
        self.write("amber", summary="amber")
        with patch.object(cairn, "render_cards", side_effect=ValueError("render failed")):
            self.assertEqual(self.hook("render-failure", "amber"), "")
        self.assertFalse(cairn._session_file("render-failure").exists())
        self.assertIn("amber", self.hook("render-failure", "amber"))

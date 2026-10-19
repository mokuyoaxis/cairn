# -*- coding: utf-8 -*-
import io
import json
import os
import sys
import unittest

from support import Base, cairn


class TestHook(Base):
    def _run(self, payload):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(json.dumps(payload, ensure_ascii=False)), io.StringIO()
        try:
            return cairn.main(["hook", "--format", "claude"]), sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out

    def test_injects_card(self):
        self.write("compose-dump", summary="docker compose config 会把密钥明文打印出来")
        cairn._INDEX = None
        _, out = self._run({"prompt": "compose 把密钥打印出来怎么办", "session_id": "s1"})
        self.assertIn("compose-dump",
                      json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_session_dedup(self):
        self.write("compose-dump", summary="docker compose config 会把密钥明文打印出来")
        cairn._INDEX = None
        _, first = self._run({"prompt": "compose 把密钥打印出来", "session_id": "s2"})
        _, second = self._run({"prompt": "compose 把密钥打印出来", "session_id": "s2"})
        self.assertTrue(first)
        self.assertEqual(second, "")

    def test_new_session_injects_again(self):
        self.write("compose-dump", summary="docker compose config 会把密钥明文打印出来")
        cairn._INDEX = None
        _, a = self._run({"prompt": "compose 把密钥打印出来", "session_id": "s3"})
        _, b = self._run({"prompt": "compose 把密钥打印出来", "session_id": "s4"})
        self.assertTrue(a and b)

    def test_extract_prompt_nested(self):
        self.assertEqual(cairn.extract_prompt({"properties": {"prompt": "nested"}}),
                         "nested")
        self.assertEqual(cairn.extract_prompt({"message": {"content": "msg"}}), "msg")

    def test_malformed_stdin_is_silent(self):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO("not json"), io.StringIO()
        try:
            self.assertEqual(cairn.main(["hook"]), 0)
            self.assertEqual(sys.stdout.getvalue(), "")
        finally:
            sys.stdin, sys.stdout = old_in, old_out

    def test_miss_is_logged(self):
        cairn._INDEX = None
        self._run({"prompt": "帮我写一个快速排序", "session_id": "s5"})
        self.assertTrue((self.home / "log" / "miss.jsonl").is_file())

    def test_inject_log_does_not_store_raw_prompt(self):
        self.write("compose-dump", summary="docker compose config 会把密钥明文打印出来")
        cairn._INDEX = None
        secret = "sk-" + "a" * 30
        prompt = f"compose 把密钥打印出来怎么办 {secret}"
        _, out = self._run({"prompt": prompt, "session_id": "log-inject"})
        self.assertTrue(out)
        raw = (self.home / "log" / "inject.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(secret, raw)
        self.assertNotIn(prompt, raw)
        rec = json.loads(raw.splitlines()[-1])
        self.assertEqual(rec["query_len"], len(prompt))
        self.assertIn("query_sha256", rec)
        self.assertNotIn("sid", rec)
        self.assertTrue(rec["ts"].endswith("+00:00"))

    def test_miss_log_does_not_store_raw_prompt(self):
        cairn._INDEX = None
        secret = "sk-" + "b" * 30
        prompt = f"帮我写一个快速排序 {secret}"
        self._run({"prompt": prompt, "session_id": "log-miss"})
        raw = (self.home / "log" / "miss.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(secret, raw)
        rec = json.loads(raw.splitlines()[-1])
        self.assertEqual(rec["reason"], "no_hit")
        self.assertIn("query_sha256", rec)

    def test_query_preview_is_opt_in_and_redacted(self):
        self.write("compose-dump", summary="docker compose config 会把密钥明文打印出来")
        cairn._INDEX = None
        secret = "sk-" + "c" * 30
        old = os.environ.get("CAIRN_LOG_QUERY_PREVIEW")
        os.environ["CAIRN_LOG_QUERY_PREVIEW"] = "1"
        try:
            self._run({"prompt": f"compose 密钥 /home/alice {secret}",
                       "session_id": "preview"})
        finally:
            if old is None:
                os.environ.pop("CAIRN_LOG_QUERY_PREVIEW", None)
            else:
                os.environ["CAIRN_LOG_QUERY_PREVIEW"] = old
        raw = (self.home / "log" / "inject.jsonl").read_text(encoding="utf-8")
        rec = json.loads(raw.splitlines()[-1])
        self.assertIn("query_preview", rec)
        self.assertNotIn("/home/alice", raw)
        self.assertNotIn(secret, raw)


class TestStats(Base):
    def test_default_stats_does_not_print_legacy_raw_query(self):
        logdir = self.home / "log"
        logdir.mkdir()
        secret = "sk-" + "d" * 30
        (logdir / "miss.jsonl").write_text(
            json.dumps({"query": f"please fix {secret}"}) + "\n", encoding="utf-8")
        old_out, old_in = sys.stdout, sys.stdin
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["stats"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertEqual(rc, 0)
        self.assertNotIn(secret, out)
        self.assertNotIn("please fix", out)

        sys.stdout = io.StringIO()
        try:
            cairn.main(["stats", "--show-queries"])
            out2 = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertNotIn(secret, out2)
        self.assertIn("<api-key>", out2)

    def test_stats_counts_events(self):
        logdir = self.home / "log"
        logdir.mkdir()
        (logdir / "inject.jsonl").write_text(
            json.dumps({"slugs": ["a"], "session": "s"}) + "\n", encoding="utf-8")
        (logdir / "miss.jsonl").write_text(
            json.dumps({"reason": "no_hit", "session": "s",
                        "query_sha256": "x", "query_len": 3}) + "\n", encoding="utf-8")
        (logdir / "show.jsonl").write_text(
            json.dumps({"slug": "a"}) + "\n", encoding="utf-8")
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["stats"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertEqual(rc, 0)
        self.assertIn("注入 1 次", out)
        self.assertIn("miss 1 次", out)
        self.assertIn("show 1 次", out)


if __name__ == "__main__":
    unittest.main()

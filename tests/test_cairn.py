# -*- coding: utf-8 -*-
"""cairn 单元测试（标准库 unittest，零依赖）。

    python3 -m unittest discover tests -v
"""
import io
import json
import os
import pickle
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
import cairn  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        os.environ["CAIRN_HOME"] = str(self.home)
        cairn._INDEX = None
        (self.home / "entries").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)
        cairn._INDEX = None

    def write(self, name, summary="示例", body="正文", kind="lesson",
              updated="2026-10-19", scope="git", source="test",
              status="active", trust="verified", verified_at="2026-10-19"):
        fm = {"name": name, "summary": summary, "kind": kind, "updated": updated,
              "status": status, "trust": trust}
        if scope:
            fm["scope"] = scope
        if source:
            fm["source"] = source
        if verified_at:
            fm["verified_at"] = verified_at
        text = "---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + f"\n---\n\n{body}\n"
        (self.home / "entries" / f"{name}.md").write_text(text, encoding="utf-8")
        cairn._INDEX = None
        return text


class TestTokenize(unittest.TestCase):
    def test_cjk_bigram(self):
        self.assertIn("卡死", cairn.tokenize("一直卡死不返回"))

    def test_latin_lower(self):
        self.assertIn("docker", cairn.tokenize("Docker Compose"))

    def test_stop_grams_dropped(self):
        self.assertNotIn("这个", cairn.tokenize("这个怎么做"))

    def test_single_char_run_kept(self):
        self.assertIn("坑", cairn.tokenize("坑"))

    def test_empty(self):
        self.assertEqual(cairn.tokenize(""), [])


class TestFrontmatter(Base):
    def test_missing_fence(self):
        fm, _, err = cairn.split_frontmatter("no fence\n")
        self.assertIsNone(fm)
        self.assertTrue(err)

    def test_bom_and_crlf(self):
        fm, _, err = cairn.split_frontmatter("\ufeff---\r\nname: a\r\n---\r\nbody")
        self.assertIsNone(err)
        self.assertEqual(fm["name"], "a")

    def test_quoted_value(self):
        fm, _, _ = cairn.split_frontmatter('---\nname: a\nsummary: "带 空格"\n---\nx')
        self.assertEqual(fm["summary"], "带 空格")


class TestAddAndLint(Base):
    def test_add_then_lint_pass(self):
        rc = cairn.main(["add", "--name", "demo-entry", "--summary", "示例",
                         "--kind", "lesson", "正文内容"])
        self.assertEqual(rc, 0)
        self.assertEqual(cairn.main(["lint"]), 0)

    def test_add_rejects_bad_slug(self):
        self.assertEqual(cairn.main(["add", "--name", "Bad Name", "--summary", "x", "b"]), 2)

    def test_add_requires_summary(self):
        self.assertEqual(cairn.main(["add", "--name", "no-summary", "b"]), 2)

    def test_add_refuses_overwrite(self):
        args = ["add", "--name", "dup", "--summary", "x", "b"]
        self.assertEqual(cairn.main(args), 0)
        self.assertEqual(cairn.main(args), 1)

    def test_lint_fails_on_empty_library(self):
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_lint_catches_missing_fields(self):
        (self.home / "entries" / "broken.md").write_text(
            "---\nname: broken\nsummary: d\nkind: lesson\n---\n\nx\n", encoding="utf-8")
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_lint_catches_bad_kind(self):
        self.write("bad-kind", kind="pitfall")
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_lint_catches_name_mismatch(self):
        text = self.write("actual-name")
        (self.home / "entries" / "actual-name.md").write_text(
            text.replace("name: actual-name", "name: other-name"), encoding="utf-8")
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_lint_catches_bad_date(self):
        self.write("bad-date", updated="2026/10/19")
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_lint_catches_nul(self):
        (self.home / "entries" / "nul.md").write_bytes(
            b"---\nname: nul\nsummary: d\nkind: lesson\nupdated: 2026-10-19\n---\n\n"
            b"code: b\"\x00\"\n")
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_lint_catches_dead_link(self):
        self.write("linker", body="关联 [[does-not-exist]]")
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_lint_ok_with_existing_link(self):
        self.write("target-entry")
        self.write("linker", body="关联 [[target-entry]]")
        self.assertEqual(cairn.main(["lint"]), 0)

    def test_unknown_field_is_warning_only(self):
        text = self.write("extra-field").replace("---\n\n", "type: old\n---\n\n")
        (self.home / "entries" / "extra-field.md").write_text(text, encoding="utf-8")
        self.assertEqual(cairn.main(["lint"]), 0)


class TestRetrieval(Base):
    def test_ranks_by_summary(self):
        self.write("compose-dump", summary="docker compose config 会把密钥明文打印出来")
        self.write("unrelated", summary="如何用 Python 写一个快速排序")
        cairn._INDEX = None
        idx = cairn.get_index(force=True)
        self.assertEqual(idx.search("compose 把密钥打印出来了")[0][4]["name"], "compose-dump")

    def test_gate_rejects_weak_match(self):
        self.write("windows-topic", summary="Windows 下路径与反斜杠的坑")
        cairn._INDEX = None
        self.assertEqual(cairn.gate(cairn.get_index(force=True).search("帮我写一个排序算法")), [])

    def test_clear_winner_on_tiny_library(self):
        self.write("only-entry", summary="docker compose config 会把密钥打印出来")
        cairn._INDEX = None
        idx = cairn.get_index(force=True)
        hits = cairn.gate(idx.search("compose 密钥"), q_len=len(cairn.tokenize("compose 密钥")))
        self.assertEqual([h[4]["name"] for h in hits], ["only-entry"])

    def test_two_close_hits_do_not_trigger_fallback(self):
        self.write("entry-a", summary="docker compose config 密钥")
        self.write("entry-b", summary="docker compose config 密钥")
        cairn._INDEX = None
        idx = cairn.get_index(force=True)
        self.assertEqual(cairn.gate(idx.search("compose 密钥"), min_score=99.0, q_len=2), [])

    def test_normalized_score_bounded(self):
        for i in range(5):
            self.write(f"entry-{i}", summary=f"条目{i} 关于 docker 的说明")
        cairn._INDEX = None
        res = cairn.get_index(force=True).search("docker 说明")
        self.assertTrue(0 < res[0][0] <= 2.2)


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


class TestImport(Base):
    def test_import_maps_old_fields(self):
        src = self.home / "old"
        src.mkdir()
        (src / "legacy-entry.md").write_text(
            "---\nname: legacy-entry\ndescription: 旧字段摘要\ntype: pitfall\n"
            "source: s\ndate: 2026-01-01\nverified: 2026-02-02\ntopic: git\n---\n\nx\n",
            encoding="utf-8")
        self.assertEqual(cairn.main(["import", str(src)]), 0)
        e, err = cairn.read_entry(self.home / "entries" / "legacy-entry.md")
        self.assertIsNone(err)
        self.assertEqual(e["summary"], "旧字段摘要")
        self.assertEqual(e["kind"], "lesson")
        self.assertEqual(e["updated"], "2026-02-02")
        self.assertEqual(e["scope"], "git")

    def test_import_exclude(self):
        src = self.home / "old2"
        src.mkdir()
        for name, summary in (("keep-me", "公开条目"), ("drop-me", "内部条目")):
            (src / f"{name}.md").write_text(
                f"---\nname: {name}\nsummary: {summary}\nkind: lesson\n"
                f"updated: 2026-01-01\n---\n\nx\n", encoding="utf-8")
        cairn.main(["import", str(src), "--exclude", "内部"])
        self.assertTrue((self.home / "entries" / "keep-me.md").exists())
        self.assertFalse((self.home / "entries" / "drop-me.md").exists())

    def test_import_skips_readme(self):
        src = self.home / "old3"
        src.mkdir()
        (src / "README.md").write_text("# 说明\n", encoding="utf-8")
        (src / "ok.md").write_text(
            "---\nname: ok\nsummary: 可以\nkind: method\nupdated: 2026-01-01\n---\n\nx\n",
            encoding="utf-8")
        cairn.main(["import", str(src)])
        self.assertFalse((self.home / "entries" / "README.md").exists())

    def test_import_normalizes_filename_and_lints(self):
        src = self.home / "old4"
        src.mkdir()
        (src / "Bad Name.md").write_text(
            "---\nname: Bad Name\nsummary: 文件名归一\nkind: lesson\n"
            "updated: 2026-01-01\n---\n\nx\n", encoding="utf-8")
        self.assertEqual(cairn.main(["import", str(src)]), 0)
        self.assertTrue((self.home / "entries" / "bad-name.md").is_file())
        self.assertFalse((self.home / "entries" / "Bad Name.md").exists())
        e, err = cairn.read_entry(self.home / "entries" / "bad-name.md")
        self.assertIsNone(err)
        self.assertEqual(e["name"], "bad-name")
        self.assertEqual(cairn.main(["lint"]), 0)

    def test_import_dry_run_does_not_write(self):
        src = self.home / "old5"
        src.mkdir()
        (src / "Bad Name.md").write_text(
            "---\nname: Bad Name\nsummary: 干跑\nkind: lesson\n"
            "updated: 2026-01-01\n---\n\nx\n", encoding="utf-8")
        self.assertEqual(cairn.main(["import", str(src), "--dry-run"]), 0)
        self.assertEqual(list((self.home / "entries").iterdir()), [])

    def test_import_skips_invalid_date(self):
        src = self.home / "old6"
        src.mkdir()
        (src / "bad-date.md").write_text(
            "---\nname: bad-date\nsummary: 日期非法\nkind: lesson\n"
            "updated: 2026/01/01\n---\n\nx\n", encoding="utf-8")
        self.assertEqual(cairn.main(["import", str(src)]), 1)
        self.assertFalse((self.home / "entries" / "bad-date.md").exists())


class TestContract(Base):
    def _hook(self, prompt):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(json.dumps({"prompt": prompt, "session_id": "contract"}))
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["hook", "--format", "text"])
            return rc, sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out

    def test_unverified_not_injected(self):
        self.write("legacy", summary="docker compose config 密钥",
                   trust="unverified", verified_at="")
        cairn._INDEX = None
        self.assertEqual(cairn.main(["recall", "docker compose config 密钥"]), 1)
        _, out = self._hook("docker compose config 密钥")
        self.assertEqual(out, "")

    def test_quarantined_not_injected(self):
        self.write("quarantined", summary="docker compose config 密钥",
                   trust="quarantined", verified_at="")
        cairn._INDEX = None
        self.assertEqual(cairn.main(["recall", "docker compose config 密钥"]), 1)

    def test_deprecated_not_injected(self):
        self.write("deprecated", summary="docker compose config 密钥",
                   status="deprecated")
        cairn._INDEX = None
        self.assertEqual(cairn.main(["recall", "docker compose config 密钥"]), 1)

    def test_lint_warns_unverified(self):
        self.write("legacy", trust="unverified", verified_at="")
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["lint"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertEqual(rc, 0)
        self.assertIn("不会自动注入", out)

    def test_lint_rejects_invalid_contract(self):
        self.write("bad", trust="maybe", verified_at="")
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_verified_needs_source_and_date(self):
        self.write("bad-verified", source="", verified_at="")
        self.assertEqual(cairn.main(["lint"]), 1)

    def test_add_defaults_to_unverified(self):
        self.assertEqual(cairn.main(["add", "--name", "new-entry",
                                     "--summary", "s", "b"]), 0)
        e, err = cairn.read_entry(self.home / "entries" / "new-entry.md")
        self.assertIsNone(err)
        self.assertEqual((e["status"], e["trust"]), ("active", "unverified"))

    def test_add_verified_requires_evidence(self):
        base = ["add", "--name", "verified-entry", "--summary", "s",
                "--trust", "verified"]
        self.assertEqual(cairn.main(base + ["b"]), 2)
        self.assertEqual(cairn.main(base + ["--source", " ",
                                            "--verified-at", "2026-10-19", "b"]), 2)
        self.assertEqual(cairn.main(base + ["--source", "src",
                                            "--verified-at", "2026-10-19", "b"]), 0)
        e, _ = cairn.read_entry(self.home / "entries" / "verified-entry.md")
        self.assertEqual(e["trust"], "verified")

    def test_import_defaults_to_quarantine(self):
        src = self.home / "contract-src"
        src.mkdir()
        (src / "imported.md").write_text(
            "---\nname: imported\nsummary: s\nkind: lesson\nupdated: 2026-01-01\n"
            "trust: verified\nverified_at: 2026-01-01\nsource: x\n---\n\nx\n",
            encoding="utf-8")
        self.assertEqual(cairn.main(["import", str(src)]), 0)
        e, err = cairn.read_entry(self.home / "entries" / "imported.md")
        self.assertIsNone(err)
        self.assertEqual((e["status"], e["trust"]), ("active", "quarantined"))

    def test_raw_shows_contract_marker(self):
        self.write("legacy", summary="docker compose config 密钥",
                   trust="unverified", verified_at="")
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            cairn.main(["recall", "docker compose config 密钥", "--raw"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertIn("active/unverified", out)

    def test_old_cache_without_contract_is_rebuilt(self):
        self.write("entry", summary="docker compose config 密钥")
        cairn._INDEX = None
        cairn.get_index(force=True)
        cache = self.home / "cache" / "index.pkl"
        blob = pickle.loads(cache.read_bytes())
        for d in blob["data"]["docs"]:
            d.pop("trust", None)
        cache.write_bytes(pickle.dumps(blob))
        cairn._INDEX = None
        idx = cairn.get_index()
        self.assertTrue(all("trust" in d for d in idx.docs))


class TestAudit(Base):
    def test_detects_private_key(self):
        self.write("leaky", body="-----BEGIN RSA PRIVATE KEY-----\nabc")
        self.assertEqual(cairn.main(["audit"]), 1)

    def test_detects_home_path(self):
        self.write("path-leak", body="配置在 C:\\\\Users\\\\alice\\\\.config")
        self.assertEqual(cairn.main(["audit"]), 1)

    def test_clean_library_passes(self):
        self.write("clean", body="不要用 docker compose config 校验配置")
        self.assertEqual(cairn.main(["audit"]), 0)

    def test_audit_fails_on_empty_library(self):
        self.assertEqual(cairn.main(["audit"]), 1)

    def test_audit_detects_secret_in_log(self):
        self.write("clean", body="不要用 docker compose config 校验配置")
        logdir = self.home / "log"
        logdir.mkdir()
        (logdir / "inject.jsonl").write_text(
            json.dumps({"query": "sk-" + "e" * 30}) + "\n", encoding="utf-8")
        self.assertEqual(cairn.main(["audit"]), 1)

    def test_audit_does_not_echo_full_secret(self):
        self.write("clean", body="不要用 docker compose config 校验配置")
        secret = "sk-" + "g" * 30
        logdir = self.home / "log"
        logdir.mkdir()
        (logdir / "inject.jsonl").write_text(
            json.dumps({"query": secret}) + "\n", encoding="utf-8")
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            cairn.main(["audit"])
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_out
        self.assertNotIn(secret, out)
        self.assertIn("<api-key>", out)

    def test_audit_clean_log_passes(self):
        self.write("clean", body="不要用 docker compose config 校验配置")
        logdir = self.home / "log"
        logdir.mkdir()
        (logdir / "inject.jsonl").write_text(
            json.dumps({"event": "inject", "query_sha256": "abc123"}) + "\n",
            encoding="utf-8")
        self.assertEqual(cairn.main(["audit"]), 0)

    def test_sanitize_refuses_source_dir(self):
        self.write("path-leak", body="配置在 /home/alice/.config")
        source = self.home / "entries" / "path-leak.md"
        before = source.read_text(encoding="utf-8")
        rc = cairn.main(["sanitize", "--out", str(self.home / "entries")])
        self.assertEqual(rc, 2)
        self.assertEqual(source.read_text(encoding="utf-8"), before)

    def test_sanitize_refuses_output_inside_entries(self):
        self.write("path-leak", body="配置在 /home/alice/.config")
        rc = cairn.main(["sanitize", "--out", str(self.home / "entries" / "clean")])
        self.assertEqual(rc, 2)

    def test_sanitize_refuses_symlink_to_entries(self):
        self.write("path-leak", body="配置在 /home/alice/.config")
        link = self.home / "entries-link"
        try:
            os.symlink(self.home / "entries", link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        rc = cairn.main(["sanitize", "--out", str(link)])
        self.assertEqual(rc, 2)

    def test_sanitize_refuses_existing_target_without_force(self):
        self.write("path-leak", body="配置在 /home/alice/.config")
        out = self.home / "clean-copy"
        (out / "entries").mkdir(parents=True)
        target = out / "entries" / "path-leak.md"
        target.write_text("keep me", encoding="utf-8")
        self.assertEqual(cairn.main(["sanitize", "--out", str(out)]), 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(cairn.main(["sanitize", "--out", str(out), "--force"]), 0)
        self.assertIn("<user>", target.read_text(encoding="utf-8"))

    def test_sanitize_output_is_auditable_home(self):
        self.write("path-leak", body="配置在 /home/alice/.config")
        out = self.home / "clean-copy"
        self.assertEqual(cairn.main(["sanitize", "--out", str(out)]), 0)
        old = os.environ.get("CAIRN_HOME")
        os.environ["CAIRN_HOME"] = str(out)
        try:
            self.assertEqual(cairn.main(["audit"]), 0)
        finally:
            if old is None:
                os.environ.pop("CAIRN_HOME", None)
            else:
                os.environ["CAIRN_HOME"] = old

    def test_sanitize_redacts_credentials(self):
        secret = "sk-" + "f" * 30
        self.write("credential-leak", body=f"key {secret} at /home/alice/.config")
        out = self.home / "clean-copy"
        self.assertEqual(cairn.main(["sanitize", "--out", str(out)]), 0)
        text = (out / "entries" / "credential-leak.md").read_text(encoding="utf-8")
        self.assertNotIn(secret, text)
        self.assertIn("<api-key>", text)
        self.assertIn("<user>", text)

    def test_sanitize_rewrites_without_touching_source(self):
        self.write("path-leak", body="配置在 C:\\\\Users\\\\alice\\\\.config")
        before = (self.home / "entries" / "path-leak.md").read_text(encoding="utf-8")
        out = self.home / "clean-copy"
        self.assertEqual(cairn.main(["sanitize", "--out", str(out)]), 0)
        self.assertEqual((self.home / "entries" / "path-leak.md").read_text(encoding="utf-8"),
                         before)
        self.assertIn("<user>", (out / "entries" / "path-leak.md").read_text(encoding="utf-8"))


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


if __name__ == "__main__":
    unittest.main()

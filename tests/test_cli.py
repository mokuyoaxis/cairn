# -*- coding: utf-8 -*-
import io
import json
import os
import subprocess
import sys
import unittest

from support import Base, REPO, cairn


class TestCLI(Base):
    def _run(self, argv):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(), io.StringIO()
        try:
            rc = cairn.main(argv)
            return rc, sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out

    def _hook(self, payload, fmt):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(json.dumps(payload, ensure_ascii=False))
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["hook", "--format", fmt])
            return rc, sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out

    def test_show_and_ls(self):
        self.write("demo-entry", summary="示例摘要", body="正文内容")
        rc, out = self._run(["show", "demo-entry"])
        self.assertEqual(rc, 0)
        self.assertIn("示例摘要", out)
        self.assertIn("正文内容", out)
        self.assertTrue((self.home / "log" / "show.jsonl").is_file())
        rc, listed = self._run(["ls"])
        self.assertEqual(rc, 0)
        self.assertIn("demo-entry", listed)
        rc, md = self._run(["ls", "--md"])
        self.assertEqual(rc, 0)
        self.assertIn("# cairn 索引", md)

    def test_show_missing_entry(self):
        rc, _ = self._run(["show", "missing-entry"])
        self.assertEqual(rc, 1)

    def test_show_rejects_path_traversal(self):
        (self.home / "secret.md").write_text("do not read", encoding="utf-8")
        rc, out = self._run(["show", "../secret"])
        self.assertEqual(rc, 1)
        self.assertNotIn("do not read", out)

    def test_prune_links(self):
        self.write("linker", body="关联 [[missing-entry]]")
        self.assertEqual(cairn.main(["prune-links"]), 0)
        text = (self.home / "entries" / "linker.md").read_text(encoding="utf-8")
        self.assertNotIn("[[missing-entry]]", text)
        self.assertEqual(cairn.main(["lint"]), 0)

    def test_feedback_logs_redacted_note(self):
        secret = "sk-" + "q" * 30
        rc, _ = self._run(["feedback", "entry", "--helpful",
                           "--note", f"this was useful {secret}"])
        self.assertEqual(rc, 0)
        raw = (self.home / "log" / "feedback.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(secret, raw)
        rec = json.loads(raw.splitlines()[-1])
        self.assertEqual(rec["slug"], "entry")
        self.assertEqual(rec["signal"], "helpful")
        self.assertIn("note_sha256", rec)

    def test_nudge_output(self):
        rc, out = self._run(["nudge", "--format", "text"])
        self.assertEqual(rc, 0)
        self.assertIn("cairn add", out)

    def test_hook_formats(self):
        self.write("compose-dump", summary="docker compose config 密钥")
        cairn._INDEX = None
        for fmt, key in (("json", "cairn"), ("codex", "systemMessage")):
            rc, out = self._hook({"prompt": "compose 密钥",
                                  "session_id": f"fmt-{fmt}"}, fmt)
            self.assertEqual(rc, 0)
            self.assertIn("compose-dump", json.loads(out)[key])
        rc, out = self._hook({"prompt": "compose 密钥", "session_id": "fmt-text"}, "text")
        self.assertEqual(rc, 0)
        self.assertIn("compose-dump", out)

    def test_add_force_overwrites(self):
        self.assertEqual(cairn.main(["add", "--name", "force-entry",
                                     "--summary", "first", "body-one"]), 0)
        self.assertEqual(cairn.main(["add", "--name", "force-entry",
                                     "--summary", "second", "body-two"]), 1)
        self.assertEqual(cairn.main(["add", "--name", "force-entry",
                                     "--summary", "second", "--force",
                                     "body-two"]), 0)
        e, err = cairn.read_entry(self.home / "entries" / "force-entry.md")
        self.assertIsNone(err)
        self.assertEqual(e["summary"], "second")
        self.assertIn("body-two", e["body"])

    def test_import_collision_and_force(self):
        src = self.home / "import-src"
        src.mkdir()
        (src / "keep-me.md").write_text(
            "---\nname: keep-me\nsummary: new summary\nkind: lesson\n"
            "updated: 2026-10-19\n---\n\nnew body\n", encoding="utf-8")
        self.write("keep-me", summary="old summary", body="old body")
        self.assertEqual(cairn.main(["import", str(src)]), 0)
        e, _ = cairn.read_entry(self.home / "entries" / "keep-me.md")
        self.assertEqual(e["summary"], "old summary")
        self.assertEqual(cairn.main(["import", str(src), "--force"]), 0)
        e, _ = cairn.read_entry(self.home / "entries" / "keep-me.md")
        self.assertEqual(e["summary"], "new summary")
        self.assertEqual(e["trust"], "quarantined")

    def test_launcher_version(self):
        exe = REPO / "cairn"
        if not os.access(exe, os.X_OK):
            self.skipTest("launcher is not executable")
        result = subprocess.run([str(exe), "--version"], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cairn 0.1.0", result.stdout)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
import io
import json
import os
import sys
import unittest

from support import Base, cairn


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

    def test_audit_read_error_returns_1(self):
        (self.home / "entries" / "broken.md").mkdir()
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


if __name__ == "__main__":
    unittest.main()

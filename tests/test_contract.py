# -*- coding: utf-8 -*-
import io
import json
import pickle
import sys
import unittest

from support import Base, cairn


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


if __name__ == "__main__":
    unittest.main()

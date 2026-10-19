# -*- coding: utf-8 -*-
"""Shared test support (not a test module)."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
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

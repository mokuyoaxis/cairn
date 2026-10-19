# -*- coding: utf-8 -*-
import io
import sys
import unittest

from support import Base, cairn


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

    def test_add_reads_body_from_stdin(self):
        old_in = sys.stdin
        sys.stdin = io.StringIO("stdin body\n")
        try:
            rc = cairn.main(["add", "--name", "stdin-entry",
                             "--summary", "s", "-"])
        finally:
            sys.stdin = old_in
        self.assertEqual(rc, 0)
        e, err = cairn.read_entry(self.home / "entries" / "stdin-entry.md")
        self.assertIsNone(err)
        self.assertIn("stdin body", e["body"])

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


if __name__ == "__main__":
    unittest.main()

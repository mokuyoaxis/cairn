# -*- coding: utf-8 -*-
"""Three-valued applicability gate tests (research module; core untouched)."""
import os
import pickle
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO

sys.path.insert(0, str(REPO / "eval"))
import applicability_gate as gate  # noqa: E402
import cairn  # noqa: E402


FM = {"requires": "journal_mode=wal; checkpointed=false", "excludes": "checkpointed=true"}


class TestPredicates(unittest.TestCase):
    def test_parse_predicates(self):
        preds, bad = gate.parse_predicates("a=1; b=two")
        self.assertEqual(preds, [("a", "1"), ("b", "two")])
        self.assertEqual(bad, [])

    def test_parse_predicates_accepts_cjk_semicolon(self):
        preds, _ = gate.parse_predicates("a=1；b=2")
        self.assertEqual(len(preds), 2)

    def test_malformed_predicate_is_reported(self):
        _, bad = gate.parse_predicates("a=1; nonsense")
        self.assertEqual(bad, ["nonsense"])

    def test_parse_context_from_string(self):
        self.assertEqual(gate.parse_context("a=1,b=2"), {"a": "1", "b": "2"})

    def test_parse_context_from_list(self):
        self.assertEqual(gate.parse_context(["a=1", "b=2"]), {"a": "1", "b": "2"})

    def test_parse_context_lowercases_keys_and_values(self):
        self.assertEqual(gate.parse_context("Shell=BASH"), {"shell": "bash"})


class TestVerdicts(unittest.TestCase):
    def test_all_conditions_met_is_applicable(self):
        v, why = gate.verdict(FM, gate.parse_context("journal_mode=wal,checkpointed=false"))
        self.assertEqual(v, gate.APPLICABLE)

    def test_contradicted_requirement_is_inapplicable(self):
        v, why = gate.verdict(FM, gate.parse_context("journal_mode=delete,checkpointed=false"))
        self.assertEqual(v, gate.INAPPLICABLE)
        self.assertIn("journal_mode", why[0])

    def test_exclusion_hit_is_inapplicable(self):
        v, _ = gate.verdict(FM, gate.parse_context("journal_mode=wal,checkpointed=true"))
        self.assertEqual(v, gate.INAPPLICABLE)

    def test_missing_premise_is_unknown_not_applicable(self):
        v, why = gate.verdict(FM, gate.parse_context(""))
        self.assertEqual(v, gate.UNKNOWN)
        self.assertTrue(why)

    def test_partial_context_is_unknown(self):
        v, _ = gate.verdict(FM, gate.parse_context("journal_mode=wal"))
        self.assertEqual(v, gate.UNKNOWN)

    def test_entry_without_conditions_is_applicable(self):
        v, _ = gate.verdict({"requires": "", "excludes": ""}, gate.parse_context(""))
        self.assertEqual(v, gate.APPLICABLE)

    def test_malformed_condition_is_unknown_not_applicable(self):
        v, why = gate.verdict({"requires": "garbage"}, gate.parse_context(""))
        self.assertEqual(v, gate.UNKNOWN)

    def test_undeclared_exclusion_key_stays_unknown(self):
        v, _ = gate.verdict({"requires": "", "excludes": "os=linux"},
                            gate.parse_context("shell=bash"))
        self.assertEqual(v, gate.UNKNOWN)

    def test_inapplicable_beats_unknown(self):
        # requires 缺失（unknown）但 excludes 命中（inapplicable）→ 必须是不适用
        fm = {"requires": "a=1; b=2", "excludes": "b=9"}
        v, _ = gate.verdict(fm, gate.parse_context("b=9"))
        self.assertEqual(v, gate.INAPPLICABLE)


class TestNoKeywordInference(unittest.TestCase):
    """不变量：查询文本里出现关键事实，也不得据此推断适用性。"""

    def test_query_words_do_not_change_verdict(self):
        ctx = gate.parse_context("")
        v1, _ = gate.verdict(FM, ctx)
        # 模拟“查询里提到了 checkpoint”，但调用方没有声明
        v2, _ = gate.verdict(FM, dict(ctx))
        self.assertEqual(v1, gate.UNKNOWN)
        self.assertEqual(v2, gate.UNKNOWN)

    def test_context_is_the_only_fact_source(self):
        # 同一上下文下，判定与任何查询文本无关（函数签名里根本没有 query）
        import inspect
        params = inspect.signature(gate.verdict).parameters
        self.assertEqual(list(params), ["entry_fm", "ctx"])


class Base(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        os.environ["CAIRN_HOME"] = str(self.home)
        (self.home / "entries").mkdir()
        cairn._INDEX = None

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)
        cairn._INDEX = None

    def write(self, slug, **fm):
        base = {"name": slug, "summary": "sqlite 拷贝后数据缺失 wal checkpoint",
                "kind": "lesson", "updated": "2026-10-25", "status": "active",
                "trust": "verified", "verified_at": "2026-10-25", "source": "test"}
        base.update(fm)
        text = "---\n" + "\n".join("%s: %s" % (k, v) for k, v in base.items() if v != "")
        text += "\n---\n\n正文\n"
        (self.home / "entries" / (slug + ".md")).write_text(text, encoding="utf-8")
        cairn._INDEX = None


class TestFilterHits(Base):
    def _hits(self, query="sqlite 拷贝后数据缺失 wal checkpoint"):
        idx = cairn.get_index(force=True)
        res = idx.search(query, limit=len(idx.docs) or 1)
        return cairn.gate(res, q_len=len(cairn.tokenize(query)))

    def _entries(self):
        idx = cairn.get_index()
        return {d["name"]: {"fm": d} for d in idx.docs}

    def test_inapplicable_is_dropped_and_retrieval_is_unaffected(self):
        self.write("wal-entry")
        hits = self._hits()
        self.assertEqual(len(hits), 1)                      # 检索/门控本身照旧
        entries = self._entries()
        entries["wal-entry"]["fm"].update(FM)
        kept, dropped, unknown = gate.filter_hits(
            hits, entries, gate.parse_context("checkpointed=true,journal_mode=wal"))
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0][1], gate.INAPPLICABLE)

    def test_unknown_silent_policy_drops(self):
        self.write("wal-entry")
        hits = self._hits()
        entries = self._entries()
        entries["wal-entry"]["fm"].update(FM)
        kept, dropped, unknown = gate.filter_hits(hits, entries, {}, unknown_policy="silent")
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0][1], gate.UNKNOWN)

    def test_unknown_labeled_policy_keeps_with_marker(self):
        self.write("wal-entry")
        hits = self._hits()
        entries = self._entries()
        entries["wal-entry"]["fm"].update(FM)
        kept, dropped, unknown = gate.filter_hits(hits, entries, {}, unknown_policy="labeled")
        self.assertEqual(len(kept), 1)
        self.assertEqual(unknown[0][0], "wal-entry")
        self.assertEqual(dropped, [])

    def test_applicable_passes_through(self):
        self.write("wal-entry")
        hits = self._hits()
        entries = self._entries()
        entries["wal-entry"]["fm"].update(FM)
        kept, dropped, unknown = gate.filter_hits(
            hits, entries, gate.parse_context("journal_mode=wal,checkpointed=false"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])


class TestCacheVersionGap(Base):
    """记录一个真实兼容性缺口：索引派生逻辑变化时，旧缓存不会失效。"""

    def test_cache_has_no_derivation_version_guard(self):
        self.write("wal-entry")
        idx = cairn.get_index(force=True)
        cache = cairn._cache_file()
        blob = pickle.loads(cache.read_bytes())
        self.assertNotIn("index_version", blob,
                         "当前缓存没有派生版本标记：改索引逻辑不会让旧缓存失效")
        # 模拟“用旧逻辑构建的缓存”：删掉派生字段后仍被接受
        for d in blob["data"]["docs"]:
            d["d"] = {}
        cache.write_bytes(pickle.dumps(blob, protocol=4))
        cairn._INDEX = None
        idx2 = cairn.get_index()
        self.assertEqual(len(idx2.docs[0]["d"]), 0,
                         "旧/异版本缓存被静默复用——这正是要修的兼容性风险")


if __name__ == "__main__":
    unittest.main()

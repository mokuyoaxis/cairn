# -*- coding: utf-8 -*-
import unittest

from support import Base, cairn


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

    def test_render_cards_truncates_long_line(self):
        hits = [(1.0, 1.0, 1, 1, {"name": "long-entry",
                                 "summary": "y" * 600, "path": "long-entry.md"})]
        out = cairn.render_cards(hits, max_chars=200)
        self.assertIn("已截断", out)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
import io
import json
import os
import pickle
import sys
import unittest

from support import Base, cairn


class TestScopeGate(Base):
    def _capture(self, argv):
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(argv)
            return rc, sys.stdout.getvalue()
        finally:
            sys.stdout = old_out

    def _hook(self, prompt):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(json.dumps({"prompt": prompt, "session_id": "scope"}))
        sys.stdout = io.StringIO()
        try:
            rc = cairn.main(["hook", "--format", "text"])
            return rc, sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out

    def test_no_declared_scope_keeps_injection(self):
        # 未声明 scope 时行为完全不变（向后兼容）
        self.write("frontend-only", summary="alpha beta gamma", scope="frontend")
        rc, out = self._capture(["recall", "alpha beta gamma"])
        self.assertEqual(rc, 0)
        self.assertIn("frontend-only", out)

    def test_declared_scope_intersection_injects(self):
        self.write("ui-entry", summary="alpha beta gamma", scope="frontend, ui")
        rc, out = self._capture(["recall", "alpha beta gamma", "--scope", "ui"])
        self.assertEqual(rc, 0)
        self.assertIn("ui-entry", out)

    def test_declared_scope_mismatch_abstains(self):
        self.write("backend-only", summary="alpha beta gamma", scope="backend")
        rc, _ = self._capture(["recall", "alpha beta gamma", "--scope", "frontend"])
        self.assertEqual(rc, 1)

    def test_untagged_entry_is_neutral(self):
        # 没有 scope 的条目是通用经验，任何声明下都应可注入
        self.write("anywhere", summary="alpha beta gamma", scope=None)
        rc, out = self._capture(["recall", "alpha beta gamma", "--scope", "frontend"])
        self.assertEqual(rc, 0)
        self.assertIn("anywhere", out)

    def test_explain_reports_out_of_scope(self):
        self.write("backend-only", summary="alpha beta gamma", scope="backend")
        rc, out = self._capture(["explain", "alpha beta gamma", "--scope", "frontend"])
        self.assertEqual(rc, 1)
        self.assertIn("[out_of_scope]", out)

    def test_scope_filtered_before_margin(self):
        # 高分但不适用 + 低分但适用：适用者应被注入，不被排除者拉大的 margin 拦下
        self.write("backend-strong", summary="alpha beta gamma delta", scope="backend")
        self.write("frontend-weak", summary="alpha beta gamma", scope="frontend")
        rc, out = self._capture(["recall", "alpha beta gamma delta", "--scope", "frontend"])
        self.assertEqual(rc, 0)
        self.assertIn("frontend-weak", out)
        self.assertNotIn("backend-strong", out)

    def test_hook_reads_cairn_scope_env(self):
        self.write("backend-only", summary="alpha beta gamma", scope="backend")
        os.environ["CAIRN_SCOPE"] = "frontend"
        try:
            _, out = self._hook("alpha beta gamma")
        finally:
            os.environ.pop("CAIRN_SCOPE", None)
        self.assertEqual(out, "")

    def test_cache_without_scope_field_is_rebuilt(self):
        # 旧版缓存没有 scope 字段，必须失效重建，否则门控读到空值
        self.write("backend-only", summary="alpha beta gamma", scope="backend")
        idx = cairn.get_index(force=True)
        self.assertIn("scope", idx.docs[0])
        blob_path = cairn._cache_file()
        blob = pickle.loads(blob_path.read_bytes())
        for doc in blob["data"]["docs"]:
            doc.pop("scope", None)
        blob_path.write_bytes(pickle.dumps(blob, protocol=4))
        cairn._INDEX = None
        idx2 = cairn.get_index()
        self.assertIn("scope", idx2.docs[0])


if __name__ == "__main__":
    unittest.main()

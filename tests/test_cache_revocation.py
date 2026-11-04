# -*- coding: utf-8 -*-
"""Regression tests for cache invalidation after an archived edit."""
import os
import sys
import unittest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import Base, cairn


class TestIndexRevocation(Base):
    def _revoke_with_same_size_and_mtime(self):
        self.write("retry-policy", summary="retry permit", body="retry policy  ")
        path = self.home / "entries" / "retry-policy.md"
        before = path.read_text(encoding="utf-8")
        stat = path.stat()
        cairn.get_index(force=True)

        after = before.replace("status: active", "status: archived", 1)
        after = after.replace("retry policy  \n", "retry policy\n", 1)
        self.assertEqual(len(after.encode("utf-8")), len(before.encode("utf-8")))
        path.write_text(after, encoding="utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(path.stat().st_size, stat.st_size)
        self.assertEqual(path.stat().st_mtime_ns, stat.st_mtime_ns)

    def test_warm_index_must_see_revocation(self):
        self._revoke_with_same_size_and_mtime()
        idx = cairn.get_index()
        doc = idx.docs[0]
        self.assertEqual(doc["status"], "archived")
        self.assertFalse(cairn.is_injectable(doc))

    def test_disk_cache_must_see_revocation(self):
        self._revoke_with_same_size_and_mtime()
        cairn._INDEX = None
        idx = cairn.get_index()
        doc = idx.docs[0]
        self.assertEqual(doc["status"], "archived")
        self.assertFalse(cairn.is_injectable(doc))


if __name__ == "__main__":
    unittest.main()

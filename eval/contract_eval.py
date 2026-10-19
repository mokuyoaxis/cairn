#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract admission eval.

Runs the real `cairn.gate()` against a mixed-trust fixture and checks that only
`active + verified + source + verified_at` entries are injected. This is a
sidecar eval: it does not modify the core or the example library.

    python3 eval/contract_eval.py
"""
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "eval" / "contract" / "entries"
CASES = ROOT / "eval" / "contract_cases.jsonl"
sys.path.insert(0, str(ROOT))

import cairn  # noqa: E402


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="cairn-contract-eval-"))
    try:
        shutil.copytree(FIXTURE, home / "entries")
        os.environ["CAIRN_HOME"] = str(home)
        cairn._INDEX = None
        with redirect_stdout(StringIO()):
            lint_rc = cairn.main(["lint"])
        if lint_rc != 0:
            print("[FAIL] contract fixture does not pass lint")
            return 1
        idx = cairn.get_index(force=True)
        cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]
        failed = 0
        for case in cases:
            hits = cairn.gate(
                idx.search(case["query"], limit=len(idx.docs)),
                q_len=len(cairn.tokenize(case["query"])),
            )
            got = [h[4]["name"] for h in hits]
            expected = case["expect_injected"]
            safe = all(cairn.is_injectable(h[4]) for h in hits)
            ok = got == expected and safe
            failed += not ok
            print(f"[{'PASS' if ok else 'FAIL'}] {case['query']}")
            print(f"       expected={expected} got={got} all_injectable={safe}")
        print(f"\n[{'PASS' if not failed else 'FAIL'}] contract admission eval "
              f"({len(cases) - failed}/{len(cases)} cases)")
        return 0 if not failed else 1
    finally:
        shutil.rmtree(home, ignore_errors=True)
        os.environ.pop("CAIRN_HOME", None)


if __name__ == "__main__":
    sys.exit(main())

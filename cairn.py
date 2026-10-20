#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cairn — 把相关经验端到 agent 面前，而不是提醒它去查。

设计：无索引文件、无触发词（每轮检索 + 三道门）、注入卡片而非全文、
零第三方依赖、零网络、2-gram BM25。条目格式与命令见 docs/usage.md。
退出码：0 成功；1 校验/评测未过；2 用法错误。

    cairn add|recall|show|lint|hook|eval|import|stats
"""
from __future__ import annotations

import argparse
import hashlib
import pickle
import json
import math
import os
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

VERSION = "0.1.0"


# ── 路径 ────────────────────────────────────────────────────────────────
HOME = Path(os.environ.get("CAIRN_HOME") or (Path.home() / ".cairn")).expanduser()
ENTRIES = HOME / "entries"
LOGDIR = HOME / "log"

def data_home() -> Path:
    """运行期再取一次，方便测试里改环境变量。"""
    return Path(os.environ.get("CAIRN_HOME") or (Path.home() / ".cairn")).expanduser()

def entries_dir() -> Path:
    return data_home() / "entries"

def log_dir() -> Path:
    return data_home() / "log"


# ── 词表 / 常量 ─────────────────────────────────────────────────────────
KINDS = ("lesson", "method")
STATUSES = ("active", "deprecated", "archived")
TRUSTS = ("verified", "unverified", "quarantined")
REQUIRED = ("name", "summary", "kind", "updated")
OPTIONAL = ("scope", "source", "status", "trust", "verified_at", "evidence")

# 低信息量的 2-gram：不参与打分，否则「这个/可以」把所有条目拉成同分
STOP2 = frozenset("""
这个 那个 一下 我们 你们 他们 它们 现在 然后 可以 需要 什么 怎么 为什么
如果 但是 所以 已经 还是 就是 没有 一个 这样 那样 时候 这里 那里 进行 通过
自己 他们 因为 而且 或者 不过 其实 应该 可能 一直 东西 事情 地方 方式 问题
""".split())

CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")
FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
FM_LINE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
NUL = b"\x00"

DEFAULT_MIN_SCORE = 0.40    # 归一化分数下限
DEFAULT_MIN_COVER = 0.20    # 命中的 query 词占比下限
DEFAULT_MIN_MARGIN = 1.50   # 第一名相对第二名的领先倍数（歧义时不注入）
MAX_CARDS = 3
MAX_CARD_CHARS = 520          # ≈ 260 tokens（中文约 2 字符/token）


# ── 分词 ────────────────────────────────────────────────────────────────
def tokenize(text: str, keep_stop: bool = False) -> list:
    """中文按 2-gram、英文按词切分；零依赖下最稳的近似，可加权、可排序。"""
    if not text:
        return []
    out = []
    for run in CJK_RUN.findall(text):
        if len(run) == 1:
            out.append(run)
            continue
        for i in range(len(run) - 1):
            gram = run[i:i + 2]
            if keep_stop or gram not in STOP2:
                out.append(gram)
    out.extend(w.lower() for w in WORD.findall(text))
    return out


# ── 条目读写 ────────────────────────────────────────────────────────────
def split_frontmatter(text: str):
    """返回 (fm, body, error)。只解析顶层 key，不做 YAML。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    m = FM_RE.match(text)
    if not m:
        return None, text, "缺少开头的 --- frontmatter"
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        mm = FM_LINE.match(line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return fm, text[m.end():], None

def read_entry(path: Path):
    """返回 (entry_dict, error)。任何异常都转成 error 字符串，不抛。"""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"读不出：{exc}"
    if NUL in raw:
        return None, "正文含 NUL 字节（grep 会把它当二进制跳过）"
    text = raw.decode("utf-8", "replace")
    fm, body, err = split_frontmatter(text)
    if fm is None:
        return None, err
    name = (fm.get("name") or path.stem).strip()
    return {
        "name": name,
        "slug": path.stem,
        "path": path.name,
        "fm": fm,
        "body": body,
        "summary": fm.get("summary", "").strip(),
        "kind": fm.get("kind", "").strip(),
        "scope": fm.get("scope", "").strip(),
        "source": fm.get("source", "").strip(),
        "status": (fm.get("status") or "active").strip(),
        "trust": (fm.get("trust") or "unverified").strip(),
        "verified_at": fm.get("verified_at", "").strip(),
        "updated": fm.get("updated", "").strip(),
    }, None

def load_entries():
    """返回 (entries, errors)。errors = [(filename, message)]。"""
    entries, errors = [], []
    d = entries_dir()
    if not d.is_dir():
        return entries, errors
    for path in sorted(d.glob("*.md")):
        e, err = read_entry(path)
        if err:
            errors.append((path.name, err))
        else:
            entries.append(e)
    return entries, errors


# ── 索引 / 打分 ─────────────────────────────────────────────────────────
class Index:
    """2-gram BM25，字段加权：summary ×3 > name ×2 > body ×1。"""

    def __init__(self, entries):
        self.docs = []
        for e in entries:
            n = Counter(tokenize(e["name"].replace("-", " ")))
            desc = Counter(tokenize(e["summary"]))
            body = Counter(tokenize(e["body"]))
            self.docs.append({
                "name": e["name"], "path": e["path"],
                "summary": e["summary"], "kind": e["kind"],
                "status": e["status"], "trust": e["trust"],
                "verified_at": e["verified_at"], "source": e["source"],
                "n": n, "d": desc, "b": body,
                "len": len(n) + len(desc) + len(body),
            })
        self.n_docs = len(self.docs)
        if not self.n_docs:
            self.idf, self.avgdl = {}, 1.0
            return
        df = Counter()
        for doc in self.docs:
            for tok in set(doc["n"]) | set(doc["d"]) | set(doc["b"]):
                df[tok] += 1
        self.idf = {t: math.log(1 + (self.n_docs - c + 0.5) / (c + 0.5))
                    for t, c in df.items()}
        # 未出现过的词按「最稀有」算的查询置信度目前不参与排序，故不持久化。
        self.avgdl = sum(d["len"] for d in self.docs) / self.n_docs

    def search(self, query: str, limit: int = 8):
        """返回 [(norm, score, matched, desc_matched, doc)]；norm 为 query 信息覆盖率。"""
        q = list(dict.fromkeys(tokenize(query)))
        if not q or not self.docs:
            return []
        # 用 idf 高的词优先（长尾词才有区分度），限制项数控制成本
        q.sort(key=lambda t: -self.idf.get(t, 0.0))
        q = q[:80]
        k1, b = 1.2, 0.75
        results = []
        for doc in self.docs:
            dl = doc["len"] or 1
            norm = k1 * (1 - b + b * dl / self.avgdl)
            score, matched, d_matched = 0.0, 0, 0
            for tok in q:
                tf = doc["n"].get(tok, 0) * 2 + doc["d"].get(tok, 0) * 3 + doc["b"].get(tok, 0)
                if not tf:
                    continue
                matched += 1
                if doc["n"].get(tok) or doc["d"].get(tok):
                    d_matched += 1
                score += self.idf.get(tok, 0.0) * (tf * (k1 + 1)) / (tf + norm)
            if score > 0:
                results.append((score, matched, d_matched, doc))
        # 分母只算库里真实存在的词：库外的词无法被任何条目覆盖，
        # 把它们算进分母会让长 query 的分数被系统性压低（小库尤其明显）。
        known = [t for t in q if t in self.idf]
        denom = sum(self.idf[t] for t in known) or 1.0
        results = [(score / denom, score, matched, d_matched, doc)
                   for score, matched, d_matched, doc in results]
        results.sort(key=lambda x: (-x[0], x[4]["name"]))
        return results[:limit]

_INDEX = None

def _to_plain(idx: "Index") -> dict:
    """Counter → 普通 dict。pickle 反序列化 Counter 慢 4 倍（实测 109ms vs 26ms）。"""
    return {
        "docs": [{"name": d["name"], "path": d["path"], "summary": d["summary"],
                  "kind": d["kind"], "status": d["status"], "trust": d["trust"],
                  "verified_at": d["verified_at"], "source": d["source"],
                  "n": dict(d["n"]), "d": dict(d["d"]),
                  "b": dict(d["b"]), "len": d["len"]} for d in idx.docs],
        "idf": dict(idx.idf), "avgdl": idx.avgdl, "n_docs": idx.n_docs,
    }

def _from_plain(data: dict) -> "Index":
    idx = Index.__new__(Index)
    idx.docs = data["docs"]
    idx.idf = data["idf"]
    idx.avgdl = data["avgdl"]
    idx.n_docs = data["n_docs"]
    return idx

def _file_sig():
    """(文件名, mtime_ns, size) 列表：索引缓存的有效性判据。"""
    d = entries_dir()
    if not d.is_dir():
        return []
    sig = []
    for path in sorted(d.glob("*.md")):
        try:
            st = path.stat()
            sig.append((path.name, st.st_mtime_ns, st.st_size))
        except OSError:
            continue
    return sig

def _cache_file() -> Path:
    return data_home() / "cache" / "index.pkl"

def get_index(force: bool = False) -> Index:
    """优先读缓存；失效判据是全部文件的 (mtime, size)，原地保存也能发现。"""
    global _INDEX
    if _INDEX is not None and not force:
        return _INDEX
    sig = _file_sig()
    cache = _cache_file()
    if not force:
        try:
            with open(cache, "rb") as fh:
                blob = pickle.load(fh)
            if blob.get("sig") == sig and all("trust" in d for d in blob["data"]["docs"]):
                _INDEX = _from_plain(blob["data"])
                return _INDEX
        except Exception:
            pass
    entries, _ = load_entries()
    _INDEX = Index(entries)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump({"sig": sig, "data": _to_plain(_INDEX)}, fh, protocol=4)
        tmp.replace(cache)
    except Exception:
        pass
    return _INDEX


# ── 日志（自优化的燃料：注入 / miss / show / feedback）────────────────────
# 默认不落原始 prompt：prompt 可能含密钥、邮箱、敏感路径。
# 只记录 UTC 时间、会话指纹、命中条目、门控原因与查询指纹；
# 调试预览必须显式开启，且仍然经过脱敏。
LOG_DENY_KEYS = frozenset({"query", "prompt", "note", "content", "text", "message"})

def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]

def _redact(text: str) -> str:
    """对任意文本套用脱敏规则；sanitize / 日志预览 / stats 共用。"""
    for pat, repl in _REDACT:
        text = pat.sub(repl, text)
    return text

def _mask_sample(value) -> str:
    """审计输出不回显完整敏感值；先脱敏，再对长样本做首尾遮蔽。"""
    text = _redact(str(value))
    return text if len(text) <= 24 else text[:10] + "…" + text[-6:]

def _text_log_fields(prefix: str, text: str) -> dict:
    fields = {f"{prefix}_sha256": _fingerprint(text), f"{prefix}_len": len(text)}
    if os.environ.get("CAIRN_LOG_QUERY_PREVIEW", "").strip() == "1":
        fields[f"{prefix}_preview"] = _redact(text.replace("\n", " "))[:120]
    return fields

def _safe_log_value(value):
    if isinstance(value, str):
        return _redact(value)[:300]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_safe_log_value(v) for v in value[:20]]
    if isinstance(value, dict):
        return {str(k): _safe_log_value(v) for k, v in value.items()
                if str(k).lower() not in LOG_DENY_KEYS}
    return str(value)[:300]

def _append_log(kind: str, payload: dict) -> None:
    try:
        d = log_dir()
        d.mkdir(parents=True, exist_ok=True)
        rec = {"ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
               "event": kind}
        for key, value in payload.items():
            name = str(key)
            if name.lower() in LOG_DENY_KEYS:
                continue
            rec[name] = _safe_log_value(value)
        with open(d / f"{kind}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 日志失败绝不能拖挂 hook

def _session_file(sid: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)[:64] or "default"
    return log_dir() / f"session-{safe}.json"

def _load_seen(sid: str) -> set:
    f = _session_file(sid)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if time.time() - data.get("ts", 0) > 12 * 3600:
            return set()
        return set(data.get("seen", []))
    except Exception:
        return set()

def _save_seen(sid: str, seen: set) -> None:
    try:
        f = _session_file(sid)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"ts": time.time(), "seen": sorted(seen)},
                                ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ── 卡片渲染 ────────────────────────────────────────────────────────────
def render_cards(hits, max_chars: int = MAX_CARD_CHARS) -> str:
    lines = ["【cairn】可能有用的既往经验（按相关度排序）："]
    used = len(lines[0])
    for norm, score, matched, d_matched, doc in hits:
        line = f"- {doc['name']}：{doc['summary']} → entries/{doc['path']}"
        if used + len(line) > max_chars and len(lines) > 1:
            break
        if len(line) > max_chars:
            line = line[:max_chars - 20] + "…（已截断）"
        lines.append(line)
        used += len(line)
    lines.append("需要全文用 `cairn show <name>`；都不相关就忽略本提示。")
    return "\n".join(lines)

def contract_reason(doc) -> str:
    """不可自动注入的原因；可注入时返回空串。"""
    if doc.get("status") != "active":
        return f"status={doc.get('status')}"
    if doc.get("trust") != "verified":
        return f"trust={doc.get('trust')}"
    if not doc.get("source"):
        return "缺 source"
    if not DATE_RE.match(doc.get("verified_at") or ""):
        return "verified_at 无效"
    return ""

def is_injectable(doc) -> bool:
    """Contract v0: active + verified + source + verified_at。"""
    return not contract_reason(doc)

def gate(results, min_score: float = DEFAULT_MIN_SCORE,
         min_cover: float = DEFAULT_MIN_COVER,
         min_margin: float = DEFAULT_MIN_MARGIN,
         max_cards: int = MAX_CARDS, q_len: int = 0, report=None):
    """契约准入 + 三道门：分数、覆盖率、领先幅度。

    覆盖率 = 命中词数 / query 词数；领先幅度 = 第一名 / 第二名。
    report 非 None 时追加 (候选, 原因)，explain 与 hook 共用同一套判断。
    """
    def note(rows, why):
        if report is not None:
            report.extend((r, why) for r in rows)
    q_len = max(q_len or 1, 1)
    ok = [r for r in results if is_injectable(r[4])]
    note([r for r in results if not is_injectable(r[4])], "ineligible")
    if not ok:
        return []
    top, second = ok[0][0], (ok[1][0] if len(ok) > 1 else 0.0)
    if top < min_score:
        note(ok, "low_score")
        return []
    if top < min_margin * max(second, 1e-9):
        note(ok, "low_margin")
        return []
    out = []
    for r in ok:
        why = ("low_score" if r[0] < min_score else
               "low_cover" if r[2] / q_len < min_cover else
               "over_limit" if len(out) >= max_cards else "hit")
        if why == "hit":
            out.append(r)
        note([r], why)
    return out

def emit(text: str, fmt: str) -> None:
    if fmt == "claude":
        payload = {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": text}}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    elif fmt == "codex":
        sys.stdout.write(json.dumps({"systemMessage": text}, ensure_ascii=False))
    elif fmt == "json":
        sys.stdout.write(json.dumps({"cairn": text}, ensure_ascii=False))
    else:
        sys.stdout.write(text + "\n")
    sys.stdout.flush()

def extract_prompt(data) -> str:
    """从平台 stdin 里挖出用户 prompt，兼容几种常见嵌套。"""
    if not isinstance(data, dict):
        return ""
    for key in ("prompt", "user_prompt", "userPrompt", "message", "content", "text"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, dict):
            for sub in ("text", "content", "message"):
                if isinstance(val.get(sub), str) and val[sub].strip():
                    return val[sub]
    props = data.get("properties")
    if isinstance(props, dict):
        return extract_prompt(props)
    return ""


# ── 命令实现 ────────────────────────────────────────────────────────────
def cmd_recall(args) -> int:
    idx = get_index()
    results = idx.search(args.query, limit=args.limit)
    if args.raw:
        for norm, score, matched, d_matched, doc in results[:args.limit]:
            print(f"norm={norm:.2f} m={matched}/desc={d_matched}  {doc['name']}  "
                  f"[{doc.get('status')}/{doc.get('trust')}]  —  {doc['summary'][:70]}")
        if not results:
            print("[无结果]")
        return 0
    hits = gate(results, args.min_score, args.min_cover, args.min_margin,
                max_cards=args.limit, q_len=len(tokenize(args.query)))
    if not hits:
        print("[无相关条目]" + ("（有候选但未通过契约/门控；用 --raw 查看）" if results else ""))
        return 1
    print(render_cards(hits))
    return 0

def cmd_explain(args) -> int:
    """解释一次检索的候选/分数/契约/门控；只读，不写日志与会话状态。"""
    idx = get_index()
    qn = len(tokenize(args.query))
    report = []
    hits = gate(idx.search(args.query, limit=20), args.min_score, args.min_cover,
                args.min_margin, max_cards=args.limit, q_len=qn, report=report)
    print(f"query: {args.query}｜候选 {len(report)} 条｜会注入 {len(hits)} 条")
    print(f"门: score≥{args.min_score:.2f} cover≥{args.min_cover:.0%} "
          f"margin≥{args.min_margin:.2f}x")
    for (norm, _, matched, _, doc), why in sorted(report, key=lambda x: -x[0][0]):
        extra = "  " + contract_reason(doc) if why == "ineligible" else ""
        tag = "INJECT" if why == "hit" else why
        print(f"  [{tag}] {doc['name']}  norm={norm:.2f} cover={matched}/{qn}"
              f"{extra}  —  {doc['summary'][:40]}")
    if not hits:
        print("[SILENT] 没有条目会进入上下文")
    return 0 if hits else 1

def cmd_show(args) -> int:
    path = entries_dir() / f"{args.name}.md"
    if not SLUG_RE.match(args.name) or not path.is_file():
        print(f"[FAIL] 没有条目：{args.name}", file=sys.stderr)
        return 1
    _append_log("show", {"slug": args.name})
    sys.stdout.write(path.read_text(encoding="utf-8"))
    return 0

def cmd_add(args) -> int:
    name = args.name or ""
    if not name:
        # 没给 slug 就用摘要哈希，保证可复现
        name = "entry-" + hashlib.sha1(
            (args.summary or "").encode("utf-8")).hexdigest()[:8]
    if not SLUG_RE.match(name):
        print(f"[FAIL] name 必须是 kebab-case：{name}", file=sys.stderr)
        return 2
    body = args.body
    if body == "-" or (body is None and not sys.stdin.isatty()):
        body = sys.stdin.read()
    body = (body or "").strip()
    if not args.summary:
        print("[FAIL] 缺 --summary（检索全靠它）", file=sys.stderr)
        return 2
    if not body:
        print("[FAIL] 正文为空（用位置参数或 stdin 传入）", file=sys.stderr)
        return 2
    if args.trust == "verified" and not (args.source and args.source.strip()
                                         and args.verified_at
                                         and DATE_RE.match(args.verified_at)):
        print("[FAIL] trust=verified 需要 --source 与 --verified-at YYYY-MM-DD", file=sys.stderr)
        return 2

    d = entries_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.md"
    if path.exists() and not args.force:
        print(f"[FAIL] 已存在：{path}（加 --force 覆盖）", file=sys.stderr)
        return 1
    today = date.today().isoformat()
    fm = {"name": name, "summary": args.summary.strip(),
          "kind": args.kind, "updated": args.updated or today,
          "status": args.status, "trust": args.trust}
    if args.scope:
        fm["scope"] = args.scope.strip()
    if args.source:
        fm["source"] = args.source.strip()
    if args.verified_at:
        fm["verified_at"] = args.verified_at
    text = "---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n---\n\n" + body + "\n"
    path.write_text(text, encoding="utf-8")
    global _INDEX
    _INDEX = None
    e, err = read_entry(path)
    if err:
        print(f"[FAIL] 写入后自检失败：{err}", file=sys.stderr)
        return 1
    problems, warnings = check_entry(e, path.name)
    print(f"[OK] 已写入 {path}")
    for msg in problems:
        print("  [ERROR] " + msg)
    for msg in warnings:
        print("  [WARN] " + msg)
    return 1 if problems else 0

def cmd_ls(args) -> int:
    entries, errors = load_entries()
    if args.md:
        print("# cairn 索引（自动生成，不要手改）\n")
        for kind in KINDS:
            group = [e for e in entries if e["kind"] == kind]
            if not group:
                continue
            print(f"## {kind}（{len(group)}）\n")
            for e in sorted(group, key=lambda x: x["name"]):
                print(f"- [{e['summary'][:60]}](entries/{e['path']}) — {e['name']}")
            print()
        return 0
    for kind in KINDS:
        group = [e for e in entries if e["kind"] == kind]
        print(f"{kind}（{len(group)}）")
        for e in sorted(group, key=lambda x: x["name"]):
            print(f"  {e['name']:<52} {e['summary'][:60]}")
    if errors:
        print(f"\n[WARN] {len(errors)} 个文件读不出（跑 cairn lint 看详情）")
    return 0

def check_entry(e, filename: str):
    """单条目检查，返回 (errors, warnings)。warnings 不影响退出码。"""
    problems, warnings = [], []
    fm = e["fm"]
    missing = [k for k in REQUIRED if not fm.get(k)]
    if missing:
        problems.append(f"缺必填字段 {', '.join(missing)}")
    name = e["name"]
    if not SLUG_RE.match(name):
        problems.append(f"name 不是 kebab-case：{name}")
    if filename != f"{name}.md":
        problems.append(f"name({name}) 与文件名({filename}) 不一致")
    if e["kind"] and e["kind"] not in KINDS:
        problems.append(f"kind='{e['kind']}' 不在 {list(KINDS)}")
    if e["updated"] and not DATE_RE.match(e["updated"]):
        problems.append(f"updated='{e['updated']}' 不是 YYYY-MM-DD")
    if e["status"] not in STATUSES:
        problems.append(f"status='{e['status']}' 不在 {list(STATUSES)}")
    if e["trust"] not in TRUSTS:
        problems.append(f"trust='{e['trust']}' 不在 {list(TRUSTS)}")
    if e["verified_at"] and not DATE_RE.match(e["verified_at"]):
        problems.append(f"verified_at='{e['verified_at']}' 不是 YYYY-MM-DD")
    if e["trust"] == "verified" and not (e["source"] and DATE_RE.match(e["verified_at"])):
        problems.append("trust=verified 需要 source 与有效 verified_at")
    if not is_injectable(e):
        warnings.append("不会自动注入（需 active+verified+source+verified_at）")
    if len(e["summary"]) > 200:
        warnings.append(f"summary 过长（{len(e['summary'])} > 200 字符）")
    if len(e["body"].splitlines()) > 80:
        warnings.append(f"正文 {len(e['body'].splitlines())} 行（建议 ≤80）")
    extra = [k for k in fm if k not in REQUIRED + OPTIONAL]
    if extra:
        warnings.append(f"未知字段 {extra}（会被忽略）")
    return problems, warnings

def cmd_lint(args) -> int:
    entries, read_errors = load_entries()
    if not entries and not read_errors:
        print("[FAIL] 0 条：库为空或 CAIRN_HOME 指向错误目录")
        return 1
    problems = []
    for fname, err in read_errors:
        problems.append(f"{fname}: {err}")
    seen_names, seen_slugs = Counter(), Counter()
    warnings = []
    slugs = set()
    for e in entries:
        errs, warns = check_entry(e, e["path"])
        for p in errs:
            problems.append(f"{e['path']}: {p}")
        for w in warns:
            warnings.append(f"{e['path']}: {w}")
        seen_names[e["name"]] += 1
        seen_slugs[e["slug"]] += 1
        slugs.add(e["slug"])
        slugs.add(e["name"])
    for name, n in seen_names.items():
        if n > 1:
            problems.append(f"重名：{name} 出现 {n} 次")
    for slug, n in seen_slugs.items():
        if n > 1:
            problems.append(f"重文件：{slug}.md 出现 {n} 次")
    for e in entries:
        for m in LINK_RE.finditer(e["body"] + e["summary"]):
            target = m.group(1).strip()
            if target not in slugs and f"{target}" not in slugs:
                problems.append(f"{e['path']}: [[{target}]] 指向不存在的条目")
    print(f"[FAIL] {len(problems)} 项问题（{len(entries)} 条）" if problems
          else f"[PASS] {len(entries)} 条全部通过")
    for p in problems:
        print("  - " + p)
    for w in warnings:
        print("  [warn] " + w)
    return 1 if problems else 0

def _slugify(stem: str) -> str:
    """文件名 → kebab-case；纯非 ASCII 时退化为稳定哈希后缀。"""
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or "entry-" + hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8]

def cmd_import(args) -> int:
    """导入任意 markdown 目录：只认 frontmatter，字段归一，默认 quarantine。

    文件名转 kebab-case；导入后自动跑 lint，避免留下脏库。
    """
    src = Path(args.src).expanduser()
    if not src.is_dir():
        print(f"[FAIL] 目录不存在：{src}", file=sys.stderr)
        return 2
    skip_re = re.compile(args.exclude) if args.exclude else None
    dst = entries_dir()
    if not args.dry_run:
        dst.mkdir(parents=True, exist_ok=True)
    took, skipped, mapped = 0, [], []
    for path in sorted(src.rglob("*.md")):
        if path.name.upper().startswith(("README", "INDEX", "CHANGELOG")):
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        fm, body, err = split_frontmatter(raw)
        if fm is None:
            skipped.append((path.name, err or "无 frontmatter"))
            continue
        summary = (fm.get("summary") or fm.get("description") or "").strip()
        if not summary:
            skipped.append((path.name, "缺 summary/description"))
            continue
        kind = (fm.get("kind") or "").strip()
        if kind not in KINDS:
            kind = {"pitfall": "lesson", "tool": "method", "workflow": "method"}.get(
                (fm.get("type") or "").strip().lower(), "lesson")
        updated = (fm.get("updated") or fm.get("verified") or fm.get("date")
                   or date.today().isoformat()).strip()
        if not DATE_RE.match(updated):
            skipped.append((path.name, f"非法日期：{updated}"))
            continue
        scope = (fm.get("scope") or fm.get("topic") or "").strip()
        if skip_re and skip_re.search(f"{path.stem} {summary}"):
            skipped.append((path.name, "匹配排除规则"))
            continue
        slug = _slugify(path.stem)
        target = dst / f"{slug}.md"
        if target.exists() and not args.force:
            skipped.append((path.name, "目标已存在"))
            continue
        if args.dry_run:
            print(f"[DRY] {path.name} → {slug}.md")
            took += 1
            continue
        out = {"name": slug, "summary": summary, "kind": kind, "updated": updated,
               "status": "active", "trust": "quarantined"}
        if scope:
            out["scope"] = scope
        if fm.get("source"):
            out["source"] = fm["source"].strip()
        target.write_text("---\n" + "\n".join(f"{k}: {v}" for k, v in out.items())
                          + "\n---\n\n" + body.lstrip("\n"), encoding="utf-8")
        took += 1
        if fm.get("description") or fm.get("type") or fm.get("topic") or fm.get("verified"):
            mapped.append(path.stem)
    print(f"[{'DRY' if args.dry_run else 'OK'}] 导入 {took} 条 → {dst}")
    if mapped:
        print(f"[MAP] {len(mapped)} 条字段已归一（description/type/topic/verified → 本库 schema）")
    if skipped:
        print(f"[SKIP] {len(skipped)} 条：")
        for name, why in skipped[:15]:
            print(f"  - {name}: {why}")
        if len(skipped) > 15:
            print(f"  … 另有 {len(skipped) - 15} 条")
    return 0 if args.dry_run else cmd_lint(args)

def cmd_prune_links(args) -> int:
    """删除指向不存在条目的 [[双链]]；宁可删链接也不放宽 lint。"""
    entries, _ = load_entries()
    slugs = {e["slug"] for e in entries} | {e["name"] for e in entries}
    changed = 0
    for e in entries:
        dead = [m.group(1) for m in LINK_RE.finditer(e["body"])
                if m.group(1).strip() not in slugs]
        if not dead:
            continue
        path = entries_dir() / e["path"]
        text = path.read_text(encoding="utf-8")
        for target in set(dead):
            text = re.sub(r"\s*\[\[" + re.escape(target) + r"\]\]", "", text)
        path.write_text(text, encoding="utf-8")
        changed += 1
    global _INDEX
    _INDEX = None
    print(f"[OK] 清理了 {changed} 个文件的死链")
    return 0

def cmd_hook(args) -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    prompt = extract_prompt(data)
    if not prompt.strip():
        return 0
    sid = str(data.get("session_id") or os.environ.get("CAIRN_SESSION") or "default")
    session = _fingerprint(sid)
    qlog = _text_log_fields("query", prompt)
    seen = _load_seen(sid)
    idx = get_index()
    results = idx.search(prompt, limit=20)
    hits = [h for h in gate(results, args.min_score, args.min_cover, args.min_margin,
                            q_len=len(tokenize(prompt))) if h[4]["name"] not in seen]
    reason = ("ineligible" if results and not any(is_injectable(r[4]) for r in results)
              else "below_gate")
    if not hits:
        if results:
            _append_log("miss", {"reason": reason, "session": session,
                                 "top": results[0][4]["name"], "norm": round(results[0][0], 3),
                                 **qlog})
        else:
            _append_log("miss", {"reason": "no_hit", "session": session, **qlog})
        return 0
    seen.update(h[4]["name"] for h in hits)
    _save_seen(sid, seen)
    _append_log("inject", {"session": session,
                           "slugs": [h[4]["name"] for h in hits],
                           "norms": [round(h[0], 3) for h in hits],
                           **qlog})
    emit(render_cards(hits), args.format)
    return 0

def cmd_feedback(args) -> int:
    note = (args.note or "").strip()
    payload = {"slug": args.name, "signal": args.signal}
    if note:
        payload.update(_text_log_fields("note", note))
    _append_log("feedback", payload)
    print(f"[OK] 已记录 {args.name}: {args.signal}")
    return 0

# 审计规则：(名称, 正则, 级别, 说明)
_AUDIT = (
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "critical", "私钥"),
    ("cloud-key", r"\b(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,})\b",
     "critical", "云/平台凭据"),
    ("api-key", r"\bsk-[A-Za-z0-9]{20,}\b", "critical", "API key"),
    ("bearer", r"Bearer [A-Za-z0-9._-]{24,}", "critical", "Bearer token"),
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "high", "邮箱"),
    ("home-path", r"(C:\\{1,4}Users\\{1,4}[A-Za-z0-9_.-]+|/home/[A-Za-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+)",
     "high", "绝对路径含用户名"),
    ("private-ip", r"\b(?:10|192\.168|172\.(?:1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}\b",
     "medium", "内网 IP"),
    ("business-figure", r"\b\d{1,3}(?:,\d{3}){2,}\b|\d+\.\d+\s*亿", "medium", "业务数字"),
)

_REDACT = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "<private-key>"),
    (re.compile(r"\b(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,})\b"),
     "<credential>"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "<api-key>"),
    (re.compile(r"\bBearer [A-Za-z0-9._-]{24,}"), "Bearer <token>"),
    (re.compile(r"(C:\\{1,4}Users\\{1,4})[A-Za-z0-9_.-]+"), r"\1<user>"),
    (re.compile(r"(/home/)[A-Za-z0-9_.-]+"), r"\1<user>"),
    (re.compile(r"(/Users/)[A-Za-z0-9_.-]+"), r"\1<user>"),
    (re.compile(r"\b\d{1,3}(?:,\d{3}){2,}\b"), "<n>"),
    (re.compile(r"\d+\.\d+\s*亿"), "<n>亿"),
    (re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}\b"), "<ip>"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
)

def _atomic_write_text(path: Path, text: str) -> None:
    """先写同目录临时文件，再原子替换；失败不留下半截目标文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
        tmp_name = ""
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

def cmd_sanitize(args) -> int:
    """复制一份并替换可识别信息，原库不动；默认不覆盖，先读后原子写。"""
    source_dir = entries_dir().resolve()
    out = Path(args.out).expanduser().resolve()
    if out == source_dir or out.is_relative_to(source_dir):
        print("[FAIL] 输出目录不能等于或位于 entries/ 内；原库不会被改动",
              file=sys.stderr)
        return 2

    entries, _ = load_entries()
    plans = []
    for e in entries:
        target = (out / "entries" / e["path"]).resolve()
        if not target.is_relative_to(out):
            print(f"[FAIL] 非法目标路径：{target}", file=sys.stderr)
            return 2
        if target.is_relative_to(source_dir):
            print("[FAIL] 目标路径落在原库 entries/ 内；拒绝覆盖", file=sys.stderr)
            return 2
        if target.exists() and not getattr(args, "force", False):
            print(f"[FAIL] 目标已存在：{target}（加 --force 覆盖）", file=sys.stderr)
            return 1
        plans.append((e, target))

    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[FAIL] 无法创建输出目录：{exc}", file=sys.stderr)
        return 2

    prepared = []
    for e, target in plans:
        try:
            text = (entries_dir() / e["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[FAIL] 读不出 {e['path']}：{exc}", file=sys.stderr)
            return 1
        new, hits = text, 0
        for pat, repl in _REDACT:
            new, n = pat.subn(repl, new)
            hits += n
        prepared.append((target, new, hits))

    changed, total_hits = 0, 0
    for target, new, hits in prepared:
        try:
            _atomic_write_text(target, new)
        except OSError as exc:
            print(f"[FAIL] 写入失败 {target}：{exc}", file=sys.stderr)
            return 1
        if hits:
            changed += 1
            total_hits += hits

    print(f"[OK] {len(entries)} 条 → {out / 'entries'}（{changed} 条被改写，共 {total_hits} 处）")
    print(f"     原库未改动；下一步：CAIRN_HOME={out} cairn audit")
    return 0

def _audit_files():
    """Cairn 管理的持久化数据：entries + log/session + 派生 cache。"""
    d, ld = entries_dir(), log_dir()
    files = [(f"entries/{p.name}", p) for p in sorted(d.glob("*.md"))] if d.is_dir() else []
    if ld.is_dir():
        files += [(f"log/{p.relative_to(ld)}", p) for p in sorted(ld.rglob("*"))
                  if p.is_file() and p.suffix in (".jsonl", ".json")]
    cache = data_home() / "cache" / "index.pkl"
    return files + ([("cache/index.pkl", cache)] if cache.is_file() else [])

def cmd_audit(args) -> int:
    """脱敏体检：只报告不修改；自动改写会毁掉条目语义。"""
    d = entries_dir()
    if not d.is_dir() or not any(d.glob("*.md")):
        print("[FAIL] 0 条经验：库为空或 CAIRN_HOME 指向错误目录")
        return 1
    targets = _audit_files()
    levels = {"critical": 0, "high": 0, "medium": 0}
    findings = {}
    read_errors = []
    for display, path in targets:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            read_errors.append((display, str(exc)))
            continue
        text = raw.decode("utf-8", "replace")
        for name, pat, level, desc in _AUDIT:
            hits = re.findall(pat, text)
            if not hits:
                continue
            uniq = sorted({h if isinstance(h, str) else h[0] for h in hits})
            samples = [_mask_sample(u) for u in uniq[:3]]
            findings.setdefault(level, []).append((display, name, samples))
            levels[level] += 1

    for display, err in read_errors:
        print(f"[WARN] 读不出 {display}: {err}")
    if not any(levels.values()):
        if read_errors:
            print(f"[FAIL] {len(read_errors)} 个文件无法读取，不能判定安全")
            return 1
        print(f"[PASS] {len(targets)} 个受管文件未发现敏感内容")
        return 0

    for level in ("critical", "high", "medium"):
        for path, name, samples in findings.get(level, []):
            print(f"[{level}] {path}: {name} → {samples}")
    print(f"\n统计：{len(targets)} 个受管文件中 critical "
          f"{levels['critical']} 项、high {levels['high']} 项、medium {levels['medium']} 项")
    if levels["critical"] or levels["high"]:
        print("[FAIL] 存在 critical/high，公开前必须处理")
        return 1
    if read_errors:
        print("[FAIL] 有文件无法读取，不能判定安全")
        return 1
    print("[WARN] 仅 medium（内网 IP/业务数字），自行判断是否公开")
    return 0

def cmd_nudge(args) -> int:
    """Stop 钩子用：会话收尾提醒一次；是否沉淀交给 agent 自己判断。"""
    text = ("【cairn】这轮若有跨项目可复用的教训，用 "
            "`cairn add --name <slug> --summary \"...\"` 落一条；"
            "已经写过的忽略本提示。")
    emit(text, args.format)
    return 0

def cmd_stats(args) -> int:
    d = log_dir()
    counts = Counter()
    missed = Counter()
    injected = Counter()
    previews = {}
    for kind in ("inject", "miss", "show", "feedback"):
        f = d / f"{kind}.jsonl"
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            counts[kind] += 1
            if kind == "inject":
                for s in rec.get("slugs", []):
                    injected[s] += 1
            if kind == "miss":
                fp = rec.get("query_sha256")
                if not fp and isinstance(rec.get("query"), str):
                    fp = _fingerprint(rec["query"])
                fp = str(fp or "unknown")
                missed[fp] += 1
                if fp not in previews:
                    preview = rec.get("query_preview")
                    if not preview and isinstance(rec.get("query"), str):
                        preview = _redact(rec["query"].replace("\n", " "))[:120]
                    if preview:
                        previews[fp] = str(preview)[:120]
    total_hook = counts["inject"] + counts["miss"]
    rate = counts["inject"] / total_hook if total_hook else 0
    print(f"注入 {counts['inject']} 次｜miss {counts['miss']} 次｜show {counts['show']} 次"
          f"｜有卡片比例 {rate:.0%}")
    if injected:
        print("\n最常注入：")
        for s, n in injected.most_common(8):
            print(f"  {n:3}  {s}")
    if missed:
        print("\n最常 miss 的 query 指纹（→ 库的缺口）：")
        for fp, n in missed.most_common(8):
            line = f"  {n:3}  {fp}"
            if getattr(args, "show_queries", False) and fp in previews:
                line += f"  |  {previews[fp]}"
            print(line)
    return 0

def cmd_eval(args) -> int:
    """回归闸门：同时报排序（召回）与产品行为（注入），别用一个数字糊弄自己。"""
    idx = get_index()
    qfile = Path(args.queries)
    if not qfile.is_file():
        print(f"[FAIL] 评测集不存在：{qfile}", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in qfile.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]
    rank1 = rank3 = inj1 = inj3 = injected_n = 0
    mrr = 0.0
    card_chars = []
    misses = []
    for row in rows:
        results = idx.search(row["query"], limit=len(idx.docs) or 1)
        order = [d["name"] for _, _, _, _, d in results]
        expect = row["expect"]
        rank = next((i for i, name in enumerate(order, 1) if name in expect), None)
        rank1 += rank == 1
        rank3 += bool(rank and rank <= 3)
        mrr += 1.0 / rank if rank else 0.0
        hits = gate(results, args.min_score, args.min_cover, args.min_margin,
                    q_len=len(tokenize(row["query"])))
        injected = [h[4]["name"] for h in hits]
        inj1 += bool(injected) and injected[0] in expect
        inj3 += any(x in expect for x in injected)
        card_chars.append(len(render_cards(hits)) if hits else 0)
        injected_n += bool(hits)
        if not any(x in expect for x in injected):
            misses.append((row["query"], expect[0], order[:2], injected[:2]))

    neg_rows = []
    neg_file = Path(args.negatives)
    if neg_file.is_file():
        neg_rows = [json.loads(l) for l in neg_file.read_text(encoding="utf-8").splitlines()
                    if l.strip() and not l.startswith("#")]
    noise = sum(1 for r in neg_rows
                if gate(idx.search(r["query"]), args.min_score, args.min_cover,
                        args.min_margin, q_len=len(tokenize(r["query"]))))

    n = len(rows) or 1
    print(f"正例 {n} 条")
    print(f"  召回@1 {rank1 / n:.1%}  召回@3 {rank3 / n:.1%}  MRR {mrr / n:.3f}   ← 排序质量")
    print(f"  注入@1 {inj1 / n:.1%}  注入@3 {inj3 / n:.1%}                   ← 实际进入上下文")
    if neg_rows:
        print(f"负例 {len(neg_rows)} 条｜误触发 {noise / len(neg_rows):.1%}"
              f"（没相关经验却注入了卡片）")
    print(f"平均注入 {sum(card_chars) / n:.0f} 字符 ≈ {sum(card_chars) / n / 2:.0f} tokens"
          "（每 query；未注入计 0）")
    if injected_n:
        print(f"实际注入 {injected_n}/{n} 次：平均 {sum(card_chars) / injected_n:.0f} 字符"
              f" ≈ {sum(card_chars) / injected_n / 2:.0f} tokens/次")
    if misses:
        print(f"\n未注入正确条目的 {len(misses)} 条：")
        for q, exp, got, inj in misses[:8]:
            print(f"  Q: {q[:40]}\n     期望 {exp}\n     排序 {got} / 注入 {inj}")
    ok = (inj3 / n) >= args.min_inject and (not neg_rows or noise / len(neg_rows) <= args.max_noise)
    print(f"\n[{'PASS' if ok else 'FAIL'}] 门槛 注入@3≥{args.min_inject:.0%} 误触发≤{args.max_noise:.0%}")
    return 0 if ok else 1


# ── CLI ─────────────────────────────────────────────────────────────────
def add_gate_args(s) -> None:
    for name, default in (("min-score", DEFAULT_MIN_SCORE),
                          ("min-cover", DEFAULT_MIN_COVER),
                          ("min-margin", DEFAULT_MIN_MARGIN)):
        s.add_argument(f"--{name}", type=float, default=default)

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cairn", description="极简经验库")
    p.add_argument("--version", action="version", version=f"cairn {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("recall", help="手动检索")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=3)
    s.add_argument("--raw", action="store_true", help="打印原始分数")
    add_gate_args(s)
    s.set_defaults(func=cmd_recall)

    s = sub.add_parser("explain", help="解释检索的契约准入与门控")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=3)
    add_gate_args(s)
    s.set_defaults(func=cmd_explain)

    s = sub.add_parser("show", help="打印条目全文（记一次命中）")
    s.add_argument("name")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("add", help="写入一条经验")
    s.add_argument("body", nargs="?", help="正文；用 - 或管道传 stdin")
    s.add_argument("--name")
    s.add_argument("--summary")
    s.add_argument("--kind", default="lesson", choices=KINDS)
    s.add_argument("--scope")
    s.add_argument("--source")
    s.add_argument("--status", choices=STATUSES, default="active")
    s.add_argument("--trust", choices=TRUSTS, default="unverified")
    s.add_argument("--verified-at")
    s.add_argument("--updated")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("ls", help="列出条目")
    s.add_argument("--md", action="store_true", help="输出自动生成的索引")
    s.set_defaults(func=cmd_ls)

    s = sub.add_parser("lint", help="校验全库")
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("import", help="导入任意 markdown 条目目录")
    s.add_argument("src", help="源目录（递归找 *.md）")
    s.add_argument("--exclude", help="排除正则（匹配文件名或 summary）")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true", help="只打印计划，不写库")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("prune-links", help="删除指向不存在条目的 [[双链]]")
    s.set_defaults(func=cmd_prune_links)

    s = sub.add_parser("hook", help="平台 hook 入口（stdin JSON → stdout JSON）")
    s.add_argument("--format", default="claude",
                   choices=("claude", "codex", "text", "json"))
    add_gate_args(s)
    s.set_defaults(func=cmd_hook)

    s = sub.add_parser("eval", help="离线回归闸门")
    s.add_argument("--queries", default=str(Path(__file__).resolve().parent / "eval" / "queries.jsonl"))
    s.add_argument("--negatives", default=str(Path(__file__).resolve().parent / "eval" / "negatives.jsonl"))
    s.add_argument("--min-inject", type=float, default=0.70)
    s.add_argument("--max-noise", type=float, default=0.10)
    add_gate_args(s)
    s.set_defaults(func=cmd_eval)

    s = sub.add_parser("feedback", help="记录某条经验有用/误导")
    s.add_argument("name")
    s.add_argument("--helpful", dest="signal", action="store_const", const="helpful")
    s.add_argument("--harmful", dest="signal", action="store_const", const="harmful")
    s.add_argument("--note")
    s.set_defaults(func=cmd_feedback, signal="neutral")

    s = sub.add_parser("audit", help="脱敏体检（entries + 日志/会话/缓存）")
    s.set_defaults(func=cmd_audit)

    s = sub.add_parser("sanitize", help="复制一份并替换标识/凭据（默认不覆盖）")
    s.add_argument("--out", required=True, help="输出目录（不得等于或位于 entries/ 内）")
    s.add_argument("--force", action="store_true", help="允许覆盖输出目录中已有文件")
    s.set_defaults(func=cmd_sanitize)

    s = sub.add_parser("nudge", help="会话收尾提醒（Stop 钩子用）")
    s.add_argument("--format", default="text", choices=("claude", "codex", "text", "json"))
    s.set_defaults(func=cmd_nudge)

    s = sub.add_parser("stats", help="注入 / miss 统计")
    s.add_argument("--show-queries", action="store_true",
                   help="显示脱敏后的 miss 预览（默认只显示查询指纹）")
    s.set_defaults(func=cmd_stats)
    return p

def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as exc:  # hook 场景绝不阻塞
        if args.cmd == "hook":
            return 0
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

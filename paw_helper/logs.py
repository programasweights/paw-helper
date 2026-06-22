"""Review and ingest paw-helper JSONL logs.

These helpers are intentionally conservative: exact-string deduplication is
automatic, but prefix/near-duplicate collapse and benchmark labels stay manual so
real-traffic benchmarks remain eyeballed artifacts.
"""

from __future__ import annotations

import collections
import json
import pathlib


def load_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def filtered(rows: list[dict], origin: str | None = None, page: str | None = None) -> list[dict]:
    out = rows
    if origin:
        out = [r for r in out if r.get("origin") == origin]
    if page:
        out = [r for r in out if r.get("page") == page]
    return out


def review_text(
    rows: list[dict],
    feedback_rows: list[dict] | None = None,
    top: int = 20,
    source: str = "queries.jsonl",
) -> str:
    lines = [f"=== Questions ({len(rows)}) from {source} ==="]
    if rows:
        by_type = collections.Counter(r.get("result_type") for r in rows)
        by_route = collections.Counter(r.get("route") for r in rows)
        by_origin = collections.Counter((r.get("origin") or r.get("page") or "?") for r in rows)
        fallbacks = [r for r in rows if r.get("fallback")]
        lines.append(f"result types: {dict(by_type)}")
        lines.append(f"routes:       {dict(by_route)}")
        lines.append(f"by origin:    {dict(by_origin)}")
        lines.append(f"fallback rate: {len(fallbacks)}/{len(rows)} = {len(fallbacks) / len(rows):.0%}")

        lines.append(f"\n--- Fallback / unanswered queries ({len(fallbacks)}) - polish targets ---")
        for r in fallbacks:
            src = r.get("origin") or r.get("page") or "?"
            lines.append(f"  - {r.get('query')!r}  (origin={src}, route={r.get('route')}, validator={r.get('validator')})")

        lines.append(f"\n--- Top {top} questions ---")
        freq = collections.Counter((r.get("query") or "").strip().lower() for r in rows)
        for q, c in freq.most_common(top):
            lines.append(f"  {c:4d}  {q!r}")

    feedback_rows = feedback_rows or []
    lines.append(f"\n=== Feedback ({len(feedback_rows)}) ===")
    for r in feedback_rows[-top:]:
        email = f" <{r.get('email')}>" if r.get("email") else ""
        src = r.get("origin") or r.get("page_url") or ""
        src = f" ({src})" if src else ""
        lines.append(f"  [{r.get('ts', '')[:19]}]{email}{src} {r.get('text')!r}")
    return "\n".join(lines)


def ingest_text(rows: list[dict], batch: int = 20) -> str:
    by_key: dict[str, dict] = collections.OrderedDict()
    for r in rows:
        q = (r.get("query") or "").strip()
        if not q:
            continue
        key = q.lower()
        info = by_key.setdefault(key, {"query": q, "routes": set(), "results": set(), "pages": set(), "origins": set()})
        if r.get("route"):
            info["routes"].add(r["route"])
        if r.get("result_type"):
            info["results"].add(r["result_type"])
        info["pages"].add(r.get("page") or "?")
        info["origins"].add(r.get("origin") or "?")

    uniq = sorted(by_key.values(), key=lambda d: d["query"].lower())
    lines = [
        f"# {len(rows)} log lines -> {len(uniq)} exact-unique queries "
        "(prefix/near-dup + categorization are MANUAL below)\n"
    ]
    for i, info in enumerate(uniq):
        if i % batch == 0:
            lines.append(f"\n----- batch {i // batch + 1} (rows {i + 1}-{min(i + batch, len(uniq))}) -----")
        routes = ",".join(sorted(info["routes"])) or "-"
        results = ",".join(sorted(info["results"])) or "-"
        pages = ",".join(sorted(info["pages"]))
        origins = ",".join(sorted(info["origins"]))
        lines.append(
            f"{i + 1:3}. {info['query']!r:50}  route=[{routes}] "
            f"result=[{results}] page=[{pages}] origin=[{origins}]"
        )
    return "\n".join(lines)

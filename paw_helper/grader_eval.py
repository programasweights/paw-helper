"""Validate a compiled rubric_checker against hand-labeled triples."""

from __future__ import annotations

import pathlib

import yaml

from . import common, grader


def _gold(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v).strip().lower()


def evaluate_cases(gfn, cases: list[dict]) -> dict:
    rows = []
    agree = 0
    false_hit = []
    false_miss = []
    for c in cases:
        gold = _gold(c["gold"])
        pred = "yes" if grader.check_point(gfn, c["q"], c["a"], c["point"]) else "no"
        ok = pred == gold
        agree += ok
        row = {"case": c, "gold": gold, "pred": pred, "ok": ok}
        rows.append(row)
        if not ok and gold == "no":
            false_hit.append(c)
        if not ok and gold == "yes":
            false_miss.append(c)
    return {
        "rows": rows,
        "agree": agree,
        "total": len(cases),
        "false_hit": false_hit,
        "false_miss": false_miss,
    }


def report(result: dict) -> str:
    total = result["total"]
    n_yes = sum(1 for r in result["rows"] if r["gold"] == "yes")
    lines = [f"=== rubric_checker meta-eval ({total} triples; gold yes={n_yes}, no={total - n_yes}) ===\n"]
    for r in result["rows"]:
        c = r["case"]
        flag = "    " if r["ok"] else " ** "
        lines.append(f"{flag}gold={r['gold']:<3} pred={r['pred']:<3} | {c['q'][:34]!r:36} :: {c['point'][:48]}")
    agree = result["agree"]
    denom = max(total, 1)
    lines.append(f"\nAgreement: {agree}/{total} = {agree / denom:.0%}")
    lines.append(f"False HITs (gold=no, pred=yes) - DANGEROUS: {len(result['false_hit'])}")
    for c in result["false_hit"]:
        lines.append(f"   - {c['q']!r} :: {c['point']}  (answer: {c['a'][:60]!r})")
    lines.append(f"False MISSes (gold=yes, pred=no): {len(result['false_miss'])}")
    for c in result["false_miss"]:
        lines.append(f"   - {c['q']!r} :: {c['point']}  (answer: {c['a'][:60]!r})")
    return "\n".join(lines)


def run(meta_path: pathlib.Path | None = None) -> str:
    import programasweights as paw

    path = meta_path or (common.CONTENT_DIR / "bench" / "grader_meta.yaml")
    cases = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    programs = common.load_programs()["programs"]
    if "rubric_checker" not in programs:
        raise SystemExit("rubric_checker not compiled yet; run `paw-helper compile --only rubric_checker`.")
    fn = paw.function(programs["rubric_checker"])
    return report(evaluate_cases(fn, cases))

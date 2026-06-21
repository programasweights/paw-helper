"""Rubric grader built on the rubric_checker PAW program.

Checks an answer against a rubric ONE point at a time (a per-point entailment
check is far more reliable on a small model than asking it to emit a multi-point
verdict, and aggregates cleanly into "which points hit / missed"). Used by
grader_eval.py (to validate the checker) and later by eval.py (to auto-grade the
open-ended benchmark). The grader is offline-only; it is not in the runtime
serving pipeline.
"""

CHECKER_MAX_TOKENS = 4  # "yes" / "no"


def build_input(question: str, answer: str, point: str) -> str:
    """The exact input format the rubric_checker spec was written against."""
    return f"Question: {question}\nAnswer: {answer}\nRequirement: {point}"


def check_point(fn, question: str, answer: str, point: str) -> bool:
    """True if the answer satisfies this single rubric point (HIT)."""
    out = fn(build_input(question, answer, point), max_tokens=CHECKER_MAX_TOKENS, temperature=0.0)
    return out.strip().lower().startswith("yes")


def score(fn, question: str, answer: str, points: list[dict]) -> dict:
    """Score an answer against a rubric (list of {text, required}).

    Returns a scorecard with per-point hits and pass = all REQUIRED points hit.
    """
    results = []
    for p in points:
        text = p["text"] if isinstance(p, dict) else str(p)
        required = p.get("required", True) if isinstance(p, dict) else True
        hit = check_point(fn, question, answer, text)
        results.append({"point": text, "required": required, "hit": hit})
    required = [r for r in results if r["required"]]
    return {
        "results": results,
        "hits": sum(r["hit"] for r in results),
        "n": len(results),
        "required_hits": sum(r["hit"] for r in required),
        "required_n": len(required),
        "passed": all(r["hit"] for r in required),
    }

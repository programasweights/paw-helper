from paw_helper import grader_eval


class FakeRubricFn:
    def __call__(self, text, max_tokens=4, temperature=0.0):
        if "Requirement: good" in text:
            return "yes"
        return "no"


def test_grader_eval_reports_false_hits():
    cases = [
        {"q": "q1", "a": "a1", "point": "good", "gold": "yes"},
        {"q": "q2", "a": "a2", "point": "good", "gold": "no"},
        {"q": "q3", "a": "a3", "point": "bad", "gold": "no"},
    ]

    result = grader_eval.evaluate_cases(FakeRubricFn(), cases)
    out = grader_eval.report(result)

    assert result["agree"] == 2
    assert len(result["false_hit"]) == 1
    assert "False HITs (gold=no, pred=yes) - DANGEROUS: 1" in out

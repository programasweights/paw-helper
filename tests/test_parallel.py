"""Parallel-branch + aggregator unit tests (offline; a stub backend, no model)."""

from paw_helper import common, pipeline


class StubBackend:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}

    def infer(self, name, text, max_tokens):
        return self.outputs.get(name, "")


def _pipe(booted_pack, outputs=None):
    common.set_content_dir(booted_pack)
    return pipeline.Pipeline(inference_backend=StubBackend(outputs))


_ITEM = {"label": "T", "url": "https://piazza.example/t", "description": ""}


def test_aggregate_invisible(booted_pack):
    p = _pipe(booted_pack)
    main = {"result": {"type": "answer", "text": "hi"}, "domain": "site"}
    assert p._aggregate("q", main, []) is main  # nothing relevant -> unchanged


def test_aggregate_augment(booted_pack):
    p = _pipe(booted_pack)
    main = {"result": {"type": "answer", "text": "hi"}, "domain": "site"}
    out = p._aggregate("q", main, [{"name": "piazza", "label": "Related on Piazza", "items": [_ITEM]}])
    assert out["result"]["related"] == [_ITEM]
    assert out["result"]["related_label"] == "Related on Piazza"
    assert out["branches"] == ["piazza"]


def test_aggregate_rescue(booted_pack):
    p = _pipe(booted_pack)
    main = {"result": {"type": "none"}, "domain": "site"}
    out = p._aggregate("q", main, [{"name": "piazza", "label": "Related on Piazza", "items": [_ITEM]}])
    assert out["result"]["type"] == "links"
    assert out["result"]["items"] == [_ITEM]


def test_run_branch_gate_no_skips(booted_pack):
    p = _pipe(booted_pack, {"g": "no"})
    p.programs["g"] = "stub"
    p.search_providers["fake"] = lambda q: [{**_ITEM, "score": 9}]
    assert p._run_branch({"name": "b", "gate": "g", "provider": "fake", "min_score": 1}, "q") is None


def test_run_branch_yes_filters_score_and_caps(booted_pack):
    p = _pipe(booted_pack, {"g": "yes"})
    p.programs["g"] = "stub"
    p.search_providers["fake"] = lambda q: [
        {"label": "A", "url": "a", "score": 9},
        {"label": "B", "url": "b", "score": 0.1},   # below min_score -> dropped
        {"label": "C", "url": "c", "score": 8},
    ]
    r = p._run_branch({"name": "b", "gate": "g", "provider": "fake", "min_score": 1, "max_items": 1}, "q")
    assert [it["label"] for it in r["items"]] == ["A"]  # B filtered, capped at 1


def test_run_branch_selector_reranks(booted_pack):
    """The PAW selector is the precision stage: BM25 recalls 3, the selector keeps
    only the relevant ones (here #1 and #3), order preserved, robust to a false
    positive (#2) the retriever scored high."""
    p = _pipe(booted_pack, {"sel": "1, 3"})
    p.programs["sel"] = "stub"
    p.search_providers["fake"] = lambda q: [
        {"label": "A", "url": "a", "score": 9},
        {"label": "B-false-positive", "url": "b", "score": 8.5},
        {"label": "C", "url": "c", "score": 8},
    ]
    r = p._run_branch({"name": "b", "provider": "fake", "selector": "sel",
                       "min_score": 1, "select_k": 3, "max_items": 2}, "q")
    assert [it["label"] for it in r["items"]] == ["A", "C"]  # B dropped by the selector


def test_run_branch_selector_none_skips(booted_pack):
    """Selector says nothing is relevant -> the branch stays invisible (no surface),
    even though the retriever returned high-scoring candidates."""
    p = _pipe(booted_pack, {"sel": "none"})
    p.programs["sel"] = "stub"
    p.search_providers["fake"] = lambda q: [{"label": "A", "url": "a", "score": 99}]
    assert p._run_branch({"name": "b", "provider": "fake", "selector": "sel",
                          "min_score": 1, "max_items": 2}, "q") is None


def test_run_branch_answerer_synthesizes(booted_pack):
    """selector keeps the relevant thread, then the answerer synthesizes a grounded
    answer from its context. The branch result carries both items and answer."""
    p = _pipe(booted_pack, {"sel": "1", "ans": "The deadline moved to June 25."})
    p.programs["sel"] = p.programs["ans"] = "stub"
    p.search_providers["fake"] = lambda q: [
        {"label": "A1 changes", "url": "a", "score": 9, "context": "deadline extended to June 25"},
        {"label": "noise", "url": "b", "score": 8},
    ]
    r = p._run_branch({"name": "b", "provider": "fake", "selector": "sel", "answerer": "ans",
                       "min_score": 1, "select_k": 2, "max_items": 2}, "what changed")
    assert r["answer"] == "The deadline moved to June 25."
    assert [it["label"] for it in r["items"]] == ["A1 changes"]


def test_run_branch_answerer_decline_not_promoted(booted_pack):
    """If the answerer declines, no `answer` is attached (so it won't be promoted)."""
    p = _pipe(booted_pack, {"sel": "1", "ans": "I don't have that information."})
    p.programs["sel"] = p.programs["ans"] = "stub"
    p.search_providers["fake"] = lambda q: [{"label": "T", "url": "a", "score": 9, "context": "x"}]
    r = p._run_branch({"name": "b", "provider": "fake", "selector": "sel", "answerer": "ans",
                       "min_score": 1, "max_items": 2}, "q")
    assert "answer" not in r and r["items"]  # links remain, but no synthesized answer


def test_run_branch_keep_bypasses_selector(booted_pack):
    """Items marked keep=True bypass the reranker (e.g. a recency list); the selector
    is never consulted for them."""
    p = _pipe(booted_pack, {"sel": "none"})  # selector would reject everything
    p.programs["sel"] = "stub"
    p.search_providers["fake"] = lambda q: [{"label": "newest", "url": "a", "score": 5, "keep": True}]
    r = p._run_branch({"name": "b", "provider": "fake", "selector": "sel",
                       "min_score": 1, "max_items": 2}, "latest posts")
    assert [it["label"] for it in r["items"]] == ["newest"]  # kept despite selector "none"


def test_aggregate_promotes_branch_answer(booted_pack):
    """A synthesized branch answer overrides a generic main answer and becomes primary,
    with the threads as citations."""
    p = _pipe(booted_pack)
    main = {"result": {"type": "answer", "text": "generic A1 dates"}, "domain": "course"}
    out = p._aggregate("q", main, [{"name": "piazza", "label": "From Piazza",
                                    "items": [_ITEM], "answer": "The deadline moved to June 25."}])
    assert out["result"]["type"] == "answer"
    assert out["result"]["text"] == "The deadline moved to June 25."
    assert out["result"]["related"] == [_ITEM]
    assert out["branches"] == ["piazza"]


def test_branches_selection(booted_pack):
    p = _pipe(booted_pack)
    p.search_providers["fake"] = lambda q: []
    dom = p.cfg["domains"]["site"]
    dom["parallel_branches"] = [{"name": "b", "provider": "fake"}]
    assert len(p._branches("site")) == 1                       # no when_page -> always
    dom["parallel_branches"][0]["when_page"] = "course"
    assert p._branches("site") == []                            # when_page mismatch
    dom["parallel_branches"][0]["when_page"] = "site"
    assert len(p._branches("site")) == 1
    dom["parallel_branches"] = [{"name": "b", "provider": "missing"}]
    assert p._branches("site") == []                            # provider not registered


def test_run_aggregates_concurrently(booted_pack, monkeypatch):
    p = _pipe(booted_pack, {"g": "yes"})
    p.programs["g"] = "stub"
    p.search_providers["fake"] = lambda q: [{**_ITEM, "score": 9}]
    p.cfg["domains"]["site"]["parallel_branches"] = [
        {"name": "piazza", "provider": "fake", "gate": "g", "min_score": 1, "result_label": "Related on Piazza"}
    ]
    monkeypatch.setattr(p, "_main", lambda q, page: {"result": {"type": "answer", "text": "main"}, "domain": "site"})
    out = p.run("a real question here", "site")
    assert out["result"]["text"] == "main"
    assert out["result"]["related"] == [_ITEM]
    assert out["branches"] == ["piazza"]

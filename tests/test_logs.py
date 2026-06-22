from paw_helper import logs


def test_filter_by_origin_and_page():
    rows = [
        {"query": "docs", "origin": "https://programasweights.com", "page": "site:paw"},
        {"query": "cv", "origin": "https://yuntiandeng.com", "page": "site"},
    ]

    assert logs.filtered(rows, origin="https://programasweights.com") == [rows[0]]
    assert logs.filtered(rows, page="site") == [rows[1]]


def test_ingest_exact_dedup_only():
    rows = [
        {"query": "Docs", "route": "docs", "result_type": "link", "page": "site:paw", "origin": "https://programasweights.com"},
        {"query": "docs", "route": "docs", "result_type": "link", "page": "site:paw", "origin": "https://programasweights.com"},
        {"query": "documentation", "route": "docs", "result_type": "link", "page": "site:paw", "origin": "https://programasweights.com"},
    ]

    out = logs.ingest_text(rows, batch=10)

    assert "3 log lines -> 2 exact-unique queries" in out
    assert "'Docs'" in out
    assert "'documentation'" in out


def test_review_surfaces_fallbacks():
    rows = [
        {"query": "what is paw", "result_type": "answer", "route": "question", "fallback": False},
        {"query": "unknown", "result_type": "none", "route": "question", "fallback": True, "validator": "no"},
    ]

    out = logs.review_text(rows, top=5)

    assert "fallback rate: 1/2 = 50%" in out
    assert "'unknown'" in out
    assert "polish targets" in out

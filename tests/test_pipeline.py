from paw_helper import common, pipeline


def test_normalize_label():
    assert pipeline.normalize_label("cv", {"cv", "github"}) == "cv"
    assert pipeline.normalize_label("CV.", {"cv"}) == "cv"
    assert pipeline.normalize_label("garbage", {"cv"}) == "question"
    assert pipeline.normalize_label("", {"cv"}) == "question"


def test_cap_input_warns_and_truncates(booted_pack, caplog):
    import logging
    common.set_content_dir(booted_pack)
    p = pipeline.Pipeline()
    p.cfg["token_budget"] = 100  # cap = (100 - max_tokens) * 4 chars
    short = "hello"
    assert p._cap_input("answerer", short, max_tokens=10) == short  # well under cap
    big = "x" * 1000
    with caplog.at_level(logging.WARNING, logger="paw_helper"):
        out = p._cap_input("answerer", big, max_tokens=10)
    assert len(out) == (100 - 10) * 4  # 360 chars
    assert any("input_truncated" in r.message for r in caplog.records)


def test_classifier_redundancy(booted_pack):
    common.set_content_dir(booted_pack)
    p = pipeline.Pipeline()
    p.cfg["domains"]["site"]["classifier_redundancy"] = [
        {"to": "code", "from": ["question", "browser"],
         "any_keywords": [" sdk", "repo"], "unless_keywords": ["install"]},
    ]
    # fires: question + keyword, no exclusion
    assert p._apply_redundancy("site", "where is the python sdk", "question") == "code"
    # excluded by unless_keywords
    assert p._apply_redundancy("site", "how do i install the sdk", "question") == "question"
    # label not in `from`
    assert p._apply_redundancy("site", "the repo", "cv") == "cv"
    # no keyword match
    assert p._apply_redundancy("site", "what is paw", "question") == "question"


def test_resource_item_view_legacy_and_generic():
    # Legacy slide shape: num/topic -> "L{num}: {topic}", description from rr.
    rr = {"item_description": "Lecture slides"}
    legacy = pipeline.Pipeline._resource_item_view({"num": 3, "topic": "Search", "url": "u"}, rr)
    assert legacy == {"label": "L3: Search", "url": "u", "description": "Lecture slides"}
    # Generic shape: provider supplies its own label/description.
    gen = pipeline.Pipeline._resource_item_view(
        {"label": "Python SDK", "url": "g", "description": "pip"}, {"item_description": "x"})
    assert gen == {"label": "Python SDK", "url": "g", "description": "pip"}


def test_is_decline():
    assert pipeline._is_decline("I don't have that information.")
    assert pipeline._is_decline("I'm not sure about that.")
    assert pipeline._is_decline("")
    assert not pipeline._is_decline("Robin is based in Toronto.")


def test_pipeline_boots_and_routes_offline(booted_pack):
    """Pipeline init + single-domain routing needs no model call."""
    common.set_content_dir(booted_pack)
    p = pipeline.Pipeline()
    assert p.available == ["site"]
    assert set(p.links) == {"site"}
    assert "cv" in p.links["site"]
    # One domain -> the router is skipped; resolve_domain returns the page default.
    assert p.resolve_domain("what do you research", "site") == "site"
    assert p.resolve_domain("anything", "unknown-page") == "site"

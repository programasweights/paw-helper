from paw_helper import common, pipeline


def test_normalize_label():
    assert pipeline.normalize_label("cv", {"cv", "github"}) == "cv"
    assert pipeline.normalize_label("CV.", {"cv"}) == "cv"
    assert pipeline.normalize_label("garbage", {"cv"}) == "question"
    assert pipeline.normalize_label("", {"cv"}) == "question"


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

from paw_helper import common


def test_compose_resolves_placeholders(example_dir):
    common.set_content_dir(example_dir)
    for name in ("page_classifier", "answerer", "validator"):
        spec = common.compose_spec(name)
        assert "{{" not in spec, f"{name} has an unresolved placeholder"
    # The classifier inlines link purposes; the answerer inlines the link registry + facts.
    assert "cv" in common.compose_spec("page_classifier").lower()
    answerer = common.compose_spec("answerer")
    assert "robin-park-cv.pdf" in answerer  # LINK_REGISTRY url
    assert "Toronto" in answerer            # FACTS


def test_links_for_spec(example_dir):
    common.set_content_dir(example_dir)
    links = common.links_for_spec("page_classifier")
    assert {"cv", "github", "contact", "feedback"} <= set(links)


def test_set_content_dir_switches_paths(tmp_path, example_dir):
    common.set_content_dir(example_dir)
    assert common.SPECS_DIR == example_dir / "specs"
    common.set_content_dir(tmp_path)
    assert common.SPECS_DIR == tmp_path / "specs"

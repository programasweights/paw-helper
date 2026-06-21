from paw_helper import validate


def test_example_pack_is_valid(example_dir):
    errors, warnings = validate.validate(example_dir)
    assert errors == [], errors
    # No programs.json in the example -> a warning, not an error.
    assert any("programs.json" in w for w in warnings)


def test_missing_files_are_caught(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "schema_version: 1\n"
        "default_domain: site\n"
        "max_tokens: {}\n"
        "domains:\n"
        "  site:\n"
        "    classifier: page_classifier\n"
        "    answerer: answerer\n"
        "    links: links.yaml\n"
    )
    errors, _ = validate.validate(tmp_path)
    assert errors
    assert any("providers.py" in e for e in errors)
    assert any("links.yaml" in e for e in errors)
    assert any("specs/page_classifier.txt" in e for e in errors)


def test_schema_version_required(tmp_path, example_dir):
    import shutil
    shutil.copytree(example_dir, tmp_path / "p")
    cfg = (tmp_path / "p" / "config.yaml")
    cfg.write_text(cfg.read_text().replace("schema_version: 1\n", ""))
    errors, _ = validate.validate(tmp_path / "p")
    assert any("schema_version" in e for e in errors)


def test_unknown_page_default_domain(tmp_path, example_dir):
    import shutil
    shutil.copytree(example_dir, tmp_path / "p")
    cfg = (tmp_path / "p" / "config.yaml")
    cfg.write_text(cfg.read_text().replace("  site: site\n", "  site: site\n  blog: nope\n"))
    errors, _ = validate.validate(tmp_path / "p")
    assert any("nope" in e for e in errors)

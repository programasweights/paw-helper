"""Tests for `paw-helper init` scaffolding and the offline mock backend - the
no-credentials path an adopter hits first (init -> validate -> mock serve)."""

import filecmp
import pathlib

from paw_helper import cli, common, inference, pipeline, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAFFOLD = ROOT / "paw_helper" / "scaffold" / "minimal"
EXAMPLE = ROOT / "examples" / "minimal"


def _tree(root: pathlib.Path) -> set[str]:
    return {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def test_scaffold_matches_example_pack():
    """The packaged scaffold (shipped in the wheel for `init`) must stay byte-identical
    to the browseable examples/minimal pack, so the two never drift."""
    assert _tree(SCAFFOLD) == _tree(EXAMPLE)
    match, mismatch, errors = filecmp.cmpfiles(
        SCAFFOLD, EXAMPLE, list(_tree(SCAFFOLD)), shallow=False)
    assert not mismatch, f"scaffold/example differ: {mismatch}"
    assert not errors, f"scaffold/example uncompared: {errors}"


def test_init_creates_valid_pack(tmp_path):
    dst = tmp_path / "mypack"
    rc = cli.main(["init", str(dst)])
    assert rc == 0
    assert (dst / "config.yaml").exists()
    assert (dst / "providers.py").exists()
    errors, warnings = validate.validate(dst)
    assert errors == [], errors
    # Not compiled yet -> a programs.json warning, never an error.
    assert any("programs.json" in w for w in warnings)


def test_init_refuses_nonempty_dir(tmp_path):
    dst = tmp_path / "mypack"
    dst.mkdir()
    (dst / "keep.txt").write_text("x")
    assert cli.main(["init", str(dst)]) == 1
    assert (dst / "keep.txt").read_text() == "x"  # untouched


def test_mock_backend_canned_outputs_per_role():
    b = inference.MockBackend()
    assert b.infer("validator", "Q: .. A: ..", 4) == "yes"
    assert b.infer("page_classifier", "where is your cv", 8) == "question"
    assert b.infer("domain_router", "anything", 8) == "question"
    assert b.infer("piazza_selector", "x", 16) == "question"
    assert b.infer("answerer", "what do you research", 200) == inference.MockBackend.PLACEHOLDER


def test_get_backend_selects_mock(monkeypatch):
    monkeypatch.delenv("PAW_HELPER_INFERENCE_BACKEND", raising=False)
    assert isinstance(inference.get_backend({}, mode="mock"), inference.MockBackend)
    assert isinstance(inference.get_backend({}, mode="offline"), inference.MockBackend)
    assert inference.is_mock_mode("echo") is True
    assert inference.is_mock_mode("local_sdk") is False


def test_mock_pipeline_boots_without_programs_json(tmp_path, monkeypatch):
    """The core enabler: in mock mode the pipeline boots and answers with NO
    compiled programs.json - what makes `init -> serve` work before `compile`."""
    dst = tmp_path / "mypack"
    cli.main(["init", str(dst)])
    assert not (dst / "programs.json").exists()
    monkeypatch.setenv("PAW_HELPER_INFERENCE_BACKEND", "mock")
    common.set_content_dir(dst)
    p = pipeline.Pipeline()
    assert p.inference_backend.__class__.__name__ == "MockBackend"
    assert p.available == ["site"]  # synthesized program names populate `available`
    out = p.run("what do you work on", page="site")
    assert out["result"]["type"] == "answer"
    assert out["result"]["text"] == inference.MockBackend.PLACEHOLDER

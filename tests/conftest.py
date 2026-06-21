import json
import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "minimal"


@pytest.fixture
def example_dir():
    return EXAMPLE


@pytest.fixture
def booted_pack(tmp_path):
    """A copy of the example pack with a stub programs.json (IDs are never called
    offline; this lets the pipeline/server boot without compiling)."""
    dst = tmp_path / "pack"
    shutil.copytree(EXAMPLE, dst)
    (dst / "programs.json").write_text(json.dumps({
        "compiler": "stub",
        "programs": {"page_classifier": "stub1", "answerer": "stub2", "validator": "stub3"},
    }))
    return dst

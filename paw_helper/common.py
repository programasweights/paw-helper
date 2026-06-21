"""Content-pack loading + spec composition for the paw-helper framework.

Locates the content pack (config/specs/facts/links/data/providers.py) and composes
specs by inlining {{LINKS}} / {{LINK_REGISTRY}} / {{FACTS}}, so a classifier's
label list and the answerer's facts are always derived from the pack - never a
hand-copied list inside a spec. The framework holds no per-content knowledge.
"""

import importlib.util
import json
import os
import pathlib
import re
import sys

import yaml

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent

# The content pack directory (config.yaml, specs/, facts/, links, data, providers.py).
# Resolve from PAW_HELPER_CONTENT, else the current working directory. Override at
# runtime with set_content_dir() (the CLI/server pass --content).
CONTENT_DIR = pathlib.Path(os.environ["PAW_HELPER_CONTENT"]).resolve() if os.environ.get(
    "PAW_HELPER_CONTENT") else pathlib.Path.cwd()

SPEC_NAMES = ["page_classifier", "answerer", "validator"]


def _recompute_paths() -> None:
    global SPECS_DIR, FACTS_PATH, PROGRAMS_PATH, FACTS_DIR
    SPECS_DIR = CONTENT_DIR / "specs"
    FACTS_PATH = CONTENT_DIR / "facts.md"
    PROGRAMS_PATH = CONTENT_DIR / "programs.json"
    FACTS_DIR = CONTENT_DIR / "facts"


def set_content_dir(path) -> pathlib.Path:
    """Point the framework at a content pack (used by the CLI/server --content)."""
    global CONTENT_DIR
    CONTENT_DIR = pathlib.Path(path).resolve()
    _recompute_paths()
    return CONTENT_DIR


_recompute_paths()

# Config file the content pack ships (new name first, legacy fallback).
CONFIG_NAMES = ("config.yaml", "pipeline.yaml")


def config_path() -> pathlib.Path:
    for n in CONFIG_NAMES:
        p = CONTENT_DIR / n
        if p.exists():
            return p
    return CONTENT_DIR / CONFIG_NAMES[0]


def load_config() -> dict:
    with open(config_path(), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_links_file(filename: str) -> dict:
    """Load one links file from the content pack by filename."""
    with open(CONTENT_DIR / filename, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _default_links_file(cfg: dict) -> str:
    return cfg["domains"][cfg["default_domain"]]["links"]


def load_links() -> dict:
    """The default domain's links: label -> {url|kind, label, description, purpose}."""
    return load_links_file(_default_links_file(load_config()))


def links_for_spec(name: str) -> dict:
    """The links dict a given spec's {{LINKS}} should be filled from.

    A domain's classifier spec is filled from that domain's links file; anything
    else (e.g. the site answerer's {{LINK_REGISTRY}}) uses the default domain's
    links. Derived from config so the framework holds no per-content knowledge.
    """
    cfg = load_config()
    classifier_links = {d["classifier"]: d["links"] for d in cfg["domains"].values()}
    return load_links_file(classifier_links.get(name) or _default_links_file(cfg))


def load_providers():
    """Import the content pack's providers.py (its only required Python).

    Exposes CONTEXT_PROVIDERS / CONTEXT_LABELS / RESOURCE_PROVIDERS. The content
    dir is put on sys.path so the pack's providers can import its own helpers.
    """
    if str(CONTENT_DIR) not in sys.path:
        sys.path.insert(0, str(CONTENT_DIR))
    path = CONTENT_DIR / "providers.py"
    spec = importlib.util.spec_from_file_location("paw_helper_providers", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_programs() -> dict:
    with open(PROGRAMS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _strip_comments(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_facts() -> str:
    """facts.md content for the answerer spec, with maintainer-only notes removed.

    HTML comments (<!-- ... -->) are stripped so editor guidance in facts.md never
    gets compiled into the program.
    """
    return _strip_comments(FACTS_PATH.read_text(encoding="utf-8"))


def load_topic_facts(name: str) -> str:
    """Detailed facts for a sub-answerer topic (facts/<name>.md), runtime-injected."""
    return _strip_comments((FACTS_DIR / f"{name}.md").read_text(encoding="utf-8"))


def build_links_block(links: dict) -> str:
    """Render links.yaml into the bullet list injected into the classifier spec."""
    return "\n".join(f"- {label}: {info['purpose']}" for label, info in links.items())


def build_link_registry(links: dict) -> str:
    """name -> url list the answerer may hyperlink, derived from links.yaml.

    This is the single source of truth (links.yaml) reused in the answerer spec,
    not a hand-copied duplicate. Entries without a URL (e.g. feedback) are skipped,
    as are routing-only links flagged `registry: false` (e.g. social/profile pages
    the answerer should never inline in prose - those stay classifier-only).
    """
    return "\n".join(
        f"- {info.get('name') or info.get('label', label)}: {info['url']}"
        for label, info in links.items()
        if info.get("url") and info.get("registry", True)
    )


def normalize_label(raw: str, links: dict | None = None) -> str:
    """Map a raw page_classifier output to a known link label or 'question'.

    Unknown/malformed output falls back to 'question' (safer than a wrong link).
    Shared by the server and the benchmark so they score identically.
    """
    links = links if links is not None else load_links()
    s = raw.strip().lower().strip("\"'").strip(".")
    parts = s.split()
    s = parts[0] if parts else ""
    if s in links or s == "question":
        return s
    return "question"


def compose_spec(name: str, links: dict | None = None) -> str:
    """Read a spec template and inline {{LINKS}} / {{LINK_REGISTRY}} / {{FACTS}}.

    The {{LINKS}} placeholder is filled from the spec's link source (site links by
    default, course links for course_classifier); pass `links` to override.
    """
    text = (SPECS_DIR / f"{name}.txt").read_text(encoding="utf-8")
    spec_links = links or links_for_spec(name)
    if "{{LINKS}}" in text:
        text = text.replace("{{LINKS}}", build_links_block(spec_links))
    if "{{LINK_REGISTRY}}" in text:
        text = text.replace("{{LINK_REGISTRY}}", build_link_registry(spec_links))
    if "{{FACTS}}" in text:
        text = text.replace("{{FACTS}}", load_facts())
    return text

# Changelog

All notable changes to paw-helper are documented here. This project adheres to
[Semantic Versioning](https://semver.org/). The content-pack contract has its own
`schema_version` (currently 1), bumped independently of the package version.

## [0.4.0] - 2026-06-24

### Added
- Parallel-branch **selector** (retrieve-then-rerank): a branch may declare
  `selector: <program>` and `select_k: N`. The search provider supplies RECALL
  (top-`select_k` candidates over a low `min_score` floor); the selector is a PAW
  program shown the ORIGINAL question + the numbered candidate labels that returns
  the genuinely-relevant numbers (most relevant first) or "none". This replaces a
  brittle absolute `min_score` threshold with a question-aware precision stage, so
  the merge is robust to retriever false positives. `min_score` now acts only as a
  recall floor when a selector is present (still the sole hard gate without one).
- `validate` + `compile` require/compile a branch's `selector` program (like `gate`).

### Notes
- Backward compatible: a branch without `selector` behaves exactly as in 0.3.0
  (`min_score` is the precision threshold).

## [0.3.0] - 2026-06-24

### Added
- Parallel branches: a domain may declare `parallel_branches: [{name, when_page,
  gate, provider, min_score, max_items, result_label}]`. `run()` executes the main
  pipeline and each enabled branch CONCURRENTLY (a `ThreadPoolExecutor`; cheap on
  the `remote_infer` backend), then aggregates: nothing relevant -> main unchanged
  (invisible); main declined -> branch links rescue it; otherwise branch links are
  attached as `result.related` (augment). A content pack may export
  `aggregate(query, main, branches)` to override the merge.
- `SEARCH_PROVIDERS` provider type (`search(query) -> [{label,url,description,score}]`)
  for branch retrieval; `validate` + `compile` understand branch gates/providers.
- The widget renders `result.related` ("Related") links below a main result.

## [0.1.1] - 2026-06-22

### Added
- `/widget.js` serves a content pack's own `widget.js` (at the pack root) when
  present, overriding the packaged default - so a deployment can ship its own
  labels, contact, and presets.
- The packaged default widget is now generic and configurable via script
  attributes: `data-name` (owner/site name) and `data-email` (fallback contact).

## [0.1.0] - 2026-06-21

Initial extraction from the yuntiandeng.com / neural-os.com helper.

### Added
- `paw_helper` framework: a config-driven, page-aware pipeline executor
  (`pipeline.py`), spec composition + content-pack loading (`common.py`), the PAW
  compiler wrapper (`compile.py`), the rubric grader (`grader.py`), and the
  FastAPI server (`server/app.py`) with an embeddable `widget.js`.
- Framework / content-pack split: a pack ships `config.yaml`, `specs/`, facts,
  links, `providers.py`, and a pinned `programs.json`; the framework holds no
  per-content knowledge.
- `paw-helper` CLI: `validate`, `compile`, `serve`, `version`.
- `paw-helper validate`: fail-fast content-pack checks against the contract
  (`schema_version` 1).
- A minimal example content pack and deploy templates (systemd, nginx, embed).
- Offline test suite + GitHub Actions CI.

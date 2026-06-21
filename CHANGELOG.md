# Changelog

All notable changes to paw-helper are documented here. This project adheres to
[Semantic Versioning](https://semver.org/). The content-pack contract has its own
`schema_version` (currently 1), bumped independently of the package version.

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

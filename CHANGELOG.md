# Changelog

All notable changes to paw-helper are documented here. This project adheres to
[Semantic Versioning](https://semver.org/). The content-pack contract has its own
`schema_version` (currently 1), bumped independently of the package version.

## [0.8.1] - 2026-06-27

### Fixed
- Branch execution is now backend-aware. The main pipeline + branches run CONCURRENTLY
  (ThreadPoolExecutor) only when the inference backend sets `parallel = True` (i.e.
  `remote_infer`, where each call is an independent HTTP POST and overlaps over the
  network). For in-process backends (`local_sdk`) it now runs SEQUENTIALLY: those
  serialize on one model instance, and CPU `llama.cpp` under Python threads is
  catastrophically slower - measured **~15-35x** (e.g. 32s vs 1.7s for one course query)
  on the default backend. Same result either way; only the scheduling changes.
- Backends declare a `parallel` flag (`local_sdk`/`mock` = False, `remote_infer` = True).

## [0.8.0] - 2026-06-27

### Added
- Parallel-branch **list/recency results**: a search provider may mark items
  `list_only: True` (e.g. a "latest posts" recency list). When every kept item is
  `list_only`, the branch SKIPS the Q&A answerer and returns the items as a links list
  with `list_primary: True`; the aggregator then surfaces that list as the PRIMARY
  result, overriding the main pipeline.

### Fixed
- "latest / what's new" branch queries no longer run the kept threads through the Q&A
  `answerer`, which is built to answer a SPECIFIC question and hallucinated on a vague
  "what's new" (it summarized threads it was never given, and omitted the actual newest
  post). A recency query is a "show me the latest" request, so its items' titles ARE the
  answer - they are now listed faithfully and deterministically.

## [0.7.0] - 2026-06-26

### Added
- `paw-helper init <dir>`: scaffold a new content pack from the packaged starter pack
  (a copy of `examples/minimal`, now shipped as package data so `init` works from a
  `pip install`, not just a source checkout). Removes the old
  `cp -r .../examples/minimal` step.
- Offline **mock inference backend** (`PAW_HELPER_INFERENCE_BACKEND=mock`): returns
  canned, deterministic outputs branched on the program ROLE, so
  `init -> validate -> serve` answers end to end with NO PAW account, API key, or
  compiled `programs.json`. In mock mode the pipeline synthesizes program IDs from the
  config, so it boots without `programs.json` (otherwise `serve` requires it). Never
  the default; for demos/tests only.
- `AGENTS.md`: an agent-facing, end-to-end setup guide (init -> author -> validate ->
  compile -> deploy -> embed) with a copy-paste prompt and a common-errors table, for
  friction-free, agent-driven adoption on any personal website.

### Notes
- The packaged scaffold (`paw_helper/scaffold/minimal`) is kept byte-identical to
  `examples/minimal` by a drift test.

## [0.6.2] - 2026-06-25

### Fixed
- Branch faithfulness: when a branch's `answerer` DECLINES, the branch now contributes
  nothing - not even a citation. Previously the selector-kept threads were still
  surfaced as `related` links even though the answerer could not answer from them,
  which cited an irrelevant source (e.g. the Assignment 2 post shown for "is
  assignment 3 released"). The answerer's decline is the grounding signal that the
  kept threads do not address the question.

## [0.6.1] - 2026-06-25

### Fixed
- `RemoteInferBackend.infer` now retries (4 attempts, short backoff) on an EMPTY
  output or a 429/5xx. The PAW API can transiently return an empty completion under
  burst load (rate-limited); previously that surfaced as a blank / "I don't have
  that" answer in production. Helper programs never legitimately return empty, so an
  empty response is treated as a transient failure and retried.

## [0.6.0] - 2026-06-24

### Added
- Parallel-branch **merge judge** (question-aware aggregation): a branch may declare
  `merge: <program>`. When the branch synthesized an answer, the aggregator shows the
  judge the QUESTION + the main answer + the branch answer (+ source titles) and it
  returns `main` (keep the course answer, discard the branch - no hijack), `augment`
  (keep the main answer + attach the branch citation), or `branch` (promote the branch
  answer to primary). This replaces blanket promote-on-answer with a decision made
  from BOTH answers, so the branch only wins when it is genuinely better. Falls back
  to promote-on-answer when no `merge` is configured (back-compat).
- `run()` records the decision in `out["merge"]` (`main | piazza | augment`) for
  outcome-level benchmarking.
- `validate` + `compile` require/compile a branch's `merge` program.

### Notes
- Pairs with over-calling the branch (no gate): recall is cheap; the merge judge,
  having both answers in hand, is a more robust selector than an up-front topic gate.

## [0.5.0] - 2026-06-24

### Added
- Parallel-branch **answerer** (retrieve -> rerank -> ANSWER): a branch may declare
  `answerer: <program>`. After the selector keeps the relevant candidates, the
  answerer is shown the original question + the kept items' `context` (e.g. an
  endorsed instructor reply a search provider attaches) and SYNTHESIZES a concise,
  grounded answer (or declines). When a branch produces an answer, the aggregator
  PROMOTES it to the primary result, with the threads attached as citation links -
  so a confident branch answer overrides a generic main answer. Guards: the
  selector (relevance) + an answerer decline (`_looks_like_decline`) gate promotion.
- Provider items may set `keep: True` to BYPASS the selector (already-qualified
  candidates, e.g. a recency list); the answerer still runs over them.
- `validate` + `compile` require/compile a branch's `answerer` (like `gate`/`selector`).

### Notes
- Backward compatible: a branch without `answerer` behaves as in 0.4.0 (links only).

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

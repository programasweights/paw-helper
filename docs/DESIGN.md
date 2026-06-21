# paw-helper: design

A small, reusable "ask about this site" helper backend built as a pipeline of
ProgramAsWeights (PAW) programs. One backend can serve many sites; each site
embeds a self-contained `widget.js` and is added to a CORS allow-list.

This document describes the architecture and the **framework / content-pack
boundary** that lets others run the same backend with their own content.

## Goal and non-goals

Goal: a generic, config-driven helper backend (the *framework*) plus a
per-deployment bundle of specs, facts, links, data, and compiled program IDs
(the *content pack*). The framework is reusable; the content pack is yours.

Non-goals: a hosted multi-tenant service (each deployer self-hosts); training or
serving the base model (that is PAW's hosted API); a general chatbot (answers are
grounded in the pack's facts and decline otherwise).

## Pipeline

```
/ask {query, page}
  -> domain_router (page-aware)        -> domain (site | course | neuralos | ...)
  -> <domain>.classifier               -> a link label or "question"
       - link label   -> return the link (a "feedback" label opens the form)
       - resource label (e.g. slides) -> rule+fuzzy resource router -> deep links
       - "question"   -> <domain>.answerer (+ topic router) -> validator -> answer / fallback
```

- The **domain router** is *page-aware*: it is fed `Page: <label>\nMessage: <query>`
  so an ambiguous/unnamed-subject question stays on the current page and the same
  question is answered per site (ADR 0005).
- Each **domain** has a classifier (link vs question) and an answerer. A domain may
  add a **topic router** to specialized sub-answerers, and **resource routers** that
  combine a rule-based candidate list with a fuzzy PAW selector (e.g. slides).
- **Facts** are injected at inference time from the content pack, not baked into the
  programs, so editing facts needs no recompile (ADR 0003).
- A shared **validator** gates freeform answers; on "no"/empty the pipeline returns a
  graceful fallback instead of a wrong answer (redundancy/resilience).

`pipeline.py` walks `config.yaml`; `programs.json` supplies the pinned compiled IDs.
The same executor runs the server and the benchmark, so they can never diverge.

## Framework / content-pack boundary

Framework (the `paw_helper` package):
- `pipeline.py` (executor), `compile.py`, `eval.py`, `grader.py`, generic
  `common.py` (spec composition, link/program loading), `server/app.py`,
  `server/static/widget.js`, `deploy/` templates, and a `paw-helper` CLI.

Content pack (per deployment, e.g. `rush-nlp/helper`):
- `config.yaml` (the pipeline graph + page defaults + router page labels)
- `specs/` (one `.txt` per program, with `{{LINKS}}` / `{{LINK_REGISTRY}}` / `{{FACTS}}` placeholders)
- `facts.md`, `facts/*.md` (baked + runtime-injected facts)
- `links.yaml`, `*_links.yaml` (routable link sets per domain)
- `data/` (volatile data rendered by providers)
- `bench/` (eval suites + `golden.jsonl`)
- `programs.json` (pinned compiled program IDs)
- `providers.py` (the only content-specific Python: registers fact/resource providers)

### The provider contract

The framework does not know about courses, students, or NeuralOS. The content
pack supplies a `providers.py` that registers:

- `CONTEXT_PROVIDERS: dict[str, Callable[[query], str]]` - returns the facts text
  injected under a domain's `context` key (the seam a future RAG retriever plugs
  into).
- `RESOURCE_PROVIDERS: dict[str, (render_candidates, map_ids)]` - the rule side of
  a resource router (render a candidate list, map selected ids -> link items).

The framework discovers the pack via `--content <dir>` / `PAW_HELPER_CONTENT` and
imports its `providers.py`. This is a documented, versioned contract
(`schema_version` in `config.yaml`), checked by `paw-helper validate` before any
model call.

## Request flow (server)

`server/app.py` builds one shared `Pipeline(content_dir)` (one model instance,
inference serialized). `/ask` runs the pipeline and logs the query + HTTP `Origin`
(which site embedded the widget) for the review loop. `/feedback` appends to a log.
`/widget.js` serves the embeddable widget (public; data endpoints are CORS-gated).

## Behavior preservation

`snapshot.py` records the full pipeline output for a fixed query set to
`bench/golden.jsonl`; `--check` re-runs and diffs. Because the refactor does not
change programs or content, the diff must be empty (verified deterministic). This
is the gate that the extraction does not alter any response.

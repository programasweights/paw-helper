# paw-helper - Agent Setup Guide

You are an AI coding agent setting up an "ask about my website" helper for the user's own site, end to end. This file is the procedure; follow it top to bottom, resolving the inputs below first.

`paw-helper` is a small, self-hosted backend: visitors ask a question in an embedded widget and get a natural-language answer grounded in facts you provide, or a link to the right page. It is a pipeline of [ProgramAsWeights](https://programasweights.com) (PAW) programs - tiny neural functions that run locally. One backend can serve many sites via CORS. It is general-purpose: nothing here assumes a particular person or site, so fill everything from the user's own website.

What you will produce: a content pack (the user's specs, facts, and links), compiled PAW programs, a deployed backend, and a one-line widget embedded on the user's site.

## Work posture: minimize friction

Infer from what you can already see - the user's repo, their live site, where it is hosted - and use sensible defaults. Ask the user only when you are genuinely blocked. Read their existing site/repo to draft the facts and links and then confirm, rather than interrogating item by item; pick a default and state it rather than asking; never ask for a PAW key unless a rate limit actually forces it.

## Inputs and decisions (resolve these first)

- Site content: what the site is about, its key links (cv/resume, github/code, contact, publications, blog, ...), and the facts visitors should get. Draft these from the user's existing site/repo, then confirm.
- Backend host: the backend is an always-on HTTP service that needs a host with a public IP and shell access. Decide where it runs by inferring, not reflexively asking:
  - If the site already runs on a server the user controls (a VPS, cloud VM, or dynamic-app host), deploy the backend on that same machine - just propose it.
  - If the site is static-only (GitHub Pages, Netlify/Vercel static, S3), there is no server to reuse: identify a separate host. Only here ask "Do you have a machine with a public IP you control (a small VPS or always-on box)?" A static site is fine; only the backend needs a server.
  - A tiny (~1 vCPU) box is enough when you use `remote_infer` (below).
- Inference backend (pick a default and state it; do not block on it): `local_sdk` (default) runs the model in-process on the host CPU - self-contained, no key, but it serializes on one model instance so it handles concurrent visitors poorly. `remote_infer` offloads inference to the PAW API - a thin proxy that runs on a tiny box and handles concurrency far better. Prefer `remote_infer` when the host is small or you expect concurrent visitors; `local_sdk` when you want zero external calls at serve time.
- PAW account/key: not required. Compiling and serving work anonymously. A key only raises the anonymous compile limit (20/hr -> 60/hr) and is recommended for `remote_infer` under load; generate one at https://programasweights.com/settings and `export PAW_API_KEY=paw_sk_...`. Do not ask for it unless needed.
- Deploy access: if you will deploy for the user, confirm you have SSH access to the host.
- Your working machine needs Python 3.10+.

## Architecture

Two decoupled pieces, connected over HTTPS with CORS:

```
[ user's site: GitHub Pages / Netlify / any host ]  --- /ask (HTTPS + CORS) -->  [ paw-helper backend ]
   embeds  <script src=".../widget.js">                                          a host with a public IP
                                                                                 /ask /feedback /health /widget.js
```

The site can live anywhere (static or dynamic); only the backend needs a server. That is why "my site is on GitHub Pages" is never a blocker.

## Procedure overview

1. Get the framework (clone + install).
2. Author the content pack (the bulk of the work).
3. Validate, then compile (pins `programs.json`).
4. Serve and smoke-test locally.
5. Deploy to the host and embed the widget on the site.
6. Iterate from real traffic.

## 1. Get the framework

Clone and install editable (the PAW SDK resolves only via the PAW package index):

```bash
git clone https://github.com/programasweights/paw-helper && cd paw-helper
python -m venv venv && . venv/bin/activate
pip install -e ".[dev]" --extra-index-url https://pypi.programasweights.com/simple/
```

A published `pip install paw-helper --extra-index-url https://pypi.programasweights.com/simple/` is the future path; the clone also gives you the example pack and tests.

## 2. Author the content pack

Scaffold a starter pack, then edit it for the user's site:

```bash
paw-helper init mypack
```

Optional sanity check (no network, no account): serve the freshly-scaffolded pack with the canned `mock` backend to see the end-to-end shape before authoring - `PAW_HELPER_INFERENCE_BACKEND=mock paw-helper serve --content mypack --port 8088`, then `POST /ask`.

The pack is a directory the framework loads; everything site-specific lives here (the framework holds no per-site knowledge):

```
mypack/
  config.yaml      # the pipeline graph: domains, page defaults, budgets
  specs/*.txt      # one spec per program (classifier, answerer, validator, ...)
  facts.md         # the facts your answerer is allowed to use
  links.yaml       # routable links (cv, github, contact, feedback, ...)
  providers.py     # the only Python; registers runtime-fact providers (RAG seam)
  programs.json    # compiled PAW program IDs (written by `paw-helper compile`)
```

Edit each file to fit the user's site. The contract (enforced by `paw-helper validate`):

### `config.yaml`

Required keys: `schema_version` (keep `1`), `default_domain`, `domains`, `max_tokens`. Each domain needs `classifier`, `answerer`, `links`; optional are a top-level `validator`, `token_budget`, `resilience`, `page_defaults`, and per-domain `facts_mode`. For a single personal site, the scaffold's one `site` domain with `facts_mode: baked` is all you need. Add more domains (and a `domain_router`) only for multi-site or multi-topic setups.

### `links.yaml`

One entry per routable destination, each with `url`, `name`, `label`, `description`, and `purpose` (the `purpose` line is what the classifier reads). Use `kind: feedback` (no URL) for a feedback form, and `registry: false` to keep a link classifier-only (never inlined in prose). Cover the common personal-site shapes: cv/resume, github/code, contact/email, publications/scholar, blog, feedback.

### `facts.md`

The facts your answerer may use: bio, research/projects, availability ("taking students/clients"), location, anything you want answered. Keep it factual and concise. HTML comments (`<!-- ... -->`) are stripped at compile, so use them for editor notes. The answerer is instructed to decline ("I don't have that information.") when a question is not covered - this is the anti-hallucination guard; keep it.

### `specs/*.txt`

One spec per program referenced by `config.yaml`. Use the placeholders the framework fills from your pack: `{{LINKS}}` (the classifier's label list), `{{LINK_REGISTRY}}` (name -> url the answerer may hyperlink), and `{{FACTS}}` (your `facts.md`). After composing, no other `{{...}}` may remain. Each spec is a short description plus a few `Input:`/`Output:` examples (this is how PAW specs are written - see https://programasweights.com/AGENTS.md). Edit the examples to match the site's real questions.

### `providers.py`

Exports `CONTEXT_PROVIDERS` (a dict; leave it `{}` for a baked single-site pack). Add a provider only when a domain sets `facts_mode: runtime` and `context: <key>` to inject volatile facts at inference time (deadlines, a roster, retrieved documents - the RAG seam). The file's docstring shows the shape.

Re-run `paw-helper validate --content mypack` until it reports OK. It collects every error at once with the exact key or file at fault.

## 3. Compile

```bash
paw-helper compile --content mypack --compiler paw-ft-bs48
```

This compiles each spec into a pinned PAW program (over the network, on the hosted PAW compiler) and writes `mypack/programs.json` - commit it so the server runs exactly what you compiled. It works anonymously (20 compiles/hr; set `PAW_API_KEY` for a higher limit). `paw-ft-bs48` is the highest-accuracy compiler (~2-5 min/program); for fast iteration on a spec you can omit `--compiler` to use the quick default, then recompile the final specs with `paw-ft-bs48` (same runtime, drop-in).

## 4. Serve and smoke-test

```bash
paw-helper serve --content mypack --port 8088
curl -s localhost:8088/health        # {"status":"ok", ...}
curl -s -X POST localhost:8088/ask -H 'Content-Type: application/json' \
  -d '{"query":"<a real question about the site>","page":"site"}'
```

Eyeball the answers against the facts; tighten specs/facts and recompile until they are right.

Choose where each PAW call runs with `PAW_HELPER_INFERENCE_BACKEND`: `local_sdk` (default) runs in-process on the host CPU (self-contained, but serializes on one model instance, so concurrent visitors queue), or `remote_infer` offloads to the PAW API (`/api/v1/infer`) so the work runs on hosted GPUs and concurrency is handled far better (set a valid `PAW_API_KEY` under load). Same pipeline, logs, and programs either way - only the transport changes. (`mock` is the third, demo-only backend.)

## 5. Deploy and embed

Deploy the backend on the host from the Inputs section. Templates are in `paw_helper/deploy/`: a systemd unit, an nginx vhost (add TLS with `certbot`), and an nginx `sub_filter` embed example. If you have SSH access, run these for the user. Key settings:

- `HELPER_ALLOWED_ORIGINS` - comma-separated; add EVERY site origin that embeds the widget. This is the CORS allow-list for `/ask`, `/feedback`, `/health`.
- `PAW_API_KEY` - set it in the service environment when serving with `remote_infer`; an anonymous key hits a strict rate limit and yields blank answers under load.
- `HELPER_CACHE_TTL_S` - optional; for a launch or a high-traffic burst set e.g. `60` to cache identical (page, query) answers for a few seconds. Answers are deterministic, so this absorbs repeated questions without changing behavior.

Embed on the site (a static page, a Jekyll/Hugo include, or any HTML):

```html
<script src="https://helper.<you>.com/widget.js"
        data-page="site" data-name="<Site Owner>" data-email="<you@example.com>"></script>
```

To customize the widget copy/presets, drop your own `widget.js` at the pack root and the server serves it in place of the default. For an app whose HTML you do not control, inject the script with nginx `sub_filter` (see `deploy/embed.nginx.example`).

## 6. Iterate from real traffic

The server appends one JSON line per `/ask` to `queries.jsonl`. Use it to find gaps and refine the facts/specs:

```bash
paw-helper review --content mypack queries.jsonl --feedback feedback.jsonl
paw-helper ingest --content mypack queries.jsonl --batch 20   # dedup for a benchmark
```

## Definition of done

- `paw-helper validate --content mypack` reports OK.
- `programs.json` is compiled and committed.
- `/health` returns ok, and `/ask` returns answers grounded in the facts (eyeball several real questions; recompile until correct).
- The backend is served over HTTPS on the host.
- Every site origin that embeds the widget is in `HELPER_ALLOWED_ORIGINS`.
- The widget renders on the live site and answers end to end.

## Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `serve` crashes: `FileNotFoundError: programs.json` | Pack not compiled | Run `paw-helper compile`, or use `PAW_HELPER_INFERENCE_BACKEND=mock` for the offline demo. |
| Blank answers / `429` under load | `remote_infer` with no/invalid `PAW_API_KEY` (anonymous rate limit) | Set a valid `PAW_API_KEY` in the service environment. |
| Widget loads but `/ask` is blocked in the browser | Embedding origin not allow-listed | Add the site's origin to `HELPER_ALLOWED_ORIGINS`. |
| `validate`: "unresolved placeholder ({...}) after composing" | A spec uses a `{{...}}` with no source | Use only `{{LINKS}}` / `{{LINK_REGISTRY}}` / `{{FACTS}}`. |
| `validate`: "missing spec file specs/<name>.txt" | `config.yaml` references a program with no spec | Add `specs/<name>.txt` or remove the reference. |
| `validate`: "config is missing required key ..." | Missing `schema_version` / `default_domain` / `domains` / `max_tokens` | Add the key (see step 2). |
| Compile `429` | Hosted compile rate limit | Wait, or set `PAW_API_KEY` for a higher limit. |
| Widget cannot reach the backend | Backend not on a public IP / not behind HTTPS, or firewall closed | Serve it on a host with a public IP and TLS; open the port. |

## Reference

- `README.md` - human-facing overview and CORS/deploy details.
- `docs/DESIGN.md` and `docs/adr/` - architecture and the load-bearing decisions.
- `examples/minimal/` - a complete, valid pack (what `init` copies).
- https://programasweights.com/AGENTS.md - how to write good PAW specs.

## For site owners: share this

Anyone can add this helper to their own site by pasting this prompt to their AI coding agent:

> I want to add an "ask about my website" helper (built on paw-helper, powered by ProgramAsWeights) to my site. Read the setup guide at https://programasweights.com/paw-helper/AGENTS.md and help me create, compile, and deploy a content pack for my website. [Describe your site: what it's about, the key links, and what visitors should be able to ask.]

If that URL is unavailable, use the raw repo copy: https://raw.githubusercontent.com/programasweights/paw-helper/main/AGENTS.md

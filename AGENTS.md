# paw-helper - Agent Setup Guide

This guide is written for an AI coding agent (e.g. Cursor) to set up an **"ask about
my website" helper** for the user's own site, end to end, with minimal back-and-forth.

`paw-helper` is a small, self-hosted backend: visitors type a question in a widget,
and it answers in natural language grounded in facts you provide, or routes them to
the right link. It is built as a pipeline of [ProgramAsWeights](https://programasweights.com)
(PAW) programs (tiny neural functions that run locally). One backend can serve many
sites via CORS, and a `<script>` tag drops the widget onto any page.

It is **general-purpose**: nothing here assumes a particular person, employer, or
site. Fill the placeholders from the user's own website.

## Copy-paste prompt (for the site owner)

If you are the site owner, paste this to your agent to start:

> I want to add an "ask about my website" helper (built on paw-helper, powered by
> ProgramAsWeights) to my site. Read the setup guide at
> https://programasweights.com/paw-helper/AGENTS.md and help me create, compile, and
> deploy a content pack for my website. [Describe your site: what it's about, the key
> links, and what visitors should be able to ask.]

(If that URL is unavailable, use the raw repo copy:
`https://raw.githubusercontent.com/programasweights/paw-helper/main/AGENTS.md`.)

## What you will build

A **content pack**: a directory of your site's specs, facts, and links that the
framework loads. The framework holds no per-site knowledge; everything site-specific
lives in the pack.

```
mypack/
  config.yaml        # the pipeline graph: domains, page defaults, budgets
  specs/*.txt        # one spec per program (classifier, answerer, validator, ...)
  facts.md           # the facts your answerer is allowed to use
  links.yaml         # routable links (cv, github, contact, feedback, ...)
  providers.py       # the only Python; registers runtime-fact providers (RAG seam)
  programs.json      # compiled PAW program IDs (written by `paw-helper compile`)
```

## Where it runs (your website can stay where it is)

The helper is two decoupled pieces, and confusing them is the #1 adoption blocker:

- The **widget** (frontend) - a one-line `<script>` you add to your site's pages. Your
  site can live ANYWHERE: GitHub Pages, Netlify, Vercel, an S3 bucket, a Jekyll/Hugo
  static site, or a dynamic app. A static site is completely fine.
- The **backend** (this project) - a small always-on HTTP service the widget calls over
  HTTPS (cross-origin via CORS). It runs on a host YOU control with a **public IP**: any
  small Linux VPS or always-on machine. It can NOT run on GitHub Pages / static hosting
  (those serve files only, they can't run a server).

So "my site is on GitHub Pages" is not a blocker - the page just calls the backend on a
separate host cross-origin (this is exactly how yuntiandeng.com, a GitHub Pages site,
talks to its helper backend).

You do NOT need a powerful server. With `PAW_HELPER_INFERENCE_BACKEND=remote_infer` the
box offloads inference to the PAW API, so it is a thin proxy and a tiny (~1 vCPU) VPS is
plenty. With `local_sdk` it runs the model on its own CPU (give it more RAM/cores).

**Agent: before the deploy step, ASK the user where the backend should run** - "Do you
have a machine with a public IP you control (a small VPS, a cloud VM, or an always-on
box)? GitHub Pages can host your site but not this backend." If they give you SSH access
to that host, you can run the deploy steps (Step 5) for them. If they have no host,
point them at a small VPS (any provider) - with `remote_infer` the cheapest tier works.

## Prerequisites

- Python 3.10+. That is it - **no PAW account required**. Compiling and serving both
  work anonymously.
- A **host for the backend**: a machine with a public IP you control (a small VPS or an
  always-on box). Your website itself can stay on GitHub Pages / any static host - only
  the backend needs the server.
- Optional: a PAW API key raises the anonymous compile rate limit (20/hr -> 60/hr) and
  lets you name programs. Generate one at `https://programasweights.com/settings` and
  `export PAW_API_KEY=paw_sk_...`. You only need it if you hit the anonymous compile
  limit, or if you serve the shared `remote_infer` backend under load.

## Step 0 - Get the framework

The dependable path is a clone + editable install (the PAW SDK resolves only via the
PAW package index):

```bash
git clone https://github.com/programasweights/paw-helper && cd paw-helper
python -m venv venv && . venv/bin/activate
pip install -e ".[dev]" --extra-index-url https://pypi.programasweights.com/simple/
```

(A published `pip install paw-helper --extra-index-url https://pypi.programasweights.com/simple/`
is the future path; the clone also gives you the example pack and tests.)

## Step 1 - 60-second offline demo (no network)

Prove the whole shape works with zero network calls. The `mock` backend returns canned
answers, so it needs no compile and no `programs.json`:

```bash
paw-helper init mypack                                   # scaffold a starter pack
paw-helper validate --content mypack                     # fail-fast contract check
PAW_HELPER_INFERENCE_BACKEND=mock paw-helper serve --content mypack --port 8088
# in another shell:
curl -s localhost:8088/health
curl -s -X POST localhost:8088/ask -H 'Content-Type: application/json' \
  -d '{"query":"what do you work on","page":"site"}'
```

You should get a placeholder answer. Now make it real.

## Step 2 - Author the content pack

Edit the files `init` created. The contract (enforced by `paw-helper validate`):

### `config.yaml`

Required keys: `schema_version` (keep `1`), `default_domain`, `domains`, `max_tokens`.
Each domain needs `classifier`, `answerer`, `links` (optional: `validator` at the top
level, `token_budget`, `resilience`, `page_defaults`, `facts_mode`). For a single
personal site, the scaffold's one `site` domain with `facts_mode: baked` is all you
need. Add more domains (and a `domain_router`) only for multi-site/multi-topic setups.

### `links.yaml`

One entry per routable destination. Each: `url`, `name`, `label`, `description`,
`purpose` (the `purpose` line is what the classifier reads). Use `kind: feedback`
(no URL) for a feedback form, and `registry: false` to keep a link classifier-only
(never inlined in prose). Cover the common personal-site shapes: cv/resume, github/
code, contact/email, publications/scholar, blog, feedback.

### `facts.md`

The facts your answerer may use - bio, research/projects, availability ("taking
students/clients"), location, anything you want answered. Keep it factual and concise.
HTML comments (`<!-- ... -->`) are stripped at compile, so use them for editor notes.
The answerer is instructed to decline ("I don't have that information.") when a
question isn't covered - this is the anti-hallucination guard; keep it.

### `specs/*.txt`

One spec per program referenced by `config.yaml`. Use the placeholders the framework
fills from your pack - `{{LINKS}}` (classifier label list), `{{LINK_REGISTRY}}`
(name->url the answerer may hyperlink), `{{FACTS}}` (your `facts.md`). After composing,
no other `{{...}}` may remain. Each spec is a short description plus a few
`Input:`/`Output:` examples (this is how PAW specs are written - see
`https://programasweights.com/AGENTS.md`). Edit the examples to match your site's
real questions.

### `providers.py`

Exports `CONTEXT_PROVIDERS` (a dict; leave it `{}` for a baked single-site pack). Only
add a provider when a domain sets `facts_mode: runtime` and `context: <key>` to inject
volatile facts at inference time (deadlines, a roster, retrieved documents - the RAG
seam). The file's docstring shows the shape.

Re-run `paw-helper validate --content mypack` until it reports OK. It collects ALL
errors at once with the exact key/file at fault - fix them and re-run.

## Step 3 - Compile

```bash
paw-helper compile --content mypack --compiler paw-ft-bs48
```

This compiles each spec into a pinned PAW program (over the network, on the hosted PAW
compiler) and writes `mypack/programs.json` (commit it). It works **anonymously** - no
account needed (20 compiles/hr; `export PAW_API_KEY=paw_sk_...` for a higher limit).
`paw-ft-bs48` is the highest-accuracy compiler (~2-5 min/program). For fast iteration on
a spec, you can omit `--compiler` to use the quick default, then recompile the final
specs with `paw-ft-bs48` (same runtime, drop-in). Commit `programs.json` so the server
runs exactly what you compiled.

## Step 4 - Serve and smoke-test

```bash
paw-helper serve --content mypack --port 8088
curl -s localhost:8088/health        # {"status":"ok", ...}
curl -s -X POST localhost:8088/ask -H 'Content-Type: application/json' \
  -d '{"query":"<a real question about your site>","page":"site"}'
```

Eyeball the answers against your facts. Tighten specs/facts and re-compile as needed.

### Two ways to serve (inference backends)

Set `PAW_HELPER_INFERENCE_BACKEND` to choose where each PAW call runs:

- `local_sdk` (default) - runs the programs **in-process on your own CPU** via the PAW
  SDK. Fully self-contained (no per-request network), and works anonymously. Caveat:
  inference is serialized through one local model instance, so it is **less amenable to
  concurrent requests** - several visitors at once queue behind each other. Best for a
  low-traffic personal site or a box with spare CPU.

  ```bash
  PAW_HELPER_INFERENCE_BACKEND=local_sdk paw-helper serve --content mypack
  ```

- `remote_infer` - **offloads inference to the PAW server** (`/api/v1/infer`), so the
  hosted GPUs do the work and concurrent requests are handled far better. Each `/ask`
  makes a network call; under real load set a valid `PAW_API_KEY` (an anonymous key hits
  a strict per-IP rate limit -> blank answers). Best when you expect concurrency or your
  host has little CPU.

  ```bash
  PAW_HELPER_INFERENCE_BACKEND=remote_infer paw-helper serve --content mypack
  ```

Same pipeline, logs, and programs either way - only the PAW-call transport changes.
(`mock` is the third, demo-only backend from Step 1.)

## Step 5 - Deploy and embed

Templates are in `paw_helper/deploy/` (a systemd unit, an nginx vhost, and an
nginx `sub_filter` embed example). Key settings:

- `HELPER_ALLOWED_ORIGINS` - comma-separated; add EVERY site origin that embeds the
  widget (this is the CORS allow-list for `/ask`, `/feedback`, `/health`).
- `PAW_API_KEY` - set it in the service environment if you serve with
  `PAW_HELPER_INFERENCE_BACKEND=remote_infer`; an anonymous key hits a strict rate
  limit and yields blank answers under load.

Embed on any page:

```html
<script src="https://helper.<you>.com/widget.js"
        data-page="site" data-name="<Your Name>" data-email="<you@example.com>"></script>
```

To fully customize widget copy/presets, drop your own `widget.js` at the pack root; the
server serves it in place of the packaged default. For an app whose HTML you don't
control, inject the script with nginx `sub_filter` (see `deploy/embed.nginx.example`).

## Step 6 - Improve from real traffic

The server logs one JSON line per `/ask` to `queries.jsonl`. Use these to refine:

```bash
paw-helper review --content mypack queries.jsonl --feedback feedback.jsonl
paw-helper ingest --content mypack queries.jsonl --batch 20   # dedup for a benchmark
```

## Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `serve` crashes: `FileNotFoundError: programs.json` | Pack not compiled | Run `paw-helper compile`, or use `PAW_HELPER_INFERENCE_BACKEND=mock` for the offline demo. |
| Blank answers / `429` under load | `remote_infer` with no/invalid `PAW_API_KEY` (anonymous rate limit) | Set a valid `PAW_API_KEY` in the service env. |
| Widget loads but `/ask` is blocked in the browser | Embedding origin not allow-listed | Add the site's origin to `HELPER_ALLOWED_ORIGINS`. |
| `validate`: "unresolved placeholder ({...}) after composing" | A spec uses a `{{...}}` with no source | Use only `{{LINKS}}` / `{{LINK_REGISTRY}}` / `{{FACTS}}`. |
| `validate`: "missing spec file specs/<name>.txt" | `config.yaml` references a program with no spec | Add `specs/<name>.txt` or remove the reference. |
| `validate`: "config is missing required key ..." | Missing `schema_version` / `default_domain` / `domains` / `max_tokens` | Add the key (see Step 2). |
| Compile `429` | Hosted compile rate limit | Wait, or sign in for a higher limit. |

## Reference

- `README.md` - human-facing overview and CORS/deploy details.
- `docs/DESIGN.md` + `docs/adr/` - architecture and the load-bearing decisions.
- `examples/minimal/` - a complete, valid pack (what `init` copies).
- `https://programasweights.com/AGENTS.md` - how to write good PAW specs.

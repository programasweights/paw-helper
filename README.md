# paw-helper

A small, reusable **"ask about this site"** helper backend, built as a pipeline of
[ProgramAsWeights](https://programasweights.com) (PAW) programs. Point it at a
**content pack** (your specs, facts, links, and data) and serve. One backend can
answer about your site, and a self-contained `widget.js` drops onto any page.

It is the extracted, generic backend behind the helper on
[yuntiandeng.com](https://yuntiandeng.com) and [neural-os.com](https://neural-os.com).

```
/ask {query, page}
  -> domain_router (page-aware)   -> a domain (site | course | ...)
  -> <domain>.classifier          -> a link, a resource list, or "question"
  -> <domain>.answerer (+facts)   -> validator -> a grounded answer / graceful fallback
```

See [docs/DESIGN.md](docs/DESIGN.md) and [docs/adr/](docs/adr) for the architecture
and the load-bearing decisions.

## Install

```bash
pip install paw-helper --extra-index-url https://pypi.programasweights.com/simple/
```

(`programasweights` is on the PAW package index; the rest are normal PyPI deps.)

## Quickstart

```bash
# 1. Start from the example pack (or author your own - see "Content pack" below).
cp -r $(python -c "import paw_helper,os;print(os.path.dirname(paw_helper.__file__))")/../examples/minimal mypack

# 2. Validate the pack (fails fast with actionable errors, before any model call).
paw-helper validate --content mypack

# 3. Compile your programs (needs network + the PAW API). Pins programs.json.
paw-helper compile --content mypack --compiler paw-ft-bs48

# 4. Serve. /ask, /feedback, /health, and /widget.js.
paw-helper serve --content mypack --port 8088

# 5. Embed the widget on any page:
#    <script src="https://helper.example.com/widget.js" data-page="site"></script>
```

`--content` defaults to `$PAW_HELPER_CONTENT` or the current directory.

## Content pack

A content pack is a directory the framework loads. Layout:

```
mypack/
  config.yaml        # the pipeline graph: domains, page defaults, router labels, budgets
  specs/*.txt        # one spec per program, with {{LINKS}} / {{LINK_REGISTRY}} / {{FACTS}}
  facts.md           # baked facts for the flat answerer
  facts/*.md         # detailed facts injected at inference time (optional)
  links.yaml         # routable links per domain (more *_links.yaml for more domains)
  providers.py       # the pack's only Python: registers CONTEXT/RESOURCE providers
  data/              # volatile data your providers render (optional)
  bench/             # your evaluation suites (optional)
  programs.json      # pinned compiled program IDs (written by `paw-helper compile`)
```

The framework holds **no per-content knowledge**: domains, links, and facts come
from the pack; the only pack-specific code is `providers.py`, which registers how
to render runtime-injected facts (the RAG seam) against a documented, versioned
contract (`schema_version`). `paw-helper validate` checks it all.

See [examples/minimal](examples/minimal) for a complete, valid pack.

## One backend, many sites (CORS)

`/widget.js` is public and embeddable anywhere. The data endpoints
(`/ask`, `/feedback`, `/health`) are restricted to `HELPER_ALLOWED_ORIGINS`
(comma-separated). Add each embedding site's origin there. For an app whose HTML
you don't control (e.g. a proxied app), inject the script with nginx `sub_filter`
- see [paw_helper/deploy/embed.nginx.example](paw_helper/deploy/embed.nginx.example).

## Deploy and rollback

Templates are in [paw_helper/deploy/](paw_helper/deploy): a systemd unit and an
nginx vhost. Programs are pinned in `programs.json` (committed), so the server runs
exactly what you compiled - no compilation on the server.

```bash
# deploy
git -C /opt/paw-helper/content pull --ff-only
sudo systemctl restart paw-helper
curl -fsS https://helper.example.com/health   # smoke check

# rollback (pinned tag)
git -C /opt/paw-helper/content checkout <last-good-tag>
sudo systemctl restart paw-helper
```

Change the CORS allow-list without overwriting a hand-tuned unit via a drop-in:

```bash
sudo install -d /etc/systemd/system/paw-helper.service.d
printf '[Service]\nEnvironment=HELPER_ALLOWED_ORIGINS=https://a.com,https://b.com\n' \
  | sudo tee /etc/systemd/system/paw-helper.service.d/override.conf
sudo systemctl daemon-reload && sudo systemctl restart paw-helper
```

## Development

```bash
pip install -e ".[dev]" --extra-index-url https://pypi.programasweights.com/simple/
ruff check paw_helper
pytest -q                       # offline: no model calls
paw-helper validate --content examples/minimal
```

The model-dependent gates (compiling, the eval suite, and a golden-snapshot diff
that proves a change does not alter responses) run where the PAW API and your
programs are available - they are your release gate, not part of offline CI.

## License

MIT - see [LICENSE](LICENSE).

"""Validate a content pack and fail fast with actionable errors - BEFORE any model
call. This makes the pack layout + provider interface an explicit, versioned contract.

Checks (collected, not first-fail):
  - config loads; schema_version present and supported
  - required keys; page_defaults / router_page_labels reference real domains
  - every program referenced by config has a spec file
  - each domain's links file exists; classifier links resolve
  - providers.py imports and exposes CONTEXT_PROVIDERS; every domain `context` and
    every resource_router `provider` is registered
  - resource_routers reference a real domain + a program with a spec
  - each spec composes with no leftover {{PLACEHOLDER}}
  - (warn) programs.json present and has an ID for every serving program
"""

from . import common

# Content-pack contract version this framework understands.
SCHEMA_VERSION = 1


def _program_names(cfg: dict) -> list[str]:
    names: list[str] = []
    if cfg.get("domain_router"):
        names.append(cfg["domain_router"])
    for dom in cfg.get("domains", {}).values():
        names += [dom.get("classifier"), dom.get("answerer")]
        if dom.get("topic_router"):
            names.append(dom["topic_router"])
        for sub in dom.get("topics", {}).values():
            if isinstance(sub, dict) and sub.get("answerer"):
                names.append(sub["answerer"])
    if cfg.get("validator"):
        names.append(cfg["validator"])
    names += [rr["program"] for rr in cfg.get("resource_routers", [])]
    names += cfg.get("tools", [])
    seen, ordered = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def validate(content_dir=None) -> tuple[list[str], list[str]]:
    if content_dir is not None:
        common.set_content_dir(content_dir)
    errors: list[str] = []
    warnings: list[str] = []

    cfgp = common.config_path()
    if not cfgp.exists():
        return ([f"no config.yaml or pipeline.yaml in {common.CONTENT_DIR}"], warnings)
    try:
        cfg = common.load_config()
    except Exception as e:
        return ([f"config failed to parse: {e}"], warnings)

    sv = cfg.get("schema_version")
    if sv is None:
        errors.append("config is missing `schema_version` (the content-pack contract version)")
    elif sv > SCHEMA_VERSION:
        errors.append(f"config schema_version {sv} is newer than this framework ({SCHEMA_VERSION}); upgrade paw-helper")

    for key in ("default_domain", "domains", "max_tokens"):
        if key not in cfg:
            errors.append(f"config is missing required key `{key}`")
    domains = cfg.get("domains", {}) or {}
    if cfg.get("default_domain") and cfg["default_domain"] not in domains:
        errors.append(f"default_domain `{cfg['default_domain']}` is not a defined domain")
    for page, dom in (cfg.get("page_defaults") or {}).items():
        if dom not in domains:
            errors.append(f"page_defaults[{page!r}] -> `{dom}` is not a defined domain")
    for dom in (cfg.get("router_page_labels") or {}):
        if dom not in domains:
            errors.append(f"router_page_labels key `{dom}` is not a defined domain")

    # Specs exist for every referenced program.
    for name in _program_names(cfg):
        if not (common.SPECS_DIR / f"{name}.txt").exists():
            errors.append(f"missing spec file specs/{name}.txt (referenced by config)")

    # Per-domain link files + required fields.
    for dname, dom in domains.items():
        for field in ("classifier", "answerer", "links"):
            if not dom.get(field):
                errors.append(f"domain `{dname}` is missing `{field}`")
        lf = dom.get("links")
        if lf and not (common.CONTENT_DIR / lf).exists():
            errors.append(f"domain `{dname}` links file `{lf}` not found")

    # providers.py + the contexts/resources the config relies on.
    providers = None
    if not (common.CONTENT_DIR / "providers.py").exists():
        errors.append("missing providers.py (must export CONTEXT_PROVIDERS)")
    else:
        try:
            providers = common.load_providers()
        except Exception as e:
            errors.append(f"providers.py failed to import: {e}")
    if providers is not None and not hasattr(providers, "CONTEXT_PROVIDERS"):
        errors.append("providers.py must define CONTEXT_PROVIDERS (a dict; may be empty for baked-only packs)")
    ctx_providers = set(getattr(providers, "CONTEXT_PROVIDERS", {}) or {}) if providers else set()
    res_providers = set(getattr(providers, "RESOURCE_PROVIDERS", {}) or {}) if providers else set()
    for dname, dom in domains.items():
        ctx = dom.get("context")
        if ctx and providers is not None and ctx not in ctx_providers:
            errors.append(f"domain `{dname}` context `{ctx}` is not in providers.CONTEXT_PROVIDERS")
    for rr in cfg.get("resource_routers", []):
        if rr.get("domain") not in domains:
            errors.append(f"resource_router domain `{rr.get('domain')}` is not a defined domain")
        if providers is not None and rr.get("provider") not in res_providers:
            errors.append(f"resource_router provider `{rr.get('provider')}` is not in providers.RESOURCE_PROVIDERS")

    # Specs compose with no leftover placeholders.
    if not errors:  # composing needs a consistent config/links
        for name in _program_names(cfg):
            spec_file = common.SPECS_DIR / f"{name}.txt"
            if not spec_file.exists():
                continue
            try:
                composed = common.compose_spec(name)
            except Exception as e:
                errors.append(f"spec {name} failed to compose: {e}")
                continue
            if "{{" in composed and "}}" in composed:
                errors.append(f"spec {name} has an unresolved placeholder ({{...}}) after composing")

    # programs.json (warn only - you compile your own).
    progp = common.PROGRAMS_PATH
    if not progp.exists():
        warnings.append("no programs.json yet - run `paw-helper compile` to build it")
    else:
        try:
            pinned = common.load_programs().get("programs", {})
            tools = set(cfg.get("tools", []))
            for name in _program_names(cfg):
                if name not in pinned and name not in tools:
                    warnings.append(f"programs.json has no ID for serving program `{name}`")
        except Exception as e:
            errors.append(f"programs.json failed to parse: {e}")

    return errors, warnings

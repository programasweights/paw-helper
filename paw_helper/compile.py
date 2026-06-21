"""Compile the helper's PAW programs and write helper/programs.json.

Usage:
    python helper/compile.py                          # compile programs missing from programs.json
    python helper/compile.py --only course_classifier course_answerer domain_router
    python helper/compile.py --all                    # recompile everything
    python helper/compile.py --compiler paw-ft-bs48   # finetuned (slow, best)

Programs and their specs are derived from pipeline.yaml (every domain's
classifier + answerer, plus the domain_router and validator). Each spec is
composed (inlining links / facts), compiled through the hosted PAW API, and its
program ID recorded. Commit programs.json so the server runs a reproducible,
pinned set of programs.

By default only programs missing from programs.json are compiled, so adding the
course domain does not disturb the already-tuned site programs. Use --all or
--only to force recompiles.

Requires network + the PAW SDK (see server/requirements.txt). Set PAW_API_KEY
for higher compile rate limits (optional).
"""

import argparse
import datetime
import json
import time

import httpx

from . import common, pipeline

# Finetuned (paw-ft-bs48) compiles can run several minutes; the SDK's built-in
# POST timeout is only 120s. We submit through the SDK client with a longer
# timeout so finetuned finalize doesn't ReadTimeout mid-compile.
COMPILE_TIMEOUT_S = 900


def compile_spec(spec: str, compiler: str | None):
    """paw.compile, but with a long HTTP read timeout (for finetuned compiles)."""
    from programasweights.client import PAWClient
    from programasweights.config import get_api_key, get_api_url

    client = PAWClient(api_url=get_api_url(), api_key=get_api_key())
    body: dict = {"spec": spec, "public": True}
    if compiler:
        body["compiler"] = compiler
    resp = httpx.post(
        f"{client._api_url}/api/v1/compile",
        json=body,
        headers=client._headers(),
        timeout=COMPILE_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("program_id", ""), data.get("error")


def write_programs(compiler_label: str, programs: dict) -> None:
    out = {
        "compiler": compiler_label,
        "compiled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "programs": programs,
    }
    common.PROGRAMS_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def program_names(cfg: dict) -> list[str]:
    """Every compiled program referenced by the pipeline config, in a stable order."""
    names: list[str] = []
    if cfg.get("domain_router"):
        names.append(cfg["domain_router"])
    for _, dom in cfg["domains"].items():
        names += [dom["classifier"], dom["answerer"]]
        if dom.get("topic_router"):
            names.append(dom["topic_router"])
        for _, sub in dom.get("topics", {}).items():
            if isinstance(sub, dict) and sub.get("answerer"):
                names.append(sub["answerer"])
    if cfg.get("validator"):
        names.append(cfg["validator"])
    # Resource-router selector programs (e.g. slide_selector).
    names += [rr["program"] for rr in cfg.get("resource_routers", [])]
    # Offline tools (not in the serving pipeline) - e.g. the rubric grader.
    names += cfg.get("tools", [])
    # De-dup, preserve order.
    seen, ordered = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def run(compiler: str | None = None, only: list[str] | None = None, recompile_all: bool = False) -> None:
    """Compile the content pack's programs into CONTENT_DIR/programs.json."""
    cfg = pipeline.load_config()
    names = program_names(cfg)

    existing = {}
    if common.PROGRAMS_PATH.exists():
        existing = json.loads(common.PROGRAMS_PATH.read_text())["programs"]

    if only:
        targets = [n for n in names if n in only]
    elif recompile_all:
        targets = names
    else:
        targets = [n for n in names if n not in existing]

    if not targets:
        print("Nothing to compile (all programs already pinned). Use --all or --only to force.")
        return

    programs = dict(existing)
    label = compiler or ("mixed" if existing else "default")
    for name in targets:
        spec = common.compose_spec(name)
        tokens = len(spec) // 4
        suffix = f" with {compiler}" if compiler else ""
        print(f"Compiling {name} ({len(spec)} chars, ~{tokens} tok){suffix} ...")
        if tokens > cfg.get("token_budget", 2048):
            # Baked-facts specs (e.g. the site answerer) are used at COMPILE time;
            # only input+output count against the runtime window. Warn, don't block.
            print(f"  WARNING: {name} spec ~{tokens} tok exceeds the {cfg.get('token_budget', 2048)} "
                  f"runtime window; fine if facts are baked, but verify behavior.")
        # Finetuned compiles can exceed the server's 120s gateway limit (504) or
        # the client read timeout, yet still finish server-side - so resubmitting
        # the identical spec returns the now-cached result. Retry a few times.
        pid = err = None
        for attempt in range(1, 6):
            try:
                pid, err = compile_spec(spec, compiler)
                break
            except httpx.TimeoutException:
                pass
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in (502, 503, 504):
                    raise
            print(f"  attempt {attempt} timed out server-side; waiting for the cached result ...")
            time.sleep(20)
        if pid is None:
            raise SystemExit(f"Compile still pending for {name}; rerun `--only {name}` shortly.")
        if err:
            raise SystemExit(f"Compile failed for {name}: {err}")
        programs[name] = pid
        # Persist after EACH success so a later failure never loses earlier work.
        write_programs(label, programs)
        print(f"  -> {pid}  (saved)")

    print(f"Wrote {common.PROGRAMS_PATH} ({len(programs)} programs)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=None,
                    help="PAW compiler name; omit for the server default.")
    ap.add_argument("--only", nargs="*", default=None, help="Only compile these program names.")
    ap.add_argument("--all", action="store_true", help="Recompile every program (ignore existing IDs).")
    args = ap.parse_args()
    run(compiler=args.compiler, only=args.only, recompile_all=args.all)


if __name__ == "__main__":
    main()

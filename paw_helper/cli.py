"""paw-helper command-line interface.

    paw-helper init     <dir>                       scaffold a new content pack
    paw-helper validate [--content DIR]            check a content pack (fail fast)
    paw-helper compile  [--content DIR] [--compiler X] [--only ...] [--all]
    paw-helper serve    [--content DIR] [--host H] [--port P]
    paw-helper review   [queries.jsonl] [--feedback feedback.jsonl] [--origin O] [--page P]
    paw-helper ingest   [queries.jsonl] [--origin O] [--page P]
    paw-helper grader-eval [bench/grader_meta.yaml]
    paw-helper version

--content defaults to $PAW_HELPER_CONTENT, else the current directory.
"""

import argparse
import os
import pathlib
import sys

from . import __version__, common


def _resolve_content(arg: str | None) -> pathlib.Path:
    path = arg or os.environ.get("PAW_HELPER_CONTENT") or os.getcwd()
    return common.set_content_dir(path)


def _scaffold_dir() -> pathlib.Path:
    """The packaged starter content pack copied by `init`. Ships inside the package
    (so it works from a `pip install`); falls back to the repo's example pack when
    running from a source checkout that has not installed the package data."""
    packaged = common.PACKAGE_DIR / "scaffold" / "minimal"
    if packaged.exists():
        return packaged
    return common.PACKAGE_DIR.parent / "examples" / "minimal"


def _cmd_init(args) -> int:
    import shutil

    dst = pathlib.Path(args.dir).resolve()
    if dst.exists() and any(dst.iterdir()):
        print(f"error: {dst} already exists and is not empty", file=sys.stderr)
        return 1
    src = _scaffold_dir()
    if not src.exists():
        print(f"error: scaffold not found at {src}", file=sys.stderr)
        return 1
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                    dirs_exist_ok=True)
    print(
        f"Created content pack at {dst}\n\n"
        "Next steps:\n"
        f"  paw-helper validate --content {dst}\n"
        f"  PAW_HELPER_INFERENCE_BACKEND=mock paw-helper serve --content {dst}   "
        "# offline demo, no PAW key\n"
        "  # then edit config.yaml / links.yaml / facts.md / specs/ for your site, and:\n"
        f"  paw-helper compile --content {dst} --compiler paw-ft-bs48            "
        "# needs a PAW API key\n"
        f"  paw-helper serve --content {dst}"
    )
    return 0


def _cmd_validate(args) -> int:
    from . import validate
    content = _resolve_content(args.content)
    errors, warnings = validate.validate(content)
    for w in warnings:
        print(f"  warning: {w}")
    if errors:
        print(f"\nINVALID content pack ({content}): {len(errors)} error(s)")
        for e in errors:
            print(f"  error: {e}")
        return 1
    print(f"OK: content pack is valid ({content})" + (f"; {len(warnings)} warning(s)" if warnings else ""))
    return 0


def _cmd_compile(args) -> int:
    from . import compile as compile_mod
    _resolve_content(args.content)
    compile_mod.run(compiler=args.compiler, only=args.only, recompile_all=args.all)
    return 0


def _cmd_serve(args) -> int:
    import uvicorn
    content = _resolve_content(args.content)
    # The server app reads the content pack from this env at import time.
    os.environ["PAW_HELPER_CONTENT"] = str(content)
    uvicorn.run("paw_helper.server.app:app", host=args.host, port=args.port, reload=False)
    return 0


def _cmd_version(args) -> int:
    print(f"paw-helper {__version__}")
    return 0


def _default_log_path(name: str) -> str:
    return str(common.CONTENT_DIR / name)


def _cmd_review(args) -> int:
    from . import logs

    content = _resolve_content(args.content)
    queries_path = pathlib.Path(args.queries or _default_log_path("queries.jsonl"))
    feedback_path = pathlib.Path(args.feedback or _default_log_path("feedback.jsonl"))
    rows = logs.filtered(logs.load_jsonl(queries_path), origin=args.origin, page=args.page)
    feedback_rows = logs.filtered(logs.load_jsonl(feedback_path), origin=args.origin, page=args.page)
    print(logs.review_text(rows, feedback_rows, top=args.top, source=str(queries_path)))
    if args.origin or args.page:
        print(f"\nFilter: content={content} origin={args.origin or '*'} page={args.page or '*'}")
    return 0


def _cmd_ingest(args) -> int:
    from . import logs

    content = _resolve_content(args.content)
    queries_path = pathlib.Path(args.queries or _default_log_path("queries.jsonl"))
    rows = logs.filtered(logs.load_jsonl(queries_path), origin=args.origin, page=args.page)
    print(logs.ingest_text(rows, batch=args.batch))
    if args.origin or args.page:
        print(f"\n# Filter: content={content} origin={args.origin or '*'} page={args.page or '*'}")
    return 0


def _cmd_grader_eval(args) -> int:
    from . import grader_eval

    _resolve_content(args.content)
    meta = pathlib.Path(args.meta) if args.meta else None
    print(grader_eval.run(meta))
    return 0


def main(argv=None) -> int:
    # Shared --content, accepted before OR after the subcommand.
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--content", default=None,
                        help="Content pack directory (default: $PAW_HELPER_CONTENT or cwd).")

    ap = argparse.ArgumentParser(prog="paw-helper", description=__doc__, parents=[parent],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pn = sub.add_parser("init", parents=[parent], help="Scaffold a new content pack from the example.")
    pn.add_argument("dir", help="Target directory to create (must not exist or be empty).")

    sub.add_parser("validate", parents=[parent], help="Validate a content pack (fail fast).")

    pc = sub.add_parser("compile", parents=[parent], help="Compile the pack's programs into programs.json.")
    pc.add_argument("--compiler", default=None)
    pc.add_argument("--only", nargs="*", default=None)
    pc.add_argument("--all", action="store_true")

    ps = sub.add_parser("serve", parents=[parent], help="Run the inference server.")
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8088)

    pr = sub.add_parser("review", parents=[parent], help="Review query/feedback JSONL logs.")
    pr.add_argument("queries", nargs="?", default=None)
    pr.add_argument("--feedback", default=None)
    pr.add_argument("--origin", default=None, help="Only include rows from this HTTP Origin.")
    pr.add_argument("--page", default=None, help="Only include rows with this page key.")
    pr.add_argument("--top", type=int, default=20)

    pi = sub.add_parser("ingest", parents=[parent], help="Print exact-deduped queries for manual curation.")
    pi.add_argument("queries", nargs="?", default=None)
    pi.add_argument("--origin", default=None, help="Only include rows from this HTTP Origin.")
    pi.add_argument("--page", default=None, help="Only include rows with this page key.")
    pi.add_argument("--batch", type=int, default=20)

    pg = sub.add_parser("grader-eval", parents=[parent], help="Validate rubric_checker against gold triples.")
    pg.add_argument("meta", nargs="?", default=None, help="Path to grader_meta.yaml (default: bench/grader_meta.yaml).")

    sub.add_parser("version", parents=[parent], help="Print the framework version.")

    args = ap.parse_args(argv)
    return {
        "init": _cmd_init,
        "validate": _cmd_validate,
        "compile": _cmd_compile,
        "serve": _cmd_serve,
        "review": _cmd_review,
        "ingest": _cmd_ingest,
        "grader-eval": _cmd_grader_eval,
        "version": _cmd_version,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

"""paw-helper command-line interface.

    paw-helper validate [--content DIR]            check a content pack (fail fast)
    paw-helper compile  [--content DIR] [--compiler X] [--only ...] [--all]
    paw-helper serve    [--content DIR] [--host H] [--port P]
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


def main(argv=None) -> int:
    # Shared --content, accepted before OR after the subcommand.
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--content", default=None,
                        help="Content pack directory (default: $PAW_HELPER_CONTENT or cwd).")

    ap = argparse.ArgumentParser(prog="paw-helper", description=__doc__, parents=[parent],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate", parents=[parent], help="Validate a content pack (fail fast).")

    pc = sub.add_parser("compile", parents=[parent], help="Compile the pack's programs into programs.json.")
    pc.add_argument("--compiler", default=None)
    pc.add_argument("--only", nargs="*", default=None)
    pc.add_argument("--all", action="store_true")

    ps = sub.add_parser("serve", parents=[parent], help="Run the inference server.")
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8088)

    sub.add_parser("version", parents=[parent], help="Print the framework version.")

    args = ap.parse_args(argv)
    return {
        "validate": _cmd_validate,
        "compile": _cmd_compile,
        "serve": _cmd_serve,
        "version": _cmd_version,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

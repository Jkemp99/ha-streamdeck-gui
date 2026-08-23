"""CLI: serve, validate, generate-sample."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ha_streamdeck_gui.app import run
from ha_streamdeck_gui.lint import lint_config
from ha_streamdeck_gui.sample import sample_yaml
from ha_streamdeck_gui.yaml_io import dump_config_yaml, load_yaml_file, save_yaml_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ha-streamdeck-gui")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the web editor")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    validate = sub.add_parser("validate", help="Validate a streamdeck.yaml file")
    validate.add_argument("path", type=Path)

    sample = sub.add_parser("generate-sample", help="Write a generic multi-page + dials example")
    sample.add_argument("path", type=Path)
    sample.add_argument("--force", action="store_true")

    dump = sub.add_parser("dump", help="Load a file and print normalized YAML")
    dump.add_argument("path", type=Path)

    args = parser.parse_args(argv)

    if args.command == "serve":
        if args.host:
            os.environ["HOST"] = args.host
        if args.port:
            os.environ["PORT"] = str(args.port)
        run()
        return 0

    if args.command == "validate":
        loaded = load_yaml_file(args.path)
        issues = lint_config(loaded.config, has_includes=loaded.has_includes)
        errors = [issue for issue in issues if issue.severity == "error"]
        for issue in issues:
            print(f"{issue.severity}: {issue.message} ({issue.path})")
        if errors:
            return 1
        print("OK")
        return 0

    if args.command == "generate-sample":
        if args.path.exists() and not args.force:
            print(f"{args.path} exists. Pass --force to overwrite (a backup is written).", file=sys.stderr)
            return 1
        save_yaml_file(args.path, text=sample_yaml(), allow_inline_includes=True)
        print(f"Wrote {args.path}")
        return 0

    if args.command == "dump":
        loaded = load_yaml_file(args.path)
        print(dump_config_yaml(loaded.config), end="")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

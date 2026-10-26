"""Command-line interface: ``cashpilot <command>`` (or ``python -m cashpilot``)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_docs(args: argparse.Namespace) -> int:
    from cashpilot.export.docs import render_data_dictionary
    from cashpilot.schema import load_schema

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "DATA_DICTIONARY.md"
    path.write_text(render_data_dictionary(load_schema()), encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cashpilot",
        description="Multi-entity cash consolidation and 13-week liquidity forecasting under scenarios.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("docs", help="regenerate docs/DATA_DICTIONARY.md from the data dictionary")
    p.add_argument("--out", default="docs", help="output folder (default: docs)")
    p.set_defaults(func=cmd_docs)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

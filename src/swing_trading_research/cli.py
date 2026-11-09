"""Command-line interface for the research project."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from swing_trading_research import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="swing-research",
        description="Reproducible US and UK swing-trading data research.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("version", help="Show the installed project version.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    parser.print_help()
    return 0

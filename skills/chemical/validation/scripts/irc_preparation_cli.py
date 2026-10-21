"""CLI contract for transition-state IRC input preparation."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(
        description="Prepare bounded forward and reverse Gaussian IRC inputs from a TS checkpoint",
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="action", required=True)
    command = sub.add_parser("irc", allow_abbrev=False)
    command.add_argument("--spec", required=True, type=Path)
    command.add_argument("--checkpoint", required=True, type=Path)
    command.add_argument("--output-dir", required=True, type=Path)
    command.add_argument("--max-points", type=int, default=80)
    return parser.parse_args(argv)

"""CLI contract for deterministic geometry safety checks."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--input', type=Path, required=True,
                        help='chemical-geometry-safety-input/1 JSON with elements and Cartesian coordinates in angstrom')
    parser.add_argument('--output', type=Path, required=True,
                        help='geometry safety report JSON; inspect its verdict even when the checker completes')
    return parser.parse_args(argv)

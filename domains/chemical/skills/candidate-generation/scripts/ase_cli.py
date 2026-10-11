"""Pure CLI for ASE NEB with xTB or Gaussian calculators."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('neb-xtb', 'neb-gaussian'):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument('--executable', required=True)
    return parser.parse_args(argv)

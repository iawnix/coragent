"""Independent energy analysis CLI; no native solver or network calls."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description='Explicit thermochemistry and energy analysis', allow_abbrev=False)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('operation', choices=('thermochemistry', 'ensemble', 'profile', 'scan-slice', 'tst', 'branching', 'network'))
    parser.add_argument('--input', type=Path, required=True)
    return parser.parse_args(argv)

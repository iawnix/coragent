"""Pure CLI contract for bound probes and endpoint connectivity checks."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    prepare = sub.add_parser('prepare', allow_abbrev=False)
    prepare.add_argument('--material', type=Path, required=True)
    prepare.add_argument('--log', type=Path, required=True)
    prepare.add_argument('--coordinates', type=Path, required=True)
    prepare.add_argument('--output-dir', type=Path, required=True)
    prepare.add_argument('--section-index', type=int)
    prepare.add_argument('--threads', type=int, default=1)
    prepare.add_argument('--memory-mb', type=int, default=2000)
    prepare.add_argument('--amplitudes', type=float, nargs='+', default=[.05, .1], help='Maximum atom displacement in angstrom')
    prepare.add_argument('--max-points', type=int, default=20)
    prepare.add_argument('--step-size', type=int, default=5)
    check = sub.add_parser('check', allow_abbrev=False)
    for name in ('material', 'evidence', 'coordinates', 'study', 'reactant', 'product', 'output'):
        check.add_argument('--' + name, type=Path, required=True)
    return parser.parse_args(argv)

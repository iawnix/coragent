"""Pure CLI for material-based QST, per-point scans and native gradients."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    p = argparse.ArgumentParser(description='Independent bounded path candidate operations', allow_abbrev=False)
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    sub = p.add_subparsers(dest='operation', required=True)
    sub.add_parser('qst', allow_abbrev=False)
    for name in ('scan-xtb','scan-gaussian','gradient-xtb','gradient-gaussian'):
        cmd = sub.add_parser(name, allow_abbrev=False)
        cmd.add_argument('--executable', required=True)
        if name.startswith('scan'): cmd.add_argument('--max-points', type=int, default=256)
    return p.parse_args(argv)

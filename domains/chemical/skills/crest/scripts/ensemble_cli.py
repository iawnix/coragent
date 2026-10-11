"""Pure contracts for ensemble analysis and complex preparation."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    p = argparse.ArgumentParser(description='Independent ensemble and rigid-fragment operations', allow_abbrev=False)
    p.add_argument('--output-dir', type=Path, required=True)
    commands = p.add_subparsers(dest='operation', required=True)
    imp = commands.add_parser('import', allow_abbrev=False)
    imp.add_argument('--material', type=Path, required=True); imp.add_argument('--run', type=Path, required=True)
    select = commands.add_parser('select', allow_abbrev=False)
    select.add_argument('--ensemble', type=Path, required=True)
    for flag, kind, default in [('energy-window', float, 6.), ('rmsd', float, .1), ('max-selected', int, 32), ('max-pairs', int, 1024), ('max-candidates', int, 64), ('max-search', int, 20000)]:
        select.add_argument('--' + flag, type=kind, default=default)
    sample = commands.add_parser('sample', allow_abbrev=False)
    sample.add_argument('--input', type=Path, required=True)
    sample.add_argument('--mode', choices=['assemble', 'perturb'], required=True)
    for flag, kind, default in [('samples', int, 16), ('max-attempts', int, 256), ('seed', int, 0), ('min-separation', float, 3.), ('max-separation', float, 6.), ('translation', float, .5), ('rotation-degrees', float, 30.), ('clash-scale', float, 1.2)]:
        sample.add_argument('--' + flag, type=kind, default=default)
    return p.parse_args(argv)

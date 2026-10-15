"""Pure CLI contracts for independent structure analysis Jobs."""
import argparse
import json
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description='Bounded structure correspondence and tensor analysis', allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    commands = parser.add_subparsers(dest='operation', required=True)
    for name in ('map', 'conformers'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--left', type=Path, required=True)
        command.add_argument('--right', type=Path, required=True)
        command.add_argument('--fixed-pairs', type=json.loads, default=[], help='Pairs of left/right local atom IDs')
        command.add_argument('--max-candidates', type=int, default=64)
        command.add_argument('--max-search', type=int, default=20000)
        if name == 'map':
            command.add_argument('--mode', choices=['identity', 'reaction'], default='reaction')
        else:
            command.add_argument('--rmsd-threshold', type=float, default=0.1, help='All-atom RMSD in angstrom')
            command.add_argument('--internal-coordinates', type=json.loads, default=[], help='Left atom IDs in groups of 2/3/4 for distance/angle/dihedral')
            command.add_argument('--distance-tolerance', type=float, default=0.1)
            command.add_argument('--angle-tolerance', type=float, default=10.)
    reorder = commands.add_parser('reorder', allow_abbrev=False)
    reorder.add_argument('--tensors', type=Path, required=True)
    reorder.add_argument('--order', type=Path, required=True)
    return parser.parse_args(argv)

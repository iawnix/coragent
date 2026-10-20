"""Pure command contracts for reaction-independent evidence checks."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description='Scoped stationary, mode and IRC evidence checks', allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    commands = parser.add_subparsers(dest='operation', required=True)
    for name in ('stationary', 'mode', 'irc', 'gaussian'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--material', type=Path, required=True)
        command.add_argument('--evidence', type=Path, required=True)
        if name == 'gaussian':
            command.add_argument('--kind', choices=['stationary', 'irc'], default='stationary')
            command.add_argument('--section-index', type=int)
            command.add_argument('--constraints', choices=['none', 'unknown'], default='unknown', help='Explicit knowledge of the calculation input, not inferred from termination')
        else:
            command.add_argument('--negative-threshold', type=float, default=20., help='Magnitude in cm-1; smaller negative values remain unresolved')
            command.add_argument('--near-zero', type=float, default=10., help='Magnitude in cm-1 for unresolved flat modes')
        if name == 'stationary':
            command.add_argument('--kind', choices=['minimum', 'saddle'], default='saddle')
        if name == 'mode':
            command.add_argument('--coordinates', type=Path, required=True)
            command.add_argument('--step', type=float, default=.05, help='Normalized Cartesian displacement length in angstrom')
        if name == 'irc':
            command.add_argument('--forward', type=Path, required=True)
            command.add_argument('--reverse', type=Path, required=True)
            command.add_argument('--reactant', type=Path, required=True)
            command.add_argument('--product', type=Path, required=True)
            command.add_argument('--endpoint-rmsd', type=float, default=.2, help='Reference-conformer diagnostic only; not a chemical identity gate')
            command.add_argument('--energy-tolerance', type=float, default=1e-6, help='Allowed upward numerical noise per path step, hartree')
            command.add_argument('--max-step-rmsd', type=float, default=1., help='Fixed-atom aligned jump screen, angstrom; declare a justified bound for the path sampling')
            command.add_argument('--origin-rmsd', type=float, default=.01)
            command.add_argument('--max-search', type=int, default=20000)
            command.add_argument('--max-candidates', type=int, default=64)
    return parser.parse_args(argv)

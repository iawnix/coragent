"""Pure contract for the bounded CREST 3.0.2 command profile."""
import argparse
import math
from pathlib import Path
import re


def parse_arguments(argv=None):
    p = argparse.ArgumentParser(description='Bounded CREST search; retain primary and partial outputs', allow_abbrev=False)
    p.add_argument('--material', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--executable', required=True)
    p.add_argument('--method', choices=['gfn1', 'gfn2'], default='gfn2')
    p.add_argument('--search-level', choices=['normal', 'quick', 'squick', 'mquick'], default='normal')
    p.add_argument('--opt-level', choices=['normal', 'tight', 'vtight'], default='vtight')
    p.add_argument('--threads', type=int, default=1)
    p.add_argument('--timeout', type=float, default=3600., help='Wall time in seconds for the search')
    p.add_argument('--energy-window', type=float, default=6., help='CREST ewin in kcal/mol')
    p.add_argument('--solvent', help='ALPB solvent; omitted means gas phase')
    p.add_argument('--max-members', type=int, default=256)
    a = p.parse_args(argv)
    if not 1 <= a.threads <= 256 or not 1 <= a.max_members <= 1024:
        p.error('threads must be 1..256 and max-members 1..1024')
    if any(not math.isfinite(v) or v <= 0 for v in (a.timeout, a.energy_window)):
        p.error('timeout and energy-window must be finite and positive')
    if a.solvent and not re.fullmatch(r'[A-Za-z0-9_+-]+', a.solvent):
        p.error('solvent must be a single solvent identifier')
    return a

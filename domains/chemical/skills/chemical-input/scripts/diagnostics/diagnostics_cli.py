"""Pure argument contract for local reaction-center diagnostics."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    return p.parse_args(argv)

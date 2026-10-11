"""Pure CLI for evidence trajectories and research report packages."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('operation',choices=('trajectory','report'))
    return p.parse_args(argv)

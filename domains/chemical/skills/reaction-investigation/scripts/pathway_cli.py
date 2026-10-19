import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser=argparse.ArgumentParser(description='Audit explicit multistep pathway evidence',allow_abbrev=False)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    return parser.parse_args(argv)

import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser=argparse.ArgumentParser(description='Bound state energies/gradients and AO transition-character tracking',allow_abbrev=False)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('operation',choices=('run','track'))
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--executable')
    args=parser.parse_args(argv)
    if args.operation=='run' and not args.executable:parser.error('run requires configured executable')
    return args

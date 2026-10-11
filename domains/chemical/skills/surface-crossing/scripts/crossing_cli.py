import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser=argparse.ArgumentParser(description='Bounded distinct-spin crossing search and numerical seam checks',allow_abbrev=False)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('operation',choices=('mecp','check'))
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--executable')
    args=parser.parse_args(argv)
    if args.operation=='mecp' and not args.executable:parser.error('mecp requires configured Gaussian executable')
    return args

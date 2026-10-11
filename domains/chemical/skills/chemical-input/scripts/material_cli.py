"""Standard-library-only contract for provenance-preserving material import."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description='Import SMILES, name or XYZ material without geometry generation', allow_abbrev=False)
    parser.add_argument('--input', type=Path, required=True, help='chemical-material-input/1 JSON')
    parser.add_argument('--output-dir', type=Path, required=True)
    return parser.parse_args(argv)

"""Pure candidate generation CLI contract; no scientific imports."""
import argparse
from pathlib import Path


def parse_arguments(argv=None):
    p=argparse.ArgumentParser(description="Prepare mapped QST2 or bidirectional IRC inputs",
        epilog="Use chemical-path-spec/1 with transformation.kind=explicit and complete bond_changes. "
               "Candidate strategies: mapped_endpoints (single-fragment embedding), provided_endpoints "
               "(mapped geometry rows), or the legacy diels_alder strategy. IRC preparation accepts "
               "explicit transformations without a DA topology; checkpoint scientific provenance must be checked separately.",
        allow_abbrev=False)
    sub=p.add_subparsers(dest='action',required=True)
    for name in ('candidates','irc'):
        command=sub.add_parser(name,allow_abbrev=False)
        command.add_argument('--spec',required=True,type=Path,
            help='Path JSON: mapped_smiles, transformation, method/basis, charge/multiplicity, threads/memory_mb; candidate_strategy and endpoints select candidate geometry')
        command.add_argument('--output-dir',required=True,type=Path,help='Empty destination for generated inputs and their digest manifest')
        if name=='candidates':
            command.add_argument('--conformers',type=int,default=1);command.add_argument('--enumerate-stereo',action='store_true')
        else:
            command.add_argument('--checkpoint',type=Path,required=True);command.add_argument('--max-points',type=int,default=80)
    return p.parse_args(argv)

"""Offline structure-environment check, independent of external name services."""
import json
from pathlib import Path

from rdkit import Chem

assert Chem.MolFromSmiles('CCO').GetNumAtoms() == 3
Path('structure-check.json').write_text(json.dumps({'graph': 'passed',
                                                  'external_services': 'not_checked'}) + '\n')

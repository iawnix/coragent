"""Compatibility entrypoint; implementation moved to ``neb/ase_search.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'neb/ase_search.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

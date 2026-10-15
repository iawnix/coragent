"""Compatibility entrypoint; implementation moved to ``search/gradient_contract.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'search/gradient_contract.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

"""Compatibility entrypoint; implementation moved to ``reaction/correspondence.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'reaction/correspondence.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

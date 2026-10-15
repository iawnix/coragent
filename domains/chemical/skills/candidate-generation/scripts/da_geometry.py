"""Compatibility entrypoint; implementation moved to ``da/da_geometry.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'da/da_geometry.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

"""Compatibility entrypoint; implementation moved to ``materials/material.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'materials/material.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

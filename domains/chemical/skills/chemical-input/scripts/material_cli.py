"""Compatibility entrypoint; implementation moved to ``materials/material_cli.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'materials/material_cli.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

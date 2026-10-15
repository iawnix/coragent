"""Compatibility entrypoint; implementation moved to ``materials/analysis_material.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'materials/analysis_material.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

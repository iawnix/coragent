"""Compatibility entrypoint; implementation moved to ``path/path_geometry.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'path/path_geometry.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

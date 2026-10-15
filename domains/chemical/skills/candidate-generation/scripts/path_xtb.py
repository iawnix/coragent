"""Compatibility entrypoint; implementation moved to ``backends/path_xtb.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'backends/path_xtb.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

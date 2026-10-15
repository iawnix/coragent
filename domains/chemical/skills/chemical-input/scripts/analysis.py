"""Compatibility entrypoint; implementation moved to ``geometry/analysis.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'geometry/analysis.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

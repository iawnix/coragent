"""Compatibility entrypoint; implementation moved to ``diagnostics/local_diagnostics.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'diagnostics/local_diagnostics.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

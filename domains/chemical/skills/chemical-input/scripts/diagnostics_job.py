"""Compatibility entrypoint; implementation moved to ``diagnostics/diagnostics_job.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'diagnostics/diagnostics_job.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

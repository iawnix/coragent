"""Compatibility entrypoint; implementation moved to ``geometry/analysis_cli.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'geometry/analysis_cli.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

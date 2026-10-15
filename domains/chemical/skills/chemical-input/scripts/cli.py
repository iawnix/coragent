"""Compatibility entrypoint; implementation moved to ``reaction/cli.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'reaction/cli.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

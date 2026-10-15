"""Compatibility entrypoint; implementation moved to ``reaction/prepare.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'reaction/prepare.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

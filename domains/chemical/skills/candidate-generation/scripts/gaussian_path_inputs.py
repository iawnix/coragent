"""Compatibility entrypoint; implementation moved to ``path/gaussian_path_inputs.py``."""
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / 'path/gaussian_path_inputs.py'
globals()['__file__'] = str(_TARGET)
exec(compile(_TARGET.read_text(), str(_TARGET), 'exec'), globals())

"""Standalone launcher for staged Python tools; no control-plane dependencies."""
import json
from pathlib import Path
import runpy
import re
import sys
import traceback


def diagnostic(exc):
    """Keep actionable validation errors without echoing arbitrary input payloads."""
    message = str(exc) or type(exc).__name__
    message = re.sub(r'''(?i)(["']?(?:password|token|secret|api[_-]?key|authorization)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)''',
                     r'\1[redacted]', message)
    message = re.sub(r'(?i)bearer\s+\S+', 'Bearer [redacted]', message)
    message = re.sub(r'(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[redacted]@', message)
    message = message.splitlines()[0][:500]
    frames = traceback.extract_tb(exc.__traceback__)
    location = 'staged Python tool'
    if frames:
        filename = Path(frames[-1].filename)
        if filename.is_relative_to(Path.cwd()):
            location = f'{filename.relative_to(Path.cwd())}:{frames[-1].lineno}'
    return {'message': message, 'location': location,
            'next_step': 'Inspect the reported field or dependency and correct it before retrying unchanged input'}



def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        paths = json.loads(args.pop(0))
        entry = Path(args[0]).resolve(strict=True)
        root = Path.cwd().resolve()
        if not entry.is_relative_to(root) or not isinstance(paths, list):
            raise ValueError('entrypoint_path_invalid')
        imports = [str(entry.parent)]
        for value in paths:
            relative = Path(value)
            path = (root / relative).resolve(strict=True)
            if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(root) or not path.is_dir():
                raise ValueError('entrypoint_import_path_invalid')
            imports.append(str(path))
        sys.path[:0] = imports
        sys.argv = [str(entry), *args[1:]]
        runpy.run_path(str(entry), run_name='__main__')
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0 if exc.code is None else 1
    except Exception as exc:
        print(json.dumps({'schema_version': 'entrypoint-error/1', 'stage': 'python_entrypoint',
                          'code': 'module_unavailable' if isinstance(exc, ModuleNotFoundError) else 'entrypoint_failed',
                          'exception_type': type(exc).__name__,
                          **(diagnostic(exc) if isinstance(exc, (ValueError, FileNotFoundError, ImportError)) else {}),
                          **({'module': exc.name} if isinstance(exc, ModuleNotFoundError) else {})}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

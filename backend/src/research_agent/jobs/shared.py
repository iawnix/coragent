"""Checks for executing directly in a controller Job directory on shared storage."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import shlex
import tempfile


class SharedDirectory:
    def __init__(self, root, run_command):
        self.root = Path(root).resolve()
        self.run_command = run_command

    def directory(self, cwd, *, job=False):
        directory = Path(cwd).resolve()
        if not directory.is_relative_to(self.root) or (job and directory == self.root):
            raise ValueError("shared Job directory must be below work_root")
        if not directory.is_dir():
            raise ValueError("shared Job directory is unavailable")
        return directory

    @staticmethod
    def check_path(root, path, *, recursive=False):
        path = Path(path)
        if '..' in path.parts or not path.is_relative_to(root):
            raise ValueError("shared path escapes Job directory")
        current = root
        for part in path.relative_to(root).parts:
            current /= part
            if current.is_symlink():
                raise ValueError("shared Job paths must not contain symlinks")
        if recursive and path.is_dir() and any(child.is_symlink() for child in path.rglob('*')):
            raise ValueError("shared output directory contains a symlink")

    def probe(self, cwd):
        """Prove that command transport and controller see the same writable file."""
        directory = self.directory(cwd)
        token = secrets.token_hex(32)
        with tempfile.NamedTemporaryFile('w', prefix='.coragent-storage-', dir=directory) as stream:
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
            path = Path(stream.name)
            quoted = shlex.quote(str(path))
            result = self.run_command(
                f'test "$(cat -- {quoted})" = {shlex.quote(token)} && '
                f'printf %s {shlex.quote(token + "-ack")} > {quoted}', check=False)
            if result.returncode or path.is_symlink() or path.read_text() != token + '-ack':
                raise ValueError("shared storage round-trip failed; no files were staged")

    def prepare(self, spec):
        directory = self.directory(spec.cwd, job=True)
        for path in (*spec.inputs, *((spec.stdin,) if spec.stdin else ())):
            self.check_path(directory, path.absolute(), recursive=path.is_dir())
            if not path.exists():
                raise ValueError("shared Job inputs must already exist in the Job directory")
        for name in ('logs', '.coragent'):
            path = directory / name
            self.check_path(directory, path)
            path.mkdir(mode=0o700, exist_ok=True)
        token = secrets.token_hex(32)
        path = directory / '.coragent/shared-token'
        self.check_path(directory, path)
        with path.open('x') as stream:
            os.chmod(path, 0o600)
            stream.write(token)
        return token

    @staticmethod
    def guard(directory, token):
        """Run on the allocated compute node, before starting the calculation."""
        quoted = shlex.quote(str(directory))
        return ('umask 077\n'
                f'cd {quoted} || exit 125\n'
                f'test "$(pwd -P)" = {quoted} || exit 125\n'
                'test ! -L .coragent && test ! -L .coragent/shared-token && '
                'test ! -L .coragent/execution-started || exit 125\n'
                f'test "$(cat .coragent/shared-token)" = {shlex.quote(token)} || exit 125\n'
                f'printf %s {shlex.quote(token)} > .coragent/execution-started || exit 125\n')

    def check_receipt(self, receipt, *, success=False):
        directory = self.directory(receipt.cwd, job=True)
        token = receipt.metadata.get('shared_token')
        if (str(directory) != receipt.metadata['remote_dir'] or
                not isinstance(token, str) or len(token) != 64):
            raise ValueError("shared Job storage identity mismatch")
        expected = {'.coragent/shared-token': token}
        if success:
            expected.update({'.coragent/execution-started': token, 'status.exit': '0'})
        for name, value in expected.items():
            path = directory / name
            self.check_path(directory, path)
            if not path.is_file() or path.read_text().strip() != value:
                raise ValueError("shared Job execution evidence unavailable or mismatched")

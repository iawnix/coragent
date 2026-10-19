"""Command and file access, independently of the task scheduler."""
from __future__ import annotations

from pathlib import Path
import shlex
import shutil

from .environment import _capture


class LocalTransport:
    name = "local"

    def __init__(self, config):
        self.timeout = int(config.get("command_timeout_seconds", 60))
        self.root = Path(config["work_root"]).resolve()

    def run(self, script, *, check=True):
        result = _capture(["/bin/sh", "-c", script], timeout=self.timeout)
        if check:
            result.check_returncode()
        return result

    def copy(self, source: Path, destination: str, *, pull=False):
        if pull:
            raise ValueError("local collection requires explicit output paths")
        target = Path(destination)
        if source.is_dir():
            if target.resolve().is_relative_to(source.resolve()):
                raise ValueError("execution directory must be outside the controller job directory")
            shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)

    def pull(self, source: str, destination: Path, *, recursive=False):
        path = Path(source)
        if not path.exists() and not path.is_symlink():
            return False
        if path.is_symlink() or not path.resolve().is_relative_to(self.root) or destination.is_symlink():
            raise ValueError("local output transfer escapes execution storage or targets a symlink")
        if recursive and path.is_dir():
            for child in path.rglob('*'):
                if child.is_symlink():
                    raise ValueError("local output directory contains a symlink")
                target = destination / child.relative_to(path)
                if target.is_symlink():
                    raise ValueError("local output destination contains a symlink")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if recursive and path.is_dir() and not path.is_symlink():
            shutil.copytree(path, destination, dirs_exist_ok=True, symlinks=True)
        else:
            shutil.copy2(path, destination, follow_symlinks=False)
        return True


class SSHTransport:
    name = "ssh"

    def __init__(self, config, *, capture=_capture):
        self.capture = capture
        self.host = config["ssh_host"]
        self.ssh_config = config.get("ssh_config")
        self.connect_timeout = int(config.get("connect_timeout_seconds", 15))
        self.timeout = int(config.get("command_timeout_seconds", 60))
        self.transfer_timeout = int(config.get("transfer_timeout_seconds", 3600))

    def argv(self):
        command = ["ssh", "-o", f"ConnectTimeout={self.connect_timeout}", "-o", "BatchMode=yes"]
        if self.ssh_config:
            command.extend(["-F", str(self.ssh_config)])
        return [*command, self.host]

    def run(self, script, *, check=True):
        result = self.capture([*self.argv(), f"sh -lc {shlex.quote(script)}"], timeout=self.timeout)
        if check:
            result.check_returncode()
        return result

    def copy(self, source: Path, destination: str, *, pull=False):
        command = ["rsync", "-a", "--protect-args", "-e", shlex.join(self.argv()[:-1])]
        if pull:
            for path in ('spec.json', 'receipt.json', 'status.json', 'input_manifest.json',
                         'supervisor.json', 'remote.json', 'cancel.request', '.coragent', '.scratch'):
                command.append('--exclude=/' + path)
            command.extend([f"{self.host}:{destination}/", str(source) + "/"])
        else:
            target = f"{self.host}:{destination}" + ("/" if source.is_dir() else "")
            command.extend([str(source) + ("/" if source.is_dir() else ""), target])
        self.capture(command, timeout=self.transfer_timeout).check_returncode()

    def pull(self, source: str, destination: Path, *, recursive=False):
        if self.run(f"test -e {shlex.quote(source)}", check=False).returncode:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = ["rsync", "-a", "--protect-args", "-e", shlex.join(self.argv()[:-1]),
                   f"{self.host}:{source}" + ("/" if recursive else ""),
                   str(destination) + ("/" if recursive else "")]
        self.capture(command, timeout=self.transfer_timeout).check_returncode()
        return True

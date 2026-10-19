"""Shared staging, execution wrappers and output collection."""
from __future__ import annotations

import hashlib
import os
from .outputs import collect_outputs
import json
import re
import shlex
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import JobReceipt, JobSpec, JobState, JobStatus
from .platform import ExecutionPlatform
from .config_contract import execution_timeout
from .process_environment import job_process_environment
from .transport import LocalTransport, SSHTransport
from .shared import SharedDirectory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StagedJobPlatform(ExecutionPlatform):
    """Shared staging, wrappers and collection for command-backed targets."""

    name = "external"

    def __init__(self, config: dict[str, Any], *, platform_name: str = "external") -> None:
        self.config = dict(config)
        self.name = platform_name
        self.transport = LocalTransport(config) if config["transport"] == "local" else SSHTransport(config)
        self.host = config.get("ssh_host")
        self.remote_root = config["work_root"].rstrip("/")
        self.file_mode = config.get('file_mode', 'staged')
        if self.file_mode not in ('staged', 'shared'):
            raise ValueError('external file_mode must be staged or shared')
        self.shared = SharedDirectory(self.remote_root, self.run_command) if self.file_mode == 'shared' else None
        self.allowed_queues = tuple(config.get("allowed_queues", ()))

    def run_command(self, script: str, *, check: bool = True):
        return self.transport.run(script, check=check)

    def _pull_path(self, remote_path: str, local_path: Path, *, recursive: bool = False):
        return self.transport.pull(remote_path, local_path, recursive=recursive)

    def _remote_dir(self, spec: JobSpec) -> str:
        job_id = spec.job_id
        if not isinstance(job_id, str) or not re.fullmatch(r"job_[1-9][0-9]*", job_id):
            raise ValueError("remote job id has an invalid format")
        if self.shared:
            return str(self.shared.directory(spec.cwd, job=True))
        scope = hashlib.sha256(str(spec.cwd.resolve()).encode()).hexdigest()[:24]
        return f"{self.remote_root}/{job_id}-{scope}"

    def stage_inputs(self, spec: JobSpec) -> dict[str, Any]:
        remote_dir = self._remote_dir(spec)
        if self.shared:
            return {'remote_dir': remote_dir, 'shared_token': self.shared.prepare(spec)}
        self.run_command(f"umask 077; mkdir -p {shlex.quote(remote_dir)}/logs {shlex.quote(remote_dir)}/.coragent")
        self.transport.copy(spec.cwd, remote_dir)
        for path in spec.inputs:
            if not path.resolve().is_relative_to(spec.cwd.resolve()):
                self.transport.copy(path, f"{remote_dir}/{path.name}")
        return {"remote_dir": remote_dir}

    def _wrapper(self, spec, remote_dir, *, inherit_environment=()):
        variables, scratch = job_process_environment(remote_dir, spec.metadata, spec.env)
        timeout = execution_timeout(spec.timeout_seconds, spec.metadata.get('resources', {}))
        argv = list(spec.command)
        if timeout is not None:
            record_exit = ('"$@"; code=$?; printf "%s\\n" "$code" > .coragent/command.exit; exit "$code"')
            argv = ['timeout', '--signal=TERM', '--kill-after=5', str(timeout),
                    '/bin/sh', '-c', record_exit, 'coragent-command', *argv]
        stdin = '/dev/null'
        if spec.stdin:
            path = spec.stdin.resolve()
            if path.is_relative_to(spec.cwd.resolve()):
                stdin = remote_dir + '/' + str(path.relative_to(spec.cwd.resolve()))
            elif path in [item.resolve() for item in spec.inputs]:
                stdin = remote_dir + '/' + path.name
            else:
                raise ValueError('remote stdin must be a staged Job input')
        script = ('set +e\numask 077\n'
                  + 'mkdir -p -- ' + shlex.quote(scratch) + ' || exit 125\n'
                  + 'cd ' + shlex.quote(remote_dir) + ' || exit 125\n'
                  + 'rm -f .coragent/command.exit\n'
                  + shlex.join(argv) + ' < ' + shlex.quote(stdin) + ' > logs/stdout.log 2> logs/stderr.log\n'
                  + 'code=$?\n')
        # A program may itself exit 124/137. Its own exit receipt distinguishes
        # that failure from termination of the timeout process group.
        if timeout is not None:
            script += ('if { [ "$code" = 124 ] || [ "$code" = 137 ]; } && [ ! -f .coragent/command.exit ]; then '
                       'printf "timed_out\\n" > status.state.tmp; mv status.state.tmp status.state; fi\n')
        script += 'printf "%s\\n" "$code" > status.exit.tmp; mv status.exit.tmp status.exit\nexit "$code"\n'
        # Scheduler/login variables are not inherited by the scientific process.
        # HOME is supplied by the remote account, never by the submitting Host.
        wrapper = '#!/bin/sh\nexec /usr/bin/env -i HOME="$HOME" '
        for key in inherit_environment:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                raise ValueError("invalid inherited process variable")
            wrapper += f'{key}="${{{key}-}}" '
        wrapper += shlex.join([f'{key}={value}' for key, value in variables.items()])
        wrapper += ' /bin/sh -c ' + shlex.quote(script) + '\n'
        return wrapper, scratch, timeout

    def collect(self, receipt: JobReceipt) -> dict[str, Any]:
        status = self.status(receipt)
        if status.state in {JobState.RUNNING, JobState.UNKNOWN, JobState.QUEUED, JobState.HELD, JobState.SUBMITTED}:
            raise RuntimeError(f"job {receipt.job_id} is not complete: {status.state}")
        root = Path(receipt.cwd)
        if self.shared:
            self.shared.check_receipt(receipt, success=status.state == JobState.SUCCEEDED)
            root = root.resolve()
        remote_dir = str(receipt.metadata["remote_dir"])
        spec_path = root / "spec.json"
        declared = json.loads(spec_path.read_text(encoding="utf-8")).get("outputs", []) if spec_path.is_file() else []
        # Pull only the declared result surface and bounded diagnostics. The
        # remote work directory may contain large scratch files or untrusted
        # calculation intermediates that do not belong in the local receipt.
        for relative in ("logs/stdout.log", "logs/stderr.log", "logs/scheduler.stdout", "logs/scheduler.stderr",
                         "scheduler.json"):
            if not (root / relative).resolve().is_relative_to(root.resolve()):
                raise ValueError("log destination escapes job cwd")
            if self.shared:
                self.shared.check_path(root, root / relative)
            else:
                self._pull_path(remote_dir + "/" + relative, root / relative)
        for output in declared:
            relative = output.get("path") if isinstance(output, dict) else None
            if not isinstance(relative, str):
                continue
            output_path = Path(relative)
            if (output_path.is_absolute() or '..' in output_path.parts or output_path == Path('.') or
                    output_path.parts[0] in {'spec.json', 'receipt.json', 'status.json', 'input_manifest.json',
                                            'supervisor.json', 'remote.json', 'cancel.request', '.coragent', '.scratch'}):
                raise ValueError("output path overlaps Job control files or escapes job cwd")
            if not (root / output_path).resolve().is_relative_to(root.resolve()):
                raise ValueError("output destination escapes job cwd")
            if self.shared:
                self.shared.check_path(root, root / output_path, recursive=bool(output.get('recursive', False)))
            else:
                self._pull_path(remote_dir + "/" + output_path.as_posix(), root / output_path,
                                recursive=bool(output.get("recursive", False)))
        outputs, validation = collect_outputs(root, declared)
        return {
            "job_id": receipt.job_id, "status": status.__dict__, "outputs": outputs, "output_validation": validation,
            "stdout": str(root / "logs" / "stdout.log"), "stderr": str(root / "logs" / "stderr.log"),
        }

    @staticmethod
    def _cancellation_acknowledged(receipt):
        try:
            value = json.loads((Path(receipt.cwd) / 'cancel.request').read_text())
            return (value.get('schema_version') == 'external-cancellation/1' and
                    value.get('scheduler_id') == receipt.metadata.get('scheduler_id'))
        except (OSError, ValueError, AttributeError):
            return False

    @staticmethod
    def _persist(receipt: JobReceipt, status: JobStatus) -> None:
        StagedJobPlatform._write(Path(receipt.cwd) / 'status.json', {
            'job_id': status.job_id, 'state': status.state.value,
            'platform': status.platform, 'exit_code': status.exit_code,
            'started_at': status.started_at, 'finished_at': status.finished_at,
            'error': status.error, 'diagnostics': dict(status.diagnostics),
        })

    @staticmethod
    def _write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix='.' + path.name, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                json.dump(value, stream, indent=2, default=str)
                stream.flush()
                os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def receipt_from_disk(path: str | Path) -> JobReceipt:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return JobReceipt(
            job_id=str(value["job_id"]), platform=str(value["platform"]),
            submitted_at=str(value["submitted_at"]), command=tuple(value["command"]),
            cwd=str(value["cwd"]), pid=value.get("pid"), metadata=value.get("metadata", {}),
            workspace_id=value.get("workspace_id"),
        )

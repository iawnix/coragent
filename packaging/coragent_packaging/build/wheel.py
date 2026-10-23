"""Build the Python distribution; validation contracts live in manifests."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from coragent_packaging.manifests._wheel import (
    PYTHON_DISTRIBUTION, SOURCE_DATE_EPOCH, WheelContractError,
    _wheel_package_names, inspect_wheel, package_identity, source_payload_sha256,
)

def build_wheel(
    package_root: str | Path,
    output_dir: str | Path,
    *,
    python: str | Path = sys.executable,
) -> dict[str, Any]:
    """Build one deterministic wheel from a temporary writable source copy."""

    root = Path(package_root).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    existing = sorted(path.name for path in destination.glob("*.whl"))
    if existing:
        raise WheelContractError(f"wheel output directory is not empty: {', '.join(existing)}")

    with tempfile.TemporaryDirectory(prefix="coragent-wheel-source-") as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        project = root / "backend"
        shutil.copy2(project / "pyproject.toml", source / "pyproject.toml")
        shutil.copytree(project / "src", source / "src",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.egg-info"))

        environment = dict(os.environ)
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
        completed = subprocess.run(
            [
                str(Path(python).expanduser()),
                "-m",
                "pip",
                "wheel",
                "--disable-pip-version-check",
                "--no-build-isolation",
                "--no-deps",
                "--no-cache-dir",
                "--wheel-dir",
                str(destination),
                str(source),
            ],
            cwd=source,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "wheel build failed"
            raise WheelContractError(detail)

    created = list(destination.glob("*.whl"))
    if len(created) != 1:
        names = ", ".join(sorted(path.name for path in created)) or "none"
        raise WheelContractError(f"wheel build must create exactly one artifact; found: {names}")
    descriptor = inspect_wheel(created[0])
    package = package_identity(root)
    if descriptor["name"] != PYTHON_DISTRIBUTION or descriptor["version"] != package["version"].replace("-rc.", "rc"):
        raise WheelContractError("wheel identity does not match package.json")
    source_digest = source_payload_sha256(root, package_names=_wheel_package_names(created[0]))
    if descriptor["payload_sha256"] != source_digest:
        raise WheelContractError("wheel payload does not match the authored Python source")
    return descriptor

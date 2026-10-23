"""Installer service contracts also work before third-party Python is installed."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from coragent_packaging.installer.install_from_github import install_uninstaller


def test_recovery_bundle_contains_the_complete_stdlib_configuration_boundary(tmp_path):
    source = Path(__file__).resolve().parents[2]
    root = tmp_path / "installation"
    install_uninstaller(root, source)
    maintenance = root / "runtimes/maintenance"
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    script = """
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path[:0] = [str(root / 'backend/src'), str(root / 'packaging')]
from research_agent.integrations.email_config import parse_email_config
from research_agent.bootstrap.name_resolver_config import parse_config
from coragent_packaging.installer.uninstall import parse_args
print(json.dumps({'email': parse_email_config({'enabled': False}),
                  'resolver': parse_config({'backends': {}}, package_root=root),
                  'site_loaded': 'site' in sys.modules}))
"""
    result = subprocess.run([sys.executable, "-S", "-B", "-c", script, str(maintenance)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "email": {"enabled": False}, "resolver": {"default_resolver": "auto", "backends": {}},
        "site_loaded": False,
    }

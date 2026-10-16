"""Explicit scheduler adapters used by SSH platform unit tests."""
from pathlib import Path
import sys

_PLUGIN_SRC = Path(__file__).resolve().parents[2] / "plugins" / "tspi-execution-pbs" / "src"
if str(_PLUGIN_SRC) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_SRC))

from tspi_execution_pbs.scheduler import PBSRemoteScheduler, TorqueRemoteScheduler


def torque(config):
    return TorqueRemoteScheduler(config)


def pbs(config):
    return PBSRemoteScheduler(config)

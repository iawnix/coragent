"""Built-in execution plugin implementations.

The job runtime imports only the scheduler adapter protocol.  These modules
are kept behind the plugin boundary so installations can replace them with
separately packaged PBS, Slurm, or tri drivers through entry points.
"""

from .schedulers import (
    DirectRemoteScheduler,
    PBSRemoteScheduler,
    SlurmRemoteScheduler,
    TorqueRemoteScheduler,
    TriRemoteScheduler,
    adapter_for,
)
from research_agent.jobs.scheduler import RemoteScheduler

__all__ = [
    "RemoteScheduler", "DirectRemoteScheduler", "PBSRemoteScheduler",
    "TorqueRemoteScheduler", "SlurmRemoteScheduler", "TriRemoteScheduler",
    "adapter_for",
]

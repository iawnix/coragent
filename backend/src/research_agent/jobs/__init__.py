"""Domain agnostic durable job execution primitives.

The package deliberately knows nothing about scientific programs, parsers, or
provider registries.  A job is a command plus declared inputs and outputs.
Interpretation of those outputs belongs to the caller (usually a Skill).
"""

from .models import (
    JobOutput,
    JobReceipt,
    JobSpec,
    JobState,
    JobStatus,
)
from .platform import ExecutionPlatform
from .local import LocalProcessPlatform
from .remote import RemoteExecutionPlatform, RemoteSSHPlatform, TorqueSSHPlatform
from .config import load_job_config, platforms_from_config
from .runtime import JobRuntime
from .registry import ExecutionPluginRegistry, PluginDescriptor

__all__ = [
    "ExecutionPlatform", "JobOutput", "JobReceipt", "JobRuntime", "JobSpec",
    "JobState", "JobStatus", "LocalProcessPlatform", "RemoteExecutionPlatform", "RemoteSSHPlatform", "TorqueSSHPlatform",
    "load_job_config", "platforms_from_config", "ExecutionPluginRegistry", "PluginDescriptor",
]

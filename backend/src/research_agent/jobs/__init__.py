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
from .external import ExternalJobPlatform
from .config import load_job_config, platforms_from_config
from .manager import JobManager

__all__ = [
    "ExecutionPlatform", "JobOutput", "JobReceipt", "JobManager", "JobSpec",
    "JobState", "JobStatus", "ExternalJobPlatform",
    "load_job_config", "platforms_from_config",
]

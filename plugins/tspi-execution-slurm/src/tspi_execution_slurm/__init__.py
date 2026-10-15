"""Standalone Slurm execution plugin."""

from .scheduler import SlurmRemoteScheduler

from .plugin import descriptor

__all__ = ["descriptor", "SlurmRemoteScheduler"]

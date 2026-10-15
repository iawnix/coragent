"""Standalone tri execution plugin."""

from .scheduler import TriRemoteScheduler

from .plugin import descriptor

__all__ = ["descriptor", "TriRemoteScheduler"]

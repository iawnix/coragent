"""PBS and Torque execution plugins for TSPi."""

from .scheduler import PBSRemoteScheduler, TorqueRemoteScheduler

__all__ = ["PBSRemoteScheduler", "TorqueRemoteScheduler"]

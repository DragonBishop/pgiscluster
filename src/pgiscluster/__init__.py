"""Module for pgiscluster."""

from pgiscluster.connector import (
    ClusterAdminDBConnector,
    ClusterDBConnector,
    HostAdminDBConnector,
    HostDBConnector,
)

__version__ = "0.4.0"

__all__ = [
    "ClusterAdminDBConnector",
    "ClusterDBConnector",
    "HostAdminDBConnector",
    "HostDBConnector",
]

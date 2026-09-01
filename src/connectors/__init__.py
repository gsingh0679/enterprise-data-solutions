"""Data connectors package for enterprise data platform.

This package provides abstract base classes and concrete implementations for
connecting to various data sources including cloud storage, message queues,
and databases.
"""

from src.connectors.base import Connector

__all__ = ["Connector"]

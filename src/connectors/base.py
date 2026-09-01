"""Abstract base class for all data connector implementations.

This module defines the Connector abstract base class that all concrete
connector implementations (storage, data sources, databases) must extend.
It establishes the interface for connection management, data operations,
and error handling.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

from src.config import ConnectorConfig
from src.errors import ConnectionError, ReadError, WriteError

logger = logging.getLogger(__name__)


class Connector(ABC):
    """Abstract base class for all data connector implementations.

    Defines the interface that all connector implementations must follow.
    Handles configuration, connection lifecycle management, and error tracking.

    Subclasses must implement the four abstract methods: connect(), read(),
    write(), and close().

    Attributes:
        config (ConnectorConfig): Immutable connector configuration.
        is_connected (bool): Whether connector is currently connected.
    """

    def __init__(self, config: ConnectorConfig) -> None:
        """Initialize connector with configuration.

        Args:
            config: ConnectorConfig instance with connection settings.

        Raises:
            TypeError: If config is not a ConnectorConfig instance.
            ValueError: If config validation fails.
        """
        if not isinstance(config, ConnectorConfig):
            raise TypeError(
                f"config must be ConnectorConfig instance, "
                f"got {type(config).__name__}"
            )

        self._config = config
        self._is_connected = False
        logger.debug(
            f"Connector initialized: connector_type={config.connector_type}, "
            f"tenant_id={config.tenant_id}"
        )

    @property
    def config(self) -> ConnectorConfig:
        """Get connector configuration (read-only).

        Returns:
            The immutable ConnectorConfig instance.
        """
        return self._config

    @property
    def is_connected(self) -> bool:
        """Check if connector is currently connected.

        Returns:
            True if connected to remote service, False otherwise.
        """
        return self._is_connected

    @property
    def connector_type(self) -> str:
        """Get connector type.

        Returns:
            The connector type from configuration.
        """
        return self._config.connector_type

    @property
    def tenant_id(self) -> str:
        """Get tenant ID.

        Returns:
            The tenant ID from configuration.
        """
        return self._config.tenant_id

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to remote service.

        Subclasses must implement this method to establish connections
        to their specific remote service (e.g., S3, Kafka, PostgreSQL).

        This method should:
        - Validate configuration before connecting
        - Authenticate with remote service using credentials
        - Set is_connected to True on success
        - Log connection attempts and outcomes
        - Raise ConnectionError on failure

        Raises:
            ConnectionError: If connection fails for any reason.
            ValidationError: If configuration is invalid.
        """
        pass  # pragma: no cover

    @abstractmethod
    def read(self, query: str) -> Any:
        """Read data from remote service.

        Subclasses must implement this method to read data according to
        the query/request specified. The semantics of 'query' depend on
        the connector type (SQL query for databases, path for storage, etc.).

        Args:
            query: Query string or request specification (semantics depend
                on connector type).

        Returns:
            Data read from the remote service. Type depends on connector.

        Raises:
            ReadError: If read operation fails.
            ConnectionError: If not currently connected.
            ValidationError: If query is invalid.
        """
        pass  # pragma: no cover

    @abstractmethod
    def write(self, data: Any) -> Dict[str, Any]:
        """Write data to remote service.

        Subclasses must implement this method to write data to their
        remote service. Returns status information about the write operation.

        Args:
            data: Data to write. Type and format depends on connector type.

        Returns:
            Status dictionary with keys:
            - success (bool): Whether write succeeded
            - rows_affected (int): Number of rows/items written
            - duration_ms (float): Write operation duration in milliseconds

        Raises:
            WriteError: If write operation fails.
            ConnectionError: If not currently connected.
            ValidationError: If data format is invalid.
        """
        pass  # pragma: no cover

    @abstractmethod
    def close(self) -> None:
        """Close connection to remote service.

        Subclasses must implement this method to cleanly close their
        connection to the remote service.

        This method should:
        - Close underlying client/connection objects
        - Set is_connected to False
        - Log disconnection
        - Handle errors gracefully (log but don't raise)

        The method should be idempotent (safe to call multiple times).
        """
        pass  # pragma: no cover

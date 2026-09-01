"""Custom exception types for connector and routing operations.

This module defines the exception hierarchy for the data connectors and
tenant-aware routing layer. All connector errors inherit from ConnectorError
for consistent error handling.
"""


class ConnectorError(Exception):
    """Base exception for all connector-related errors.

    This is the root exception type that all connector-specific errors
    inherit from. It should not be raised directly; use specific subclasses
    instead for clearer error semantics.

    Attributes:
        connector_type (str): Type of connector that raised the error.
        tenant_id (str): Tenant ID associated with the error.
    """

    def __init__(
        self,
        message: str,
        connector_type: str = None,
        tenant_id: str = None,
    ) -> None:
        """Initialize connector error with context.

        Args:
            message: The error message.
            connector_type: Optional type of connector (e.g., "s3", "kafka").
            tenant_id: Optional tenant ID for multi-tenant context.
        """
        self.connector_type = connector_type
        self.tenant_id = tenant_id
        context = []
        if connector_type:
            context.append(f"connector_type={connector_type}")
        if tenant_id:
            context.append(f"tenant_id={tenant_id}")
        context_str = f" [{', '.join(context)}]" if context else ""
        super().__init__(f"{message}{context_str}")


class ConnectionError(ConnectorError):
    """Raised when connector fails to establish or maintain connection.

    Covers connection establishment failures, authentication failures,
    network timeouts, and connection pool exhaustion.
    """

    pass


class ReadError(ConnectorError):
    """Raised when a read operation fails.

    Covers data retrieval failures, query execution failures, message
    consumption failures, and deserialization errors.
    """

    pass


class WriteError(ConnectorError):
    """Raised when a write operation fails.

    Covers data insertion/update failures, message production failures,
    serialization errors, and transaction failures.
    """

    pass


class ValidationError(ConnectorError):
    """Raised when configuration or data validation fails.

    Covers invalid connector configuration, malformed queries, invalid
    message formats, and type mismatches.
    """

    pass


class TenantAccessError(ConnectorError):
    """Raised when tenant access is denied.

    Covers cross-tenant access attempts, resource access violations,
    and ACL enforcement failures.
    """

    pass

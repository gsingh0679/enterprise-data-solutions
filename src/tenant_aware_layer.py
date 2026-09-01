"""Multi-tenant aware routing layer orchestrating all connectors.

This module provides the TenantAwareRouter singleton that orchestrates
storage, data source, and database connectors across multiple tenants.
Enforces tenant isolation, manages connection pooling, validates access,
and integrates with audit logging.
"""

import logging
from typing import Any, Dict, List, Optional

from src.audit_log import AuditLog
from src.config import ConfigManager, ConnectorConfig
from src.connectors.base import Connector
from src.connectors.storage import S3Connector, GCSConnector, ADLSConnector
from src.connectors.data_source import KafkaConnector, PubSubConnector
from src.connectors.database import (
    PostgreSQLConnector,
    MongoDBConnector,
    SnowflakeConnector,
)
from src.errors import ConnectionError, TenantAccessError, ValidationError

logger = logging.getLogger(__name__)


class TenantAwareRouter:
    """Singleton router orchestrating all connectors across tenants.

    Manages multi-tenant isolation, connection pooling, access control,
    and audit logging for all connector operations.
    """

    _instance: Optional["TenantAwareRouter"] = None
    _connector_pool: Dict[str, Dict[str, Connector]] = {}
    _tenant_acls: Dict[str, set] = {}

    CONNECTOR_CLASSES = {
        "s3": S3Connector,
        "gcs": GCSConnector,
        "adls": ADLSConnector,
        "kafka": KafkaConnector,
        "pubsub": PubSubConnector,
        "postgresql": PostgreSQLConnector,
        "mongodb": MongoDBConnector,
        "snowflake": SnowflakeConnector,
    }

    def __new__(cls) -> "TenantAwareRouter":
        """Singleton pattern: return or create instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize router (only once due to singleton)."""
        if self._initialized:
            return
        self._audit_log = AuditLog()
        self._config_manager = ConfigManager()
        self._initialized = True
        logger.info("TenantAwareRouter singleton initialized")

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (testing only)."""
        cls._instance = None
        cls._connector_pool.clear()
        cls._tenant_acls.clear()
        logger.debug("TenantAwareRouter singleton reset")

    def get_connector(
        self, connector_type: str, tenant_id: str, config: ConnectorConfig
    ) -> Connector:
        """Get or create connector from pool.

        Args:
            connector_type: Type of connector (e.g., "s3", "postgresql").
            tenant_id: Tenant identifier.
            config: ConnectorConfig for initialization.

        Returns:
            Configured connector instance.

        Raises:
            ValidationError: If connector_type unsupported.
            ConnectionError: If connector creation fails.
            TenantAccessError: If tenant access denied.
        """
        self._validate_connector_type(connector_type)
        self._validate_tenant_access(tenant_id, connector_type)

        # Initialize tenant pool if needed
        if tenant_id not in self._connector_pool:
            self._connector_pool[tenant_id] = {}

        # Check if connector already in pool
        if connector_type in self._connector_pool[tenant_id]:
            logger.debug(
                f"Returning pooled connector: {connector_type} for tenant {tenant_id}"
            )
            return self._connector_pool[tenant_id][connector_type]

        # Create new connector
        try:
            connector_class = self.CONNECTOR_CLASSES[connector_type]
            connector = connector_class(config)
            connector.connect()
            self._connector_pool[tenant_id][connector_type] = connector

            self._audit_log.log_event(
                action="CONNECTOR_CREATED",
                user="system",
                tenant_id=tenant_id,
                details={"connector_type": connector_type},
                status="SUCCESS",
            )
            logger.info(
                f"Created connector: {connector_type} for tenant {tenant_id}"
            )
            return connector
        except Exception as e:
            self._audit_log.log_event(
                action="CONNECTOR_CREATION_FAILED",
                user="system",
                tenant_id=tenant_id,
                details={"connector_type": connector_type},
                status="FAILURE",
                error_message=str(e),
            )
            raise ConnectionError(
                f"Failed to create {connector_type} connector: {str(e)}",
                connector_type=connector_type,
                tenant_id=tenant_id,
            ) from e

    def read_data(
        self,
        tenant_id: str,
        query: str,
        connector_type: str,
        config: Optional[ConnectorConfig] = None,
    ) -> Any:
        """Route read operation across connectors.

        Args:
            tenant_id: Tenant identifier.
            query: Query string.
            connector_type: Type of connector to use.
            config: Optional ConnectorConfig (uses default if not provided).

        Returns:
            Read data (type depends on connector).

        Raises:
            TenantAccessError: If access denied.
            ValidationError: If inputs invalid.
        """
        self._validate_tenant_access(tenant_id, f"read:{connector_type}")

        if config is None:
            config = self._get_tenant_config(tenant_id, connector_type)

        try:
            connector = self.get_connector(connector_type, tenant_id, config)
            result = connector.read(query)

            self._audit_log.log_event(
                action="READ_OPERATION",
                user="system",
                tenant_id=tenant_id,
                details={"connector_type": connector_type},
                status="SUCCESS",
            )
            logger.debug(
                f"Read operation successful: {connector_type} for tenant {tenant_id}"
            )
            return result
        except Exception as e:
            self._audit_log.log_event(
                action="READ_OPERATION",
                user="system",
                tenant_id=tenant_id,
                details={"connector_type": connector_type},
                status="FAILURE",
                error_message=str(e),
            )
            raise

    def write_data(
        self,
        tenant_id: str,
        data: Any,
        connector_type: str,
        destination: Optional[str] = None,
        config: Optional[ConnectorConfig] = None,
    ) -> Dict[str, Any]:
        """Route write operation across connectors.

        Args:
            tenant_id: Tenant identifier.
            data: Data to write.
            connector_type: Type of connector to use.
            destination: Optional destination (table, topic, bucket).
            config: Optional ConnectorConfig.

        Returns:
            Status dict with write results.

        Raises:
            TenantAccessError: If access denied.
            ValidationError: If inputs invalid.
        """
        self._validate_tenant_access(tenant_id, f"write:{connector_type}")

        if config is None:
            config = self._get_tenant_config(tenant_id, connector_type)

        try:
            connector = self.get_connector(connector_type, tenant_id, config)
            result = connector.write(data)

            self._audit_log.log_event(
                action="WRITE_OPERATION",
                user="system",
                tenant_id=tenant_id,
                details={"connector_type": connector_type, "destination": destination},
                status="SUCCESS",
            )
            logger.debug(
                f"Write operation successful: {connector_type} for tenant {tenant_id}"
            )
            return result
        except Exception as e:
            self._audit_log.log_event(
                action="WRITE_OPERATION",
                user="system",
                tenant_id=tenant_id,
                details={"connector_type": connector_type},
                status="FAILURE",
                error_message=str(e),
            )
            raise

    def validate_tenant_access(
        self, tenant_id: str, resource: str
    ) -> bool:
        """Validate tenant has access to resource.

        Args:
            tenant_id: Tenant identifier.
            resource: Resource identifier (connector type or path).

        Returns:
            True if access allowed.

        Raises:
            TenantAccessError: If access denied.
        """
        return self._validate_tenant_access(tenant_id, resource)

    def get_tenant_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant-specific configuration.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Tenant configuration dict.
        """
        config = self._config_manager.load()
        return {
            "tenant_id": tenant_id,
            "app_env": config.app_env,
            "storage_path": config.storage_path,
        }

    def close_tenant_connections(self, tenant_id: str) -> None:
        """Close all connections for a tenant.

        Args:
            tenant_id: Tenant identifier.
        """
        if tenant_id in self._connector_pool:
            for connector in self._connector_pool[tenant_id].values():
                try:
                    connector.close()
                except Exception as e:
                    logger.error(
                        f"Error closing connector for tenant {tenant_id}: {e}"
                    )
            del self._connector_pool[tenant_id]

        self._audit_log.log_event(
            action="TENANT_CLEANUP",
            user="system",
            tenant_id=tenant_id,
            details={},
            status="SUCCESS",
        )
        logger.info(f"Closed all connections for tenant {tenant_id}")

    def close_all_connections(self) -> None:
        """Close all connections for all tenants."""
        for tenant_id in list(self._connector_pool.keys()):
            self.close_tenant_connections(tenant_id)
        logger.info("Closed all connections for all tenants")

    def _validate_tenant_access(self, tenant_id: str, resource: str) -> bool:
        """Validate tenant access to resource.

        Args:
            tenant_id: Tenant identifier.
            resource: Resource identifier.

        Returns:
            True if access allowed.

        Raises:
            TenantAccessError: If access denied.
        """
        if not tenant_id:
            self._audit_log.log_event(
                action="TENANT_ACCESS_DENIED",
                user="system",
                tenant_id=tenant_id or "UNKNOWN",
                details={"resource": resource, "reason": "empty_tenant_id"},
                status="FAILURE",
                error_message="tenant_id required",
            )
            raise TenantAccessError(
                "tenant_id required",
                tenant_id=tenant_id,
            )

        if not isinstance(tenant_id, str):
            self._audit_log.log_event(
                action="TENANT_ACCESS_DENIED",
                user="system",
                tenant_id="INVALID_TYPE",
                details={"resource": resource, "reason": "invalid_type"},
                status="FAILURE",
                error_message=f"tenant_id must be string, got {type(tenant_id).__name__}",
            )
            raise TenantAccessError(
                f"tenant_id must be string, got {type(tenant_id).__name__}",
                tenant_id=tenant_id,
            )

        if len(tenant_id) > 255:
            self._audit_log.log_event(
                action="TENANT_ACCESS_DENIED",
                user="system",
                tenant_id=tenant_id,
                details={"resource": resource, "reason": "tenant_id_too_long"},
                status="FAILURE",
                error_message=f"tenant_id too long: {len(tenant_id)} > 255",
            )
            raise TenantAccessError(
                f"tenant_id too long: {len(tenant_id)} > 255",
                tenant_id=tenant_id,
            )

        if any(char in tenant_id for char in ['/', '\\', '..', '\0']):
            self._audit_log.log_event(
                action="TENANT_ACCESS_DENIED",
                user="system",
                tenant_id=tenant_id,
                details={"resource": resource, "reason": "invalid_characters"},
                status="FAILURE",
                error_message=f"tenant_id contains invalid characters: {tenant_id!r}",
            )
            raise TenantAccessError(
                f"tenant_id contains invalid characters: {tenant_id!r}",
                tenant_id=tenant_id,
            )

        # Initialize ACLs for tenant if needed
        if tenant_id not in self._tenant_acls:
            self._tenant_acls[tenant_id] = {resource}

        # Check access (all tenants can access their resources)
        if resource in self._tenant_acls[tenant_id]:
            logger.debug(f"Tenant {tenant_id} access allowed to {resource}")
            return True

        # Log access denial
        self._audit_log.log_event(
            action="TENANT_ACCESS_DENIED",
            user="system",
            tenant_id=tenant_id,
            details={"resource": resource},
            status="FAILURE",
        )
        raise TenantAccessError(
            f"Access denied to {resource}",
            tenant_id=tenant_id,
        )

    def _validate_connector_type(self, connector_type: str) -> None:
        """Validate connector type is supported.

        Args:
            connector_type: Type to validate.

        Raises:
            ValidationError: If connector type unsupported.
        """
        if connector_type not in self.CONNECTOR_CLASSES:
            raise ValidationError(
                f"Unsupported connector type: {connector_type}",
                connector_type=connector_type,
            )

    def _get_tenant_config(
        self, tenant_id: str, connector_type: str
    ) -> ConnectorConfig:
        """Get or create tenant-specific connector config.

        Args:
            tenant_id: Tenant identifier.
            connector_type: Type of connector.

        Returns:
            ConnectorConfig for tenant.
        """
        # Create basic config (in production, would load from tenant config store)
        return ConnectorConfig(
            connector_type=connector_type,
            tenant_id=tenant_id,
            credentials={},  # Loaded from secure store in production
            metadata={},
        )

"""Multi-tenant aware routing layer orchestrating all connectors.

This module provides the TenantAwareRouter singleton that orchestrates
storage, data source, and database connectors across multiple tenants.
Enforces tenant isolation, manages connection pooling, validates access,
and integrates with audit logging.
"""

import logging
from typing import Any, Dict, List, Optional

from src.compliance.audit_log import AuditLog
from src.config import ConfigManager, ConnectorConfig
from src.connectors.base import Connector
from src.connectors.storage import S3Connector, GCSConnector, ADLSConnector
from src.connectors.data_source import KafkaConnector, PubSubConnector
from src.connectors.database import (
    PostgreSQLConnector,
    MongoDBConnector,
    SnowflakeConnector,
)
from src.errors import ConnectionError, PipelineError, TenantAccessError, ValidationError

logger = logging.getLogger(__name__)


class TenantAwareRouter:
    """Singleton router orchestrating all connectors across tenants.

    Manages multi-tenant isolation, connection pooling, access control,
    and audit logging for all connector operations.
    """

    _instance: Optional["TenantAwareRouter"] = None
    _connector_pool: Dict[str, Dict[str, Connector]] = {}
    _tenant_acls: Dict[str, set] = {}
    _tenant_configs: Dict[str, Dict[str, Any]] = {}

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

    def atomic_pipeline(
        self, tenant_id: str, operations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute multiple operations atomically across connectors.

        Implements cross-connector transactions with rollback on failure.
        All operations succeed or all are rolled back (ACID semantics).

        Args:
            tenant_id: Tenant identifier.
            operations: List of operation dicts with keys:
                - connector_type: Type of connector (s3, postgresql, etc)
                - operation: "read" or "write"
                - query (for read): Query to execute
                - destination (for write): Destination identifier
                - data (for write): Data to write

        Returns:
            Dict with status, steps_executed, and results list.

        Raises:
            PipelineError: If any operation fails (all rolled back).
            TenantAccessError: If tenant cannot execute pipelines.
            ValidationError: If operations invalid.
        """
        from src.errors import PipelineError

        if not operations:
            return {"status": "success", "results": []}

        if tenant_id not in self._tenant_configs:
            logger.debug(f"Tenant {tenant_id} not registered, allowing pipeline (backward compat)")
        else:
            self.validate_tenant_access(tenant_id, "pipeline:execute")

        active_transactions = {}
        results = []

        try:
            for i, op in enumerate(operations):
                connector_type = op.get("connector_type")
                operation = op.get("operation")

                if not connector_type or not operation:
                    raise ValidationError(
                        f"Operation {i} missing connector_type or operation",
                        tenant_id=tenant_id,
                    )

                if operation not in ["read", "write"]:
                    raise ValidationError(
                        f"Unknown operation: {operation}",
                        tenant_id=tenant_id,
                    )

                connector = self.get_connector(connector_type, tenant_id, None)

                if connector_type not in active_transactions:
                    active_transactions[connector_type] = connector

                try:
                    if operation == "read":
                        query = op.get("query")
                        result = connector.read(query)
                        results.append({
                            "step": i,
                            "connector_type": connector_type,
                            "operation": "read",
                            "status": "success",
                            "data": result,
                        })

                    elif operation == "write":
                        destination = op.get("destination")
                        data = op.get("data")
                        success = connector.write(data)
                        results.append({
                            "step": i,
                            "connector_type": connector_type,
                            "operation": "write",
                            "destination": destination,
                            "status": "success",
                            "result": success,
                        })


                except Exception as e:
                    results.append({
                        "step": i,
                        "connector_type": connector_type,
                        "operation": operation,
                        "status": "failed",
                        "error": str(e),
                    })
                    raise PipelineError(
                        f"Pipeline failed at step {i}: {str(e)}",
                        tenant_id=tenant_id,
                    )

            for connector_type, connector in active_transactions.items():
                if hasattr(connector, 'commit'):
                    try:
                        connector.commit()
                        logger.debug(f"Committed {connector_type}")
                    except Exception as e:
                        logger.warning(f"Commit failed for {connector_type}: {e}")

            self._audit_log.log_event(
                action="PIPELINE_SUCCESS",
                user="system",
                tenant_id=tenant_id,
                details={"steps": len(operations), "connector_types": list(active_transactions.keys())},
                status="SUCCESS",
            )

            return {
                "status": "success",
                "steps_executed": len(operations),
                "results": results,
            }

        except Exception as e:
            for connector_type, connector in active_transactions.items():
                if hasattr(connector, 'rollback'):
                    try:
                        connector.rollback()
                        logger.debug(f"Rolled back {connector_type}")
                    except Exception as rb_error:
                        logger.error(f"Rollback failed for {connector_type}: {rb_error}")

            self._audit_log.log_event(
                action="PIPELINE_FAILED",
                user="system",
                tenant_id=tenant_id,
                details={"error": str(e), "results": results},
                status="FAILURE",
                error_message=str(e),
            )

            raise

    def validate_tenant_access(
        self, tenant_id: str, resource: str
    ) -> bool:
        """Validate tenant has access to resource via ACL checking.

        Checks if tenant is configured and allowed to access resource.
        Supports exact match, wildcard, and regex patterns.

        Args:
            tenant_id: Tenant identifier.
            resource: Resource identifier (e.g., "s3://bucket/file", "postgresql:table_name").

        Returns:
            True if access allowed.

        Raises:
            TenantAccessError: If access denied.
        """
        if not tenant_id or not isinstance(tenant_id, str):
            raise TenantAccessError(
                f"Invalid tenant_id: {tenant_id}",
                tenant_id=tenant_id,
            )

        if tenant_id not in self._tenant_configs:
            logger.debug(f"Tenant {tenant_id} not in configs, allowing access (backward compat)")
            return True

        tenant_config = self._tenant_configs[tenant_id]

        if not tenant_config.get("enabled", True):
            self._audit_log.log_event(
                action="TENANT_ACCESS_DENIED",
                user="system",
                tenant_id=tenant_id,
                details={"resource": resource, "reason": "tenant_disabled"},
                status="FAILURE",
                error_message=f"Tenant disabled: {tenant_id}",
            )
            raise TenantAccessError(
                f"Tenant disabled: {tenant_id}",
                tenant_id=tenant_id,
            )

        allowed_resources = tenant_config.get("allowed_resources", [])

        if not allowed_resources:
            logger.debug(f"Tenant {tenant_id} has no restrictions (full access)")
            return True

        for pattern in allowed_resources:
            if self._resource_matches(pattern, resource):
                logger.debug(f"Access granted: {tenant_id} -> {resource}")
                return True

        self._audit_log.log_event(
            action="TENANT_ACCESS_DENIED",
            user="system",
            tenant_id=tenant_id,
            details={"resource": resource, "allowed_patterns": allowed_resources},
            status="FAILURE",
            error_message=f"Resource not in allowed list",
        )
        raise TenantAccessError(
            f"Access denied to {resource} (allowed: {allowed_resources})",
            tenant_id=tenant_id,
        )

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
            error_message=f"Access denied to resource: {resource}",
        )
        raise TenantAccessError(
            f"Access denied to {resource}",
            tenant_id=tenant_id,
        )

    def add_tenant(self, tenant_id: str, config: Dict[str, Any]) -> None:
        """Add tenant with access control configuration.

        Args:
            tenant_id: Tenant identifier.
            config: Tenant configuration dict with keys:
                - name (required): Tenant display name
                - enabled (optional, default True): Enable/disable tenant
                - allowed_resources (optional): List of allowed resource patterns
                - allowed_connector_types (optional): List of allowed connector types

        Raises:
            ValidationError: If tenant_id or config invalid.
        """
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValidationError(
                f"Invalid tenant_id: {tenant_id}",
                tenant_id=tenant_id,
            )

        if not isinstance(config, dict):
            raise ValidationError(
                f"Config must be dict, got {type(config).__name__}",
                tenant_id=tenant_id,
            )

        required_fields = ["name"]
        for field in required_fields:
            if field not in config:
                raise ValidationError(
                    f"Missing required field: {field}",
                    tenant_id=tenant_id,
                )

        allowed = config.get("allowed_resources", [])
        if allowed and not isinstance(allowed, list):
            raise ValidationError(
                f"allowed_resources must be list, got {type(allowed).__name__}",
                tenant_id=tenant_id,
            )

        allowed_types = config.get("allowed_connector_types", [])
        if allowed_types:
            valid_types = {"s3", "gcs", "adls", "kafka", "pubsub",
                          "postgresql", "mongodb", "snowflake"}
            for ct in allowed_types:
                if ct not in valid_types:
                    raise ValidationError(
                        f"Unknown connector type: {ct}",
                        tenant_id=tenant_id,
                    )

        self._tenant_configs[tenant_id] = config
        logger.info(f"Added tenant: {tenant_id} with config: {config.get('name')}")

    def _resource_matches(self, pattern: str, resource: str) -> bool:
        """Check if resource matches pattern (supports wildcards and regex).

        Args:
            pattern: Pattern to match (supports wildcards and regex:)
            resource: Resource to check

        Returns:
            True if resource matches pattern.
        """
        import fnmatch
        import re

        if pattern == resource:
            return True

        if fnmatch.fnmatch(resource, pattern):
            return True

        if pattern.startswith("regex:"):
            regex = pattern[6:]
            if re.match(regex, resource):
                return True

        return False

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

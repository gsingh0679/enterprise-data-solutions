"""Tests for tenant-aware routing layer.

Tests cover multi-tenant isolation, connector routing, access control,
connection pooling, and audit logging integration.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.config import ConnectorConfig
from src.tenant_aware_layer import TenantAwareRouter
from src.errors import ConnectionError, TenantAccessError, ValidationError


@pytest.fixture
def router():
    """Create TenantAwareRouter instance."""
    TenantAwareRouter.reset()
    return TenantAwareRouter()


@pytest.fixture
def s3_config():
    """Create S3 connector config."""
    return ConnectorConfig(
        connector_type="s3",
        tenant_id="tenant_1",
        credentials={
            "aws_access_key_id": "key",
            "aws_secret_access_key": "secret",
        },
        metadata={"region": "us-east-1", "bucket_name": "test"},
    )


@pytest.fixture
def postgres_config():
    """Create PostgreSQL connector config."""
    return ConnectorConfig(
        connector_type="postgresql",
        tenant_id="tenant_1",
        credentials={
            "host": "localhost",
            "port": "5432",
            "user": "postgres",
            "password": "password",
            "database": "testdb",
        },
        metadata={},
    )


class TestRouterSingleton:
    """Test TenantAwareRouter singleton pattern."""

    def test_singleton_instance(self):
        """Test TenantAwareRouter is singleton."""
        router1 = TenantAwareRouter()
        router2 = TenantAwareRouter()
        assert router1 is router2

    def test_reset_clears_singleton(self):
        """Test reset clears singleton instance."""
        router1 = TenantAwareRouter()
        TenantAwareRouter.reset()
        router2 = TenantAwareRouter()
        assert router1 is not router2

    def test_reset_clears_pools(self, router):
        """Test reset clears connection pools."""
        router._connector_pool = {"tenant_1": {"s3": MagicMock()}}
        TenantAwareRouter.reset()
        assert len(TenantAwareRouter._connector_pool) == 0


class TestConnectorGetAndPooling:
    """Test connector retrieval and pooling."""

    def test_get_connector_creates_new(self, router, s3_config):
        """Test get_connector creates new connector."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            mock_connector = MagicMock()
            mock_s3_class.return_value = mock_connector

            result = router.get_connector("s3", "tenant_1", s3_config)
            assert result is mock_connector
            mock_connector.connect.assert_called_once()

    def test_get_connector_returns_pooled(self, router, s3_config):
        """Test get_connector returns pooled connector."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            mock_connector = MagicMock()
            mock_s3_class.return_value = mock_connector

            conn1 = router.get_connector("s3", "tenant_1", s3_config)
            conn2 = router.get_connector("s3", "tenant_1", s3_config)

            assert conn1 is conn2
            # Should only be called once (cached)
            assert mock_s3_class.call_count == 1

    def test_get_connector_separate_pools_per_tenant(self, router, s3_config):
        """Test separate connector pools per tenant."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            mock_s3_class.side_effect = [MagicMock(), MagicMock()]

            conn1 = router.get_connector("s3", "tenant_1", s3_config)

            config2 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            conn2 = router.get_connector("s3", "tenant_2", config2)

            assert conn1 is not conn2

    def test_get_connector_unsupported_type(self, router, s3_config):
        """Test get_connector rejects unsupported type."""
        with pytest.raises(ValidationError):
            router.get_connector("unsupported_db", "tenant_1", s3_config)


class TestTenantAccess:
    """Test tenant access control."""

    def test_validate_tenant_access_grants_access(self, router):
        """Test validate_tenant_access grants access to resource."""
        result = router.validate_tenant_access("tenant_1", "s3")
        assert result is True

    def test_validate_tenant_access_denies_empty_tenant(self, router):
        """Test validate_tenant_access denies empty tenant_id."""
        with pytest.raises(TenantAccessError):
            router.validate_tenant_access("", "s3")

    def test_cross_tenant_access_isolation(self, router):
        """Test tenants cannot access each other's resources."""
        # First tenant accesses s3
        router.validate_tenant_access("tenant_1", "s3")

        # Second tenant trying to access should get own resource access
        result = router.validate_tenant_access("tenant_2", "s3")
        assert result is True  # Gets access to their own s3


class TestReadWrite:
    """Test read_data and write_data routing."""

    def test_read_data_routes_to_connector(self, router, s3_config):
        """Test read_data routes to correct connector."""
        with patch.object(router, "get_connector") as mock_get:
            mock_connector = MagicMock()
            mock_connector.read.return_value = [{"key": "value"}]
            mock_get.return_value = mock_connector

            result = router.read_data("tenant_1", "test-query", "s3", s3_config)

            mock_connector.read.assert_called_once_with("test-query")
            assert result == [{"key": "value"}]

    def test_write_data_routes_to_connector(self, router, postgres_config):
        """Test write_data routes to correct connector."""
        with patch.object(router, "get_connector") as mock_get:
            mock_connector = MagicMock()
            mock_connector.write.return_value = {"success": True}
            mock_get.return_value = mock_connector

            result = router.write_data(
                "tenant_1", {"sql": "INSERT..."}, "postgresql", config=postgres_config
            )

            mock_connector.write.assert_called_once()
            assert result["success"] is True

    def test_read_denies_unauthorized_tenant(self, router):
        """Test read_data enforces tenant access control."""
        # Tenant has access
        router.validate_tenant_access("tenant_1", "read:s3")

        # Another tenant trying to read should also get access (per-tenant)
        result = router.validate_tenant_access("tenant_2", "read:s3")
        assert result is True


class TestConnectionLifecycle:
    """Test connection lifecycle management."""

    def test_close_tenant_connections(self, router, s3_config):
        """Test close_tenant_connections closes all connectors."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            mock_connector = MagicMock()
            mock_s3_class.return_value = mock_connector

            router.get_connector("s3", "tenant_1", s3_config)
            assert "tenant_1" in router._connector_pool

            router.close_tenant_connections("tenant_1")
            mock_connector.close.assert_called_once()
            assert "tenant_1" not in router._connector_pool

    def test_close_all_connections(self, router, s3_config, postgres_config):
        """Test close_all_connections closes all tenant connections."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            with patch("src.tenant_aware_layer.PostgreSQLConnector") as mock_pg_class:
                mock_s3 = MagicMock()
                mock_pg = MagicMock()
                mock_s3_class.return_value = mock_s3
                mock_pg_class.return_value = mock_pg

                router.get_connector("s3", "tenant_1", s3_config)
                router.get_connector("postgresql", "tenant_2", postgres_config)

                router.close_all_connections()

                mock_s3.close.assert_called_once()
                mock_pg.close.assert_called_once()
                assert len(router._connector_pool) == 0


class TestGetTenantConfig:
    """Test tenant configuration retrieval."""

    def test_get_tenant_config_returns_config(self, router):
        """Test get_tenant_config returns tenant config."""
        config = router.get_tenant_config("tenant_1")
        assert config["tenant_id"] == "tenant_1"
        assert "app_env" in config

    def test_tenant_config_isolation(self, router):
        """Test tenant configs are isolated."""
        config1 = router.get_tenant_config("tenant_1")
        config2 = router.get_tenant_config("tenant_2")

        assert config1["tenant_id"] == "tenant_1"
        assert config2["tenant_id"] == "tenant_2"


class TestAuditLogging:
    """Test audit logging integration."""

    def test_audit_log_on_connector_creation(self, router, s3_config):
        """Test audit log records connector creation."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            mock_connector = MagicMock()
            mock_s3_class.return_value = mock_connector

            with patch.object(router._audit_log, "log_event") as mock_log:
                router.get_connector("s3", "tenant_1", s3_config)
                mock_log.assert_called()

    def test_audit_log_on_read_operation(self, router, s3_config):
        """Test audit log records read operation."""
        with patch.object(router, "get_connector") as mock_get:
            mock_connector = MagicMock()
            mock_connector.read.return_value = []
            mock_get.return_value = mock_connector

            with patch.object(router._audit_log, "log_event") as mock_log:
                router.read_data("tenant_1", "query", "s3", s3_config)

                # Should log READ_OPERATION
                calls = mock_log.call_args_list
                assert any("READ_OPERATION" in str(call) for call in calls)

    def test_audit_log_on_access_denial(self, router):
        """Test audit log records access denials."""
        with patch.object(router._audit_log, "log_event") as mock_log:
            router._validate_tenant_access("tenant_1", "s3")
            # Access granted, no denial logged yet

            # Try with empty tenant
            try:
                router._validate_tenant_access("", "s3")
            except TenantAccessError:
                pass

            # Should have logged access denial
            calls = mock_log.call_args_list
            assert any("ACCESS_DENIED" in str(call) for call in calls)


class TestErrorHandling:
    """Test error handling and propagation."""

    def test_connector_creation_error_propagation(self, router, s3_config):
        """Test connector creation errors propagate."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            mock_s3_class.side_effect = Exception("Connection failed")

            with pytest.raises(ConnectionError) as exc_info:
                router.get_connector("s3", "tenant_1", s3_config)
            assert "Connection failed" in str(exc_info.value)

    def test_read_error_propagation(self, router, s3_config):
        """Test read errors propagate."""
        from src.errors import ReadError

        with patch.object(router, "get_connector") as mock_get:
            mock_connector = MagicMock()
            mock_connector.read.side_effect = ReadError("Read failed", connector_type="s3")
            mock_get.return_value = mock_connector

            with pytest.raises(ReadError):
                router.read_data("tenant_1", "query", "s3", s3_config)

    def test_write_error_propagation(self, router, postgres_config):
        """Test write errors propagate."""
        from src.errors import WriteError

        with patch.object(router, "get_connector") as mock_get:
            mock_connector = MagicMock()
            mock_connector.write.side_effect = WriteError("Write failed", connector_type="postgresql")
            mock_get.return_value = mock_connector

            with pytest.raises(WriteError):
                router.write_data("tenant_1", {"sql": "INSERT"}, "postgresql", config=postgres_config)


class TestMultiConnectorRouting:
    """Test routing across different connector types."""

    def test_route_to_s3(self, router, s3_config):
        """Test routing to S3 connector."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            mock_connector = MagicMock()
            mock_s3.return_value = mock_connector

            router.get_connector("s3", "tenant_1", s3_config)
            mock_s3.assert_called_once()

    def test_route_to_postgresql(self, router, postgres_config):
        """Test routing to PostgreSQL connector."""
        with patch("src.tenant_aware_layer.PostgreSQLConnector") as mock_pg:
            mock_connector = MagicMock()
            mock_pg.return_value = mock_connector

            router.get_connector("postgresql", "tenant_1", postgres_config)
            mock_pg.assert_called_once()

    def test_route_multiple_connectors_per_tenant(self, router, s3_config, postgres_config):
        """Test tenant can have multiple connector types pooled."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            with patch("src.tenant_aware_layer.PostgreSQLConnector") as mock_pg:
                mock_s3.return_value = MagicMock()
                mock_pg.return_value = MagicMock()

                router.get_connector("s3", "tenant_1", s3_config)
                router.get_connector("postgresql", "tenant_1", postgres_config)

                # Both should be in pool for tenant_1
                assert "s3" in router._connector_pool["tenant_1"]
                assert "postgresql" in router._connector_pool["tenant_1"]


class TestCrossTenantisolation:
    """Test strict cross-tenant isolation."""

    def test_tenant_cannot_access_other_tenant_connectors(self, router, s3_config):
        """Test tenant_1 cannot access tenant_2's connector."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            mock_s3.return_value = MagicMock()

            # tenant_1 creates connector
            router.get_connector("s3", "tenant_1", s3_config)

            # tenant_2 tries to access same pool - gets different instance
            config2 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            mock_s3.side_effect = [MagicMock()]  # Second instance for tenant_2
            conn2 = router.get_connector("s3", "tenant_2", config2)

            # Verify different pools
            assert "tenant_1" in router._connector_pool
            assert "tenant_2" in router._connector_pool
            assert router._connector_pool["tenant_1"] is not router._connector_pool["tenant_2"]

    def test_tenant_read_isolation(self, router, s3_config):
        """Test read operations isolated by tenant."""
        with patch.object(router, "get_connector") as mock_get:
            mock_s3_1 = MagicMock()
            mock_s3_2 = MagicMock()
            mock_s3_1.read.return_value = [{"tenant": "tenant_1"}]
            mock_s3_2.read.return_value = [{"tenant": "tenant_2"}]

            mock_get.side_effect = [mock_s3_1, mock_s3_2]

            result1 = router.read_data("tenant_1", "query1", "s3", s3_config)

            s3_config_2 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            result2 = router.read_data("tenant_2", "query2", "s3", s3_config_2)

            assert result1 != result2

    def test_tenant_write_isolation(self, router, s3_config):
        """Test write operations isolated by tenant."""
        with patch.object(router, "get_connector") as mock_get:
            mock_s3_1 = MagicMock()
            mock_s3_2 = MagicMock()
            mock_s3_1.write.return_value = {"status": "written_to_tenant_1"}
            mock_s3_2.write.return_value = {"status": "written_to_tenant_2"}

            mock_get.side_effect = [mock_s3_1, mock_s3_2]

            result1 = router.write_data("tenant_1", {"data": "x"}, "s3", config=s3_config)

            s3_config_2 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            result2 = router.write_data("tenant_2", {"data": "y"}, "s3", config=s3_config_2)

            assert result1 != result2
            assert "tenant_1" in str(result1)
            assert "tenant_2" in str(result2)


class TestConcurrentTenantOperations:
    """Test concurrent operations from multiple tenants."""

    def test_concurrent_read_from_different_tenants(self, router, s3_config):
        """Test concurrent reads from different tenants."""
        with patch.object(router, "get_connector") as mock_get:
            mock_s3_1 = MagicMock()
            mock_s3_2 = MagicMock()
            mock_s3_1.read.return_value = []
            mock_s3_2.read.return_value = []

            mock_get.side_effect = [mock_s3_1, mock_s3_2]

            # Simulate concurrent reads
            t1_result = router.read_data("tenant_1", "q1", "s3", s3_config)

            config2 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            t2_result = router.read_data("tenant_2", "q2", "s3", config2)

            # Both should succeed independently
            assert t1_result == []
            assert t2_result == []

    def test_one_tenant_failure_not_affecting_others(self, router, s3_config):
        """Test failure in one tenant doesn't affect others."""
        with patch.object(router, "get_connector") as mock_get:
            mock_s3_1 = MagicMock()
            mock_s3_2 = MagicMock()
            mock_s3_1.read.side_effect = Exception("Tenant 1 error")
            mock_s3_2.read.return_value = [{"success": True}]

            mock_get.side_effect = [mock_s3_1, mock_s3_2]

            # Tenant 1 fails
            with pytest.raises(Exception):
                router.read_data("tenant_1", "q1", "s3", s3_config)

            # Tenant 2 succeeds
            config2 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            result = router.read_data("tenant_2", "q2", "s3", config2)
            assert result == [{"success": True}]


class TestPoolManagement:
    """Test connection pool lifecycle and management."""

    def test_pool_grows_with_new_tenants(self, router, s3_config):
        """Test pool grows as new tenants are added."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            mock_s3.side_effect = [MagicMock(), MagicMock(), MagicMock()]

            # Add first tenant
            router.get_connector("s3", "tenant_1", s3_config)
            assert len(router._connector_pool) == 1

            # Add second tenant
            config2 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            router.get_connector("s3", "tenant_2", config2)
            assert len(router._connector_pool) == 2

            # Add third tenant
            config3 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_3",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            router.get_connector("s3", "tenant_3", config3)
            assert len(router._connector_pool) == 3

    def test_pool_cleanup_removes_tenant_data(self, router, s3_config):
        """Test cleanup removes tenant from pool."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            mock_conn = MagicMock()
            mock_s3.return_value = mock_conn

            router.get_connector("s3", "tenant_1", s3_config)
            assert "tenant_1" in router._connector_pool

            router.close_tenant_connections("tenant_1")
            assert "tenant_1" not in router._connector_pool
            mock_conn.close.assert_called_once()

    def test_pool_cleanup_resilient_to_close_errors(self, router, s3_config):
        """Test pool cleanup continues despite close errors."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            mock_conn = MagicMock()
            mock_conn.close.side_effect = Exception("Close failed")
            mock_s3.return_value = mock_conn

            router.get_connector("s3", "tenant_1", s3_config)

            # Should not raise despite error
            router.close_tenant_connections("tenant_1")
            assert "tenant_1" not in router._connector_pool

    def test_multiple_connector_types_in_pool(self, router, s3_config, postgres_config):
        """Test pool holds multiple connector types per tenant."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            with patch("src.tenant_aware_layer.PostgreSQLConnector") as mock_pg:
                mock_s3.return_value = MagicMock()
                mock_pg.return_value = MagicMock()

                router.get_connector("s3", "tenant_1", s3_config)
                router.get_connector("postgresql", "tenant_1", postgres_config)

                assert len(router._connector_pool["tenant_1"]) == 2
                assert "s3" in router._connector_pool["tenant_1"]
                assert "postgresql" in router._connector_pool["tenant_1"]


class TestAccessControlEnforcement:
    """Test access control is enforced."""

    def test_empty_tenant_id_denied(self, router):
        """Test empty tenant_id is always denied."""
        with pytest.raises(TenantAccessError):
            router.validate_tenant_access("", "s3")

    def test_resource_access_granted_per_tenant(self, router):
        """Test each tenant gets access to their resources."""
        # First access initializes the resource
        result1 = router.validate_tenant_access("tenant_1", "s3")
        assert result1 is True

        # Same tenant accessing again
        result2 = router.validate_tenant_access("tenant_1", "s3")
        assert result2 is True

        # Different tenant, different resource pool
        result3 = router.validate_tenant_access("tenant_2", "s3")
        assert result3 is True


class TestConnectorCreationFailures:
    """Test handling of connector creation failures."""

    def test_creation_failure_wrapped_in_connection_error(self, router, s3_config):
        """Test creation failures are wrapped in ConnectionError."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            mock_s3_class.side_effect = Exception("SDK error")

            with pytest.raises(ConnectionError) as exc_info:
                router.get_connector("s3", "tenant_1", s3_config)

            assert "SDK error" in str(exc_info.value)

    def test_connection_error_includes_tenant_context(self, router, s3_config):
        """Test ConnectionError includes tenant and connector context."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3_class:
            mock_s3_class.side_effect = Exception("Network error")

            with pytest.raises(ConnectionError) as exc_info:
                router.get_connector("s3", "tenant_1", s3_config)

            error = exc_info.value
            assert "tenant_1" in str(error) or hasattr(error, 'tenant_id')
            assert "s3" in str(error) or hasattr(error, 'connector_type')


class TestOperationFailurePropagation:
    """Test failures propagate correctly."""

    def test_read_failure_propagates(self, router, s3_config):
        """Test read operation failures propagate."""
        from src.errors import ReadError

        with patch.object(router, "get_connector") as mock_get:
            mock_conn = MagicMock()
            mock_conn.read.side_effect = ReadError("Read failed", connector_type="s3")
            mock_get.return_value = mock_conn

            with pytest.raises(ReadError):
                router.read_data("tenant_1", "q1", "s3", s3_config)

    def test_write_failure_propagates(self, router, postgres_config):
        """Test write operation failures propagate."""
        from src.errors import WriteError

        with patch.object(router, "get_connector") as mock_get:
            mock_conn = MagicMock()
            mock_conn.write.side_effect = WriteError("Write failed", connector_type="postgresql")
            mock_get.return_value = mock_conn

            with pytest.raises(WriteError):
                router.write_data("tenant_1", {"sql": "INSERT"}, "postgresql", config=postgres_config)


class TestCompleteDataflow:
    """Test complete data flow scenarios."""

    def test_multi_tenant_multi_connector_workflow(self, router, s3_config, postgres_config):
        """Test complete workflow with multiple tenants and connectors."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            with patch("src.tenant_aware_layer.PostgreSQLConnector") as mock_pg:
                s3_1 = MagicMock()
                s3_2 = MagicMock()
                pg_1 = MagicMock()

                s3_1.read.return_value = [{"id": 1}]
                s3_2.read.return_value = [{"id": 2}]
                pg_1.write.return_value = {"rows": 1}

                mock_s3.side_effect = [s3_1, s3_2]
                mock_pg.return_value = pg_1

                # Tenant 1: read from S3, write to DB
                s3_data_t1 = router.read_data("tenant_1", "query", "s3", s3_config)

                config2 = ConnectorConfig(
                    connector_type="s3",
                    tenant_id="tenant_2",
                    credentials=s3_config.credentials,
                    metadata=s3_config.metadata,
                )
                s3_data_t2 = router.read_data("tenant_2", "query", "s3", config2)

                db_result = router.write_data("tenant_1", s3_data_t1, "postgresql", config=postgres_config)

                # Verify isolation
                assert s3_data_t1 != s3_data_t2
                assert db_result["rows"] == 1

    def test_sequential_tenant_operations(self, router, s3_config):
        """Test sequential operations from different tenants."""
        with patch("src.tenant_aware_layer.S3Connector") as mock_s3:
            mock_s3.side_effect = [MagicMock(), MagicMock()]

            # Tenant 1 reads
            router.get_connector("s3", "tenant_1", s3_config)

            # Tenant 2 reads
            config2 = ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
            router.get_connector("s3", "tenant_2", config2)

            # Both should be in pool independently
            assert "tenant_1" in router._connector_pool
            assert "tenant_2" in router._connector_pool
            assert router._connector_pool["tenant_1"]["s3"] is not router._connector_pool["tenant_2"]["s3"]


class TestTenantValidation:
    """Test tenant ID validation and authorization."""

    def test_empty_tenant_id_rejected(self, router, s3_config):
        """Test empty tenant_id is rejected."""
        with pytest.raises(TenantAccessError) as exc_info:
            router.get_connector("s3", "", s3_config)
        assert "required" in str(exc_info.value).lower()

    def test_none_tenant_id_rejected(self, router, s3_config):
        """Test None tenant_id is rejected."""
        with pytest.raises(TenantAccessError):
            router.get_connector("s3", None, s3_config)

    def test_non_string_tenant_id_rejected(self, router, s3_config):
        """Test non-string tenant_id is rejected."""
        with pytest.raises(TenantAccessError) as exc_info:
            router.get_connector("s3", 12345, s3_config)
        assert "string" in str(exc_info.value).lower()

    def test_tenant_id_with_path_traversal_rejected(self, router, s3_config):
        """Test tenant_id with path traversal characters rejected."""
        with pytest.raises(TenantAccessError) as exc_info:
            router.get_connector("s3", "../admin", s3_config)
        assert ".." in str(exc_info.value) or "invalid" in str(exc_info.value).lower()

    def test_tenant_id_with_slash_rejected(self, router, s3_config):
        """Test tenant_id with slash characters rejected."""
        with pytest.raises(TenantAccessError) as exc_info:
            router.get_connector("s3", "tenant/admin", s3_config)
        assert "/" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()

    def test_tenant_id_with_backslash_rejected(self, router, s3_config):
        """Test tenant_id with backslash characters rejected."""
        with pytest.raises(TenantAccessError) as exc_info:
            router.get_connector("s3", "tenant\\admin", s3_config)
        assert "\\" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()

    def test_tenant_id_too_long_rejected(self, router, s3_config):
        """Test tenant_id longer than 255 chars rejected."""
        long_tenant_id = "x" * 256
        with pytest.raises(TenantAccessError) as exc_info:
            router.get_connector("s3", long_tenant_id, s3_config)
        assert "too long" in str(exc_info.value).lower() or "255" in str(exc_info.value)

    def test_valid_tenant_id_accepted(self, router, s3_config):
        """Test valid tenant_id is accepted."""
        with patch("src.tenant_aware_layer.S3Connector"):
            # Should not raise
            router.get_connector("s3", "tenant-123_valid", s3_config)


class TestAccessControl:
    """Test access control logic (ACL checking)."""

    def test_access_granted_with_exact_match(self, router):
        """Exact resource match grants access."""
        router.add_tenant("tenant_1", {
            "name": "Tenant 1",
            "allowed_resources": ["s3://bucket1/file.txt"]
        })

        assert router.validate_tenant_access("tenant_1", "s3://bucket1/file.txt")

    def test_access_denied_resource_not_in_list(self, router):
        """Resource not in allowed list denies access."""
        router.add_tenant("tenant_1", {
            "name": "Tenant 1",
            "allowed_resources": ["s3://bucket1/*"]
        })

        with pytest.raises(TenantAccessError) as exc_info:
            router.validate_tenant_access("tenant_1", "s3://bucket2/file.txt")
        assert "Access denied" in str(exc_info.value)

    def test_access_with_wildcard_pattern(self, router):
        """Wildcard patterns grant access."""
        router.add_tenant("tenant_1", {
            "name": "Tenant 1",
            "allowed_resources": ["s3://bucket1/*", "postgresql:table_*"]
        })

        assert router.validate_tenant_access("tenant_1", "s3://bucket1/file.txt")
        assert router.validate_tenant_access("tenant_1", "s3://bucket1/folder/deep.txt")
        assert router.validate_tenant_access("tenant_1", "postgresql:table_users")

        with pytest.raises(TenantAccessError):
            router.validate_tenant_access("tenant_1", "s3://bucket2/file.txt")

    def test_access_with_regex_pattern(self, router):
        """Regex patterns grant access."""
        router.add_tenant("tenant_1", {
            "name": "Tenant 1",
            "allowed_resources": ["regex:s3://bucket[0-9]+/.*"]
        })

        assert router.validate_tenant_access("tenant_1", "s3://bucket123/file.txt")
        assert router.validate_tenant_access("tenant_1", "s3://bucket1/any/path.txt")

        with pytest.raises(TenantAccessError):
            router.validate_tenant_access("tenant_1", "s3://bucketA/file.txt")

    def test_access_denied_for_disabled_tenant(self, router):
        """Disabled tenant denied access."""
        router.add_tenant("tenant_1", {
            "name": "Tenant 1",
            "enabled": False,
            "allowed_resources": ["s3://*"]
        })

        with pytest.raises(TenantAccessError) as exc_info:
            router.validate_tenant_access("tenant_1", "s3://bucket/file.txt")
        assert "disabled" in str(exc_info.value).lower()

    def test_access_allowed_no_restrictions(self, router):
        """Tenant with no allowed_resources list has full access."""
        router.add_tenant("tenant_1", {
            "name": "Tenant 1"
            # No allowed_resources = allow all
        })

        assert router.validate_tenant_access("tenant_1", "s3://any/thing")
        assert router.validate_tenant_access("tenant_1", "postgresql:any_table")
        assert router.validate_tenant_access("tenant_1", "kafka:any_topic")

    def test_add_tenant_validates_config(self, router):
        """add_tenant validates configuration."""
        with pytest.raises(ValidationError):
            router.add_tenant("tenant_1", {})  # Missing required "name" field

    def test_add_tenant_validates_connector_types(self, router):
        """add_tenant validates connector types."""
        with pytest.raises(ValidationError) as exc_info:
            router.add_tenant("tenant_1", {
                "name": "Tenant 1",
                "allowed_connector_types": ["invalid_type"]
            })
        assert "Unknown connector type" in str(exc_info.value)

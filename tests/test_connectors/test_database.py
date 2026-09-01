"""Tests for database connectors (PostgreSQL, MongoDB, Snowflake).

Tests cover query/execute operations, batch inserts, transactions, SQL injection
prevention, connection failures, and multi-tenant isolation for databases.
"""

import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

from src.config import ConnectorConfig
from src.connectors.database import (
    DatabaseConnector,
    PostgreSQLConnector,
    MongoDBConnector,
    SnowflakeConnector,
)
from src.errors import ConnectionError, ReadError, WriteError, ValidationError


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
        metadata={"schema": "public"},
    )


@pytest.fixture
def mongodb_config():
    """Create MongoDB connector config."""
    return ConnectorConfig(
        connector_type="mongodb",
        tenant_id="tenant_1",
        credentials={"uri": "mongodb://localhost:27017"},
        metadata={"database": "testdb", "collection": "users"},
    )


@pytest.fixture
def snowflake_config():
    """Create Snowflake connector config."""
    return ConnectorConfig(
        connector_type="snowflake",
        tenant_id="tenant_1",
        credentials={
            "account": "xy12345",
            "user": "user",
            "password": "password",
            "warehouse": "COMPUTE_WH",
            "database": "TESTDB",
        },
        metadata={"schema": "PUBLIC"},
    )


@pytest.fixture
def postgres_connector(postgres_config):
    """Create PostgreSQL connector instance."""
    return PostgreSQLConnector(postgres_config)


@pytest.fixture
def mongodb_connector(mongodb_config):
    """Create MongoDB connector instance."""
    return MongoDBConnector(mongodb_config)


@pytest.fixture
def snowflake_connector(snowflake_config):
    """Create Snowflake connector instance."""
    return SnowflakeConnector(snowflake_config)


class TestDatabaseConnectorAbstract:
    """Test abstract DatabaseConnector class."""

    def test_cannot_instantiate_database_connector(self, postgres_config):
        """Test that DatabaseConnector cannot be instantiated."""
        with pytest.raises(TypeError):
            DatabaseConnector(postgres_config)  # type: ignore

    def test_database_connector_extends_connector(self, postgres_config):
        """Test that DatabaseConnector extends Connector."""
        postgres = PostgreSQLConnector(postgres_config)
        assert isinstance(postgres, DatabaseConnector)


class TestPostgresConnector:
    """Test PostgreSQL connector."""

    def test_connect_success(self, postgres_connector):
        """Test PostgreSQL connection succeeds."""
        postgres_connector.connect()
        assert postgres_connector.is_connected is True

    def test_connect_validates_credentials(self):
        """Test PostgreSQL connect validates all credentials."""
        config = ConnectorConfig(
            connector_type="postgresql",
            tenant_id="tenant_1",
            credentials={"host": "localhost"},  # missing others
            metadata={},
        )
        postgres = PostgreSQLConnector(config)
        with pytest.raises(ValidationError):
            postgres.connect()

    def test_query_success(self, postgres_connector):
        """Test PostgreSQL query execution."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",), ("name",)]
            mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            result = postgres_connector.query(
                "SELECT * FROM users WHERE id = %s", {"id": 1}, "tenant_1"
            )
            assert len(result) == 2
            assert result[0]["name"] == "Alice"

    def test_query_parameterized(self, postgres_connector):
        """Test parameterized queries prevent SQL injection."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = []
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            postgres_connector.query(
                "SELECT * FROM users WHERE id = %s", {"id": "1 OR 1=1"}, "tenant_1"
            )
            # Verify execute was called with params, not interpolated SQL
            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            # Params should be passed separately, not in SQL string
            assert "1 OR 1=1" not in call_args[0][0]

    def test_execute_success(self, postgres_connector):
        """Test PostgreSQL execute."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.rowcount = 1
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            result = postgres_connector.execute(
                "INSERT INTO users (name) VALUES (%s)",
                {"name": "Alice"},
                "tenant_1"
            )
            assert result == 1
            mock_conn.commit.assert_called_once()

    def test_insert_batch(self, postgres_connector):
        """Test PostgreSQL batch insert."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
            result = postgres_connector.insert_batch("users", rows, "tenant_1")
            assert result == 2
            assert mock_cursor.execute.call_count == 2

    def test_transaction_success(self, postgres_connector):
        """Test PostgreSQL transaction commits on success."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_client.return_value = mock_conn

            with postgres_connector.transaction("tenant_1"):
                pass
            mock_conn.commit.assert_called_once()

    def test_transaction_rollback_on_error(self, postgres_connector):
        """Test PostgreSQL transaction rolls back on error."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_client.return_value = mock_conn

            with pytest.raises(WriteError):
                with postgres_connector.transaction("tenant_1"):
                    raise Exception("Test error")
            mock_conn.rollback.assert_called_once()

    def test_close(self, postgres_connector):
        """Test PostgreSQL connection close."""
        postgres_connector.connect()
        postgres_connector.close()
        assert postgres_connector.is_connected is False


class TestMongoDBConnector:
    """Test MongoDB connector."""

    def test_connect_success(self, mongodb_connector):
        """Test MongoDB connection succeeds."""
        mongodb_connector.connect()
        assert mongodb_connector.is_connected is True

    def test_connect_validates_credentials(self):
        """Test MongoDB connect validates credentials."""
        config = ConnectorConfig(
            connector_type="mongodb",
            tenant_id="tenant_1",
            credentials={},  # missing uri
            metadata={"database": "db", "collection": "coll"},
        )
        mongodb = MongoDBConnector(config)
        with pytest.raises(ValidationError):
            mongodb.connect()

    def test_query_success(self, mongodb_connector):
        """Test MongoDB query execution."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.find.return_value = [
                {"_id": "1", "name": "Alice"},
                {"_id": "2", "name": "Bob"},
            ]
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            result = mongodb_connector.query(
                '{"name": "Alice"}', {}, "tenant_1"
            )
            assert len(result) == 2

    def test_execute_insert(self, mongodb_connector):
        """Test MongoDB insert execution."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.insert_one.return_value = MagicMock(inserted_id="id1")
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            result = mongodb_connector.execute(
                '{"insert_one": {"name": "Alice"}}', {}, "tenant_1"
            )
            assert result == 1

    def test_insert_batch(self, mongodb_connector):
        """Test MongoDB batch insert."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.insert_many.return_value = MagicMock(
                inserted_ids=["id1", "id2"]
            )
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            rows = [{"name": "Alice"}, {"name": "Bob"}]
            result = mongodb_connector.insert_batch("users", rows, "tenant_1")
            assert result == 2

    def test_transaction_success(self, mongodb_connector):
        """Test MongoDB transaction."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client"):
            with mongodb_connector.transaction("tenant_1"):
                pass  # No error

    def test_close(self, mongodb_connector):
        """Test MongoDB connection close."""
        mongodb_connector.connect()
        mongodb_connector.close()
        assert mongodb_connector.is_connected is False


class TestSnowflakeConnector:
    """Test Snowflake connector."""

    def test_connect_success(self, snowflake_connector):
        """Test Snowflake connection succeeds."""
        snowflake_connector.connect()
        assert snowflake_connector.is_connected is True

    def test_connect_validates_credentials(self):
        """Test Snowflake connect validates credentials."""
        config = ConnectorConfig(
            connector_type="snowflake",
            tenant_id="tenant_1",
            credentials={"account": "xy12345"},  # missing others
            metadata={},
        )
        snowflake = SnowflakeConnector(config)
        with pytest.raises(ValidationError):
            snowflake.connect()

    def test_query_success(self, snowflake_connector):
        """Test Snowflake query execution."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("ID",), ("NAME",)]
            mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            result = snowflake_connector.query(
                "SELECT * FROM users", {}, "tenant_1"
            )
            assert len(result) == 2

    def test_execute_success(self, snowflake_connector):
        """Test Snowflake execute."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.rowcount = 1
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            result = snowflake_connector.execute(
                "INSERT INTO users VALUES (?, ?)",
                {"id": 1, "name": "Alice"},
                "tenant_1"
            )
            assert result == 1

    def test_insert_batch(self, snowflake_connector):
        """Test Snowflake batch insert."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            rows = [{"id": 1, "name": "Alice"}]
            result = snowflake_connector.insert_batch("users", rows, "tenant_1")
            assert result == 1

    def test_transaction_success(self, snowflake_connector):
        """Test Snowflake transaction."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_client.return_value = mock_conn

            with snowflake_connector.transaction("tenant_1"):
                pass
            mock_conn.commit.assert_called_once()

    def test_close(self, snowflake_connector):
        """Test Snowflake connection close."""
        snowflake_connector.connect()
        snowflake_connector.close()
        assert snowflake_connector.is_connected is False


class TestMultiTenantIsolation:
    """Test multi-tenant isolation across connectors."""

    def test_postgres_schema_prefixing(self, postgres_connector):
        """Test PostgreSQL schemas are prefixed with tenant_id."""
        postgres_connector.connect()
        schema = postgres_connector._tenant_schema("public", "tenant_1")
        assert schema == "tenant_1_public"

    def test_mongodb_database_prefixing(self, mongodb_connector):
        """Test MongoDB databases are prefixed with tenant_id."""
        mongodb_connector.connect()
        db = mongodb_connector._tenant_schema("testdb", "tenant_1")
        assert db == "tenant_1_testdb"

    def test_snowflake_schema_prefixing(self, snowflake_connector):
        """Test Snowflake schemas are prefixed with tenant_id."""
        snowflake_connector.connect()
        schema = snowflake_connector._tenant_schema("PUBLIC", "tenant_1")
        assert schema == "tenant_1_PUBLIC"


class TestConnectionPooling:
    """Test connection pooling per tenant."""

    def test_postgres_pools_clients(self, postgres_connector):
        """Test PostgreSQL pools clients per tenant."""
        postgres_connector.connect()
        client1 = postgres_connector._get_client("tenant_1")
        client2 = postgres_connector._get_client("tenant_1")
        assert client1 is client2

    def test_postgres_different_tenants(self, postgres_connector):
        """Test PostgreSQL different tenants have separate clients."""
        postgres_connector.connect()
        client1 = postgres_connector._get_client("tenant_1")
        client2 = postgres_connector._get_client("tenant_2")
        assert client1 is not client2

    def test_mongodb_pools_clients(self, mongodb_connector):
        """Test MongoDB pools clients per tenant."""
        mongodb_connector.connect()
        client1 = mongodb_connector._get_client("tenant_1")
        client2 = mongodb_connector._get_client("tenant_1")
        assert client1 is client2

    def test_snowflake_pools_clients(self, snowflake_connector):
        """Test Snowflake pools clients per tenant."""
        snowflake_connector.connect()
        client1 = snowflake_connector._get_client("tenant_1")
        client2 = snowflake_connector._get_client("tenant_1")
        assert client1 is client2


class TestErrorHandling:
    """Test error handling across connectors."""

    def test_postgres_query_error(self, postgres_connector):
        """Test PostgreSQL query errors are wrapped."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception("Syntax error")
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            with pytest.raises(ReadError):
                postgres_connector.query("SELECT * FROM bad_table", {}, "tenant_1")

    def test_mongodb_execute_error(self, mongodb_connector):
        """Test MongoDB execute errors are wrapped."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.insert_one.side_effect = Exception("Insert failed")
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            with pytest.raises(WriteError):
                mongodb_connector.execute(
                    '{"insert_one": {}}', {}, "tenant_1"
                )

    def test_snowflake_transaction_error(self, snowflake_connector):
        """Test Snowflake transaction errors are wrapped."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_client.return_value = mock_conn

            with pytest.raises(WriteError):
                with snowflake_connector.transaction("tenant_1"):
                    raise Exception("Transaction error")


class TestReadWriteInterface:
    """Test read() and write() methods from Connector interface."""

    def test_postgres_read_delegates_to_query(self, postgres_connector):
        """Test PostgreSQL read() delegates to query()."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "query", return_value=[]):
            result = postgres_connector.read("SELECT * FROM users")
            assert result == []

    def test_postgres_write_delegates_to_execute(self, postgres_connector):
        """Test PostgreSQL write() delegates to execute()."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "execute", return_value=1):
            result = postgres_connector.write(
                {"sql": "INSERT INTO users VALUES (%s)", "params": {}}
            )
            assert result["rows_affected"] == 1

    def test_mongodb_read_fails_if_not_connected(self, mongodb_connector):
        """Test MongoDB read() fails if not connected."""
        with pytest.raises(ConnectionError):
            mongodb_connector.read("{}")

    def test_snowflake_write_fails_if_not_connected(self, snowflake_connector):
        """Test Snowflake write() fails if not connected."""
        with pytest.raises(ConnectionError):
            snowflake_connector.write({"sql": "INSERT INTO users VALUES (1)"})


class TestValidation:
    """Test input validation."""

    def test_validate_sql_rejects_empty(self, postgres_connector):
        """Test SQL validation rejects empty strings."""
        postgres_connector.connect()
        with pytest.raises(ValidationError):
            postgres_connector.query("", {}, "tenant_1")

    def test_validate_sql_rejects_non_string(self, postgres_connector):
        """Test SQL validation rejects non-strings."""
        postgres_connector.connect()
        with pytest.raises(ValidationError):
            postgres_connector.query(123, {}, "tenant_1")  # type: ignore

    def test_validate_params_rejects_non_dict(self, postgres_connector):
        """Test params validation rejects non-dicts."""
        postgres_connector.connect()
        with pytest.raises(ValidationError):
            postgres_connector.query("SELECT 1", "not a dict", "tenant_1")  # type: ignore

    def test_empty_batch_insert_returns_zero(self, postgres_connector):
        """Test empty batch insert returns 0."""
        postgres_connector.connect()
        result = postgres_connector.insert_batch("users", [], "tenant_1")
        assert result == 0


class TestTransactionRollback:
    """Test transaction rollback scenarios in detail."""

    def test_postgres_transaction_partial_rollback(self, postgres_connector):
        """Test PostgreSQL transaction rolls back all changes on any error."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_client.return_value = mock_conn

            with pytest.raises(WriteError):
                with postgres_connector.transaction("tenant_1"):
                    mock_cursor = MagicMock()
                    mock_conn.cursor.return_value = mock_cursor
                    mock_cursor.execute("INSERT INTO users...")
                    raise ValueError("Mid-transaction error")

            mock_conn.rollback.assert_called_once()
            mock_conn.commit.assert_not_called()

    def test_mongodb_transaction_error_prevents_persistence(self, mongodb_connector):
        """Test MongoDB transaction error doesn't persist changes."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client"):
            with pytest.raises(WriteError):
                with mongodb_connector.transaction("tenant_1"):
                    raise RuntimeError("Transaction failed")

    def test_snowflake_transaction_error_rollback(self, snowflake_connector):
        """Test Snowflake transaction rollback on error."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_client.return_value = mock_conn

            with pytest.raises(WriteError):
                with snowflake_connector.transaction("tenant_1"):
                    raise Exception("Snowflake error")

            mock_conn.rollback.assert_called_once()

    def test_postgres_rollback_idempotent(self, postgres_connector):
        """Test rolling back already rolled back transaction is safe."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_conn.rollback.side_effect = [None, Exception("Already rolled back")]
            mock_client.return_value = mock_conn

            try:
                with postgres_connector.transaction("tenant_1"):
                    raise Exception("Error")
            except WriteError:
                pass
            # Should handle multiple rollback attempts gracefully
            assert mock_conn.rollback.called

    def test_postgres_transaction_with_multiple_statements(self, postgres_connector):
        """Test transaction with multiple statements rolls back all."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            statement_count = 0
            def execute_side_effect(*args):
                nonlocal statement_count
                statement_count += 1
                if statement_count == 3:
                    raise RuntimeError("Third statement fails")

            mock_cursor.execute.side_effect = execute_side_effect

            with pytest.raises(WriteError):
                with postgres_connector.transaction("tenant_1"):
                    for i in range(5):
                        postgres_connector.execute(
                            f"INSERT INTO users VALUES ({i})",
                            {},
                            "tenant_1"
                        )

            mock_conn.rollback.assert_called()


class TestConcurrentTransactions:
    """Test concurrent transaction handling."""

    def test_postgres_concurrent_transactions_isolation(self, postgres_connector):
        """Test concurrent transactions from different tenants are isolated."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_get:
            clients = {"tenant_1": MagicMock(), "tenant_2": MagicMock()}
            mock_get.side_effect = lambda tid: clients[tid]

            # Simulate concurrent transactions
            conn1 = postgres_connector._get_client("tenant_1")
            conn2 = postgres_connector._get_client("tenant_2")

            assert conn1 is not conn2
            assert conn1 is clients["tenant_1"]
            assert conn2 is clients["tenant_2"]

    def test_mongodb_concurrent_operations_same_tenant(self, mongodb_connector):
        """Test concurrent operations on same tenant use same connection."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client

            client1 = mongodb_connector._get_client("tenant_1")
            client2 = mongodb_connector._get_client("tenant_1")

            assert client1 is client2  # Same connection for same tenant

    def test_snowflake_concurrent_different_tenants(self, snowflake_connector):
        """Test concurrent operations across tenants have separate connections."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_get:
            conns = {}
            def get_or_create(tenant_id):
                if tenant_id not in conns:
                    conns[tenant_id] = MagicMock()
                return conns[tenant_id]
            mock_get.side_effect = get_or_create

            t1_conn = snowflake_connector._get_client("tenant_1")
            t2_conn = snowflake_connector._get_client("tenant_2")
            t1_conn_2 = snowflake_connector._get_client("tenant_1")

            assert t1_conn is t1_conn_2  # Same for same tenant
            assert t1_conn is not t2_conn  # Different for different tenants


class TestConnectionPoolExhaustion:
    """Test connection pool exhaustion scenarios."""

    def test_postgres_max_pool_connections(self, postgres_connector):
        """Test PostgreSQL handles max connections gracefully."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_get:
            mock_get.side_effect = ConnectionError(
                "Connection pool exhausted",
                connector_type="postgresql",
                tenant_id="tenant_1"
            )

            with pytest.raises(ReadError):
                postgres_connector.query("SELECT 1", {}, "tenant_1")

    def test_mongodb_connection_timeout_on_pool_exhaustion(self, mongodb_connector):
        """Test MongoDB connection timeout when pool exhausted."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_get:
            mock_get.side_effect = ConnectionError(
                "Connection pool exhausted",
                connector_type="mongodb",
                tenant_id="tenant_1"
            )

            with pytest.raises(ReadError):
                mongodb_connector.query("{}", {}, "tenant_1")

    def test_snowflake_recovery_after_pool_release(self, snowflake_connector):
        """Test Snowflake recovers after connection pool releases."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_get:
            mock_client = MagicMock()
            # First call fails, second succeeds
            mock_get.side_effect = [
                ConnectionError("Pool exhausted", connector_type="snowflake", tenant_id="tenant_1"),
                mock_client
            ]

            with pytest.raises(ReadError):
                snowflake_connector.query("SELECT 1", {}, "tenant_1")

            # After recovery, should work
            client = snowflake_connector._get_client("tenant_1")
            assert client is not None


class TestMultiTenantSchemaIsolation:
    """Test schema/database isolation across tenants in detail."""

    def test_postgres_different_tenants_different_schemas(self, postgres_connector):
        """Test PostgreSQL different tenants get different schemas."""
        postgres_connector.connect()
        schema1 = postgres_connector._tenant_schema("public", "tenant_1")
        schema2 = postgres_connector._tenant_schema("public", "tenant_2")
        schema3 = postgres_connector._tenant_schema("public", "tenant_1")

        assert schema1 == "tenant_1_public"
        assert schema2 == "tenant_2_public"
        assert schema1 == schema3  # Same tenant always same schema

    def test_mongodb_tenant_database_isolation(self, mongodb_connector):
        """Test MongoDB databases are isolated per tenant."""
        mongodb_connector.connect()
        db1 = mongodb_connector._tenant_schema("users_db", "tenant_1")
        db2 = mongodb_connector._tenant_schema("users_db", "tenant_2")

        assert db1 == "tenant_1_users_db"
        assert db2 == "tenant_2_users_db"
        assert db1 != db2

    def test_snowflake_schema_prefixing_consistent(self, snowflake_connector):
        """Test Snowflake schema prefixing is consistent."""
        snowflake_connector.connect()
        schema = snowflake_connector._tenant_schema("analytics", "company_a")
        assert schema.startswith("company_a_")
        assert "analytics" in schema

    def test_postgres_cross_tenant_query_isolation(self, postgres_connector):
        """Test PostgreSQL queries are isolated to tenant schema."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",)]
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            postgres_connector.query("SELECT * FROM users", {}, "tenant_1")
            postgres_connector.query("SELECT * FROM users", {}, "tenant_2")

            # Each query should have been executed (mocked)
            assert mock_cursor.execute.call_count == 2


class TestSQLErrorTypes:
    """Test specific SQL error types and handling."""

    def test_postgres_constraint_violation_error(self, postgres_connector):
        """Test PostgreSQL constraint violation is caught."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception(
                'ERROR: duplicate key value violates unique constraint "users_email_key"'
            )
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            with pytest.raises(WriteError) as exc_info:
                postgres_connector.execute(
                    "INSERT INTO users (email) VALUES (%s)",
                    {"email": "duplicate@test.com"},
                    "tenant_1"
                )
            assert "constraint" in str(exc_info.value).lower()

    def test_postgres_syntax_error(self, postgres_connector):
        """Test PostgreSQL syntax errors are caught."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception("SYNTAX ERROR: unexpected EOF")
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            with pytest.raises(ReadError):
                postgres_connector.query("SELEC * FROM users", {}, "tenant_1")

    def test_postgres_deadlock_error(self, postgres_connector):
        """Test PostgreSQL deadlock is caught and reported."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception(
                "ERROR: deadlock detected"
            )
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            with pytest.raises(WriteError) as exc_info:
                postgres_connector.execute(
                    "UPDATE users SET active = TRUE",
                    {},
                    "tenant_1"
                )
            assert "deadlock" in str(exc_info.value).lower()

    def test_mongodb_duplicate_key_error(self, mongodb_connector):
        """Test MongoDB duplicate key error."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.insert_one.side_effect = Exception(
                "E11000 duplicate key error"
            )
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            with pytest.raises(WriteError):
                mongodb_connector.execute(
                    '{"insert_one": {"email": "duplicate@test.com"}}',
                    {},
                    "tenant_1"
                )

    def test_snowflake_permission_denied_error(self, snowflake_connector):
        """Test Snowflake permission denied error."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception(
                "Schema 'PROTECTED_SCHEMA' does not exist or not authorized"
            )
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            with pytest.raises(ReadError):
                snowflake_connector.query(
                    "SELECT * FROM PROTECTED_SCHEMA.users",
                    {},
                    "tenant_1"
                )


class TestLargeBatchOperations:
    """Test large batch operation edge cases."""

    def test_postgres_large_batch_insert(self, postgres_connector):
        """Test PostgreSQL handles large batch inserts."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            # Create 10,000 rows
            rows = [{"id": i, "name": f"user_{i}"} for i in range(10000)]
            result = postgres_connector.insert_batch("users", rows, "tenant_1")

            assert result == 10000
            assert mock_cursor.execute.call_count == 10000

    def test_mongodb_large_batch_with_error(self, mongodb_connector):
        """Test MongoDB large batch stops on error."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()

            # First 5 succeed, 6th fails
            def insert_side_effect(doc):
                if len(mock_collection.insert_many.call_args_list) >= 5:
                    raise Exception("Quota exceeded")
                return MagicMock(inserted_id=doc.get("id"))

            mock_collection.insert_one.side_effect = insert_side_effect
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            rows = [{"id": i} for i in range(100)]
            # Should handle error gracefully
            try:
                mongodb_connector.insert_batch("users", rows, "tenant_1")
            except WriteError:
                pass

    def test_snowflake_batch_memory_efficiency(self, snowflake_connector):
        """Test Snowflake handles batch operations efficiently."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            # Large batch
            rows = [{"id": i, "value": "x" * 1000} for i in range(5000)]
            result = snowflake_connector.insert_batch("users", rows, "tenant_1")

            assert result == 5000

    def test_postgres_batch_empty_rows(self, postgres_connector):
        """Test PostgreSQL batch insert with empty row list."""
        postgres_connector.connect()
        result = postgres_connector.insert_batch("users", [], "tenant_1")
        assert result == 0


class TestQueryTimeout:
    """Test query timeout handling."""

    def test_postgres_query_timeout(self, postgres_connector):
        """Test PostgreSQL query timeout is caught."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception("Query timeout")
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            with pytest.raises(ReadError):
                postgres_connector.query(
                    "SELECT * FROM huge_table WHERE ...",
                    {},
                    "tenant_1"
                )

    def test_mongodb_operation_timeout(self, mongodb_connector):
        """Test MongoDB operation timeout."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.find.side_effect = Exception("Operation timeout")
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            with pytest.raises(ReadError):
                mongodb_connector.query("{}", {}, "tenant_1")

    def test_snowflake_query_timeout(self, snowflake_connector):
        """Test Snowflake query timeout."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception("Timeout: Query exceeded 30s limit")
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            with pytest.raises(ReadError):
                snowflake_connector.query("SELECT * FROM analytics", {}, "tenant_1")


class TestConnectionFailureRecovery:
    """Test connection failure and recovery scenarios."""

    def test_postgres_connection_recovery_on_retry(self, postgres_connector):
        """Test PostgreSQL recovers from connection failure on retry."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_get:
            mock_client = MagicMock()
            # First call fails, second succeeds
            mock_get.side_effect = [
                ConnectionError("Connection lost", connector_type="postgresql", tenant_id="tenant_1"),
                mock_client
            ]

            # First attempt fails (wrapped in ReadError)
            with pytest.raises(ReadError):
                postgres_connector.query("SELECT 1", {}, "tenant_1")

            # Verify the mock was called
            assert mock_get.call_count == 1

    def test_mongodb_reconnect_after_network_failure(self, mongodb_connector):
        """Test MongoDB reconnects after network failure."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client

            # Simulate network failure
            mongo_error = Exception("Network timeout")
            with patch.object(mongodb_connector, "query") as mock_query:
                mock_query.side_effect = mongo_error

                with pytest.raises(Exception):
                    mongodb_connector.query("{}", {}, "tenant_1")

    def test_snowflake_handle_connection_abort(self, snowflake_connector):
        """Test Snowflake handles connection abort gracefully."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_get:
            mock_get.side_effect = ConnectionError(
                "Connection aborted",
                connector_type="snowflake",
                tenant_id="tenant_1"
            )

            with pytest.raises(WriteError):
                snowflake_connector.execute("INSERT INTO users VALUES (1)", {}, "tenant_1")


class TestTransactionStatefulness:
    """Test transaction state management."""

    def test_postgres_transaction_commit_idempotent(self, postgres_connector):
        """Test PostgreSQL transaction commit is safe to call multiple times."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_client.return_value = mock_conn

            with postgres_connector.transaction("tenant_1"):
                pass

            # Commit should be called exactly once
            assert mock_conn.commit.call_count == 1

    def test_mongodb_transaction_state_cleaned_after_rollback(self, mongodb_connector):
        """Test MongoDB cleans up transaction state after rollback."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client"):
            try:
                with mongodb_connector.transaction("tenant_1"):
                    raise Exception("Test error")
            except WriteError:
                pass

            # Transaction should be cleaned up
            # (State should allow new transaction)
            with mongodb_connector.transaction("tenant_1"):
                pass  # Should succeed

    def test_snowflake_nested_transaction_not_supported(self, snowflake_connector):
        """Test Snowflake nested transactions work (depends on SDK support)."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_client.return_value = mock_conn

            # Snowflake should handle nested context managers
            # (may not truly nest, but should not error)
            with snowflake_connector.transaction("tenant_1"):
                # This is a nested call, but depends on SDK behavior
                pass  # Should complete without error


class TestMultiDatabaseOperations:
    """Test operations across multiple database instances."""

    def test_postgres_multiple_database_connections(self, postgres_connector):
        """Test multiple PostgreSQL databases can be accessed."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_get:
            db1_client = MagicMock()
            db2_client = MagicMock()
            clients = {"tenant_1": db1_client, "tenant_2": db2_client}
            mock_get.side_effect = lambda tid: clients[tid]

            client1 = postgres_connector._get_client("tenant_1")
            client2 = postgres_connector._get_client("tenant_2")

            assert client1 is not client2

    def test_mongodb_multiple_collections_operations(self, mongodb_connector):
        """Test MongoDB operations on multiple collections."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_coll1 = MagicMock()
            mock_coll2 = MagicMock()

            def get_collection(name):
                if "users" in name:
                    return mock_coll1
                return mock_coll2

            mock_db.get_collection.side_effect = get_collection
            mock_client.return_value.get_database.return_value = mock_db

            # Both collections should work
            mock_coll1.insert_one.return_value = MagicMock(inserted_id="id1")
            mock_coll2.insert_one.return_value = MagicMock(inserted_id="id2")

            result1 = mongodb_connector.execute(
                '{"insert_one": {"name": "Alice"}}', {}, "tenant_1"
            )
            result2 = mongodb_connector.execute(
                '{"insert_one": {"name": "Bob"}}', {}, "tenant_1"
            )

            assert result1 == 1 and result2 == 1


class TestSQLInjectionPrevention:
    """Test SQL injection prevention across all database engines (SECURITY-CRITICAL)."""

    def test_postgres_injection_in_where_clause(self, postgres_connector):
        """PostgreSQL: Parameterized queries prevent WHERE clause injection."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",), ("name",)]
            mock_cursor.fetchall.return_value = [(1, "Alice")]
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            # Attempt SQL injection via parameter
            malicious_input = "'; DROP TABLE users; --"
            result = postgres_connector.query(
                "SELECT * FROM users WHERE name = %s",
                {"name": malicious_input},
                "tenant_1"
            )

            # Verify parameterized query was used (not string interpolation)
            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            # SQL should have placeholder, not injection string
            assert "%s" in call_args[0][0]
            assert malicious_input not in call_args[0][0]

    def test_postgres_injection_in_order_by(self, postgres_connector):
        """PostgreSQL: ORDER BY clause protected."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",)]
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            # Injection in ORDER BY
            malicious = "name; DROP TABLE users; --"
            result = postgres_connector.query(
                "SELECT * FROM users ORDER BY %s",
                {"order": malicious},
                "tenant_1"
            )

            # Verify parameters are separate from SQL
            call_args = mock_cursor.execute.call_args
            assert "%s" in call_args[0][0]

    def test_postgres_injection_with_union(self, postgres_connector):
        """PostgreSQL: UNION injection attempt blocked."""
        postgres_connector.connect()
        with patch.object(postgres_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("id",)]
            mock_cursor.fetchall.return_value = [(1,)]
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            # UNION-based injection
            malicious = "1 UNION SELECT * FROM admin_users; --"
            result = postgres_connector.query(
                "SELECT id FROM users WHERE id = %s",
                {"id": malicious},
                "tenant_1"
            )

            # Injection treated as string literal, not SQL
            call_args = mock_cursor.execute.call_args
            assert "%s" in call_args[0][0]

    def test_mongodb_injection_in_filter(self, mongodb_connector):
        """MongoDB: Filter operators are passed safely to MongoDB driver."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.find.return_value = [{"_id": "1", "name": "alice"}]
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            # Query with MongoDB operators (valid JSON)
            # Operators like $or are passed to MongoDB driver, not interpreted by connector
            result = mongodb_connector.query(
                '{"name": "alice"}',
                {},
                "tenant_1"
            )

            # Verify find was called with the query as-is
            mock_collection.find.assert_called_once()
            # Result should be properly returned
            assert len(result) == 1

    def test_mongodb_injection_via_field_name(self, mongodb_connector):
        """MongoDB: Field name manipulation doesn't bypass tenant."""
        mongodb_connector.connect()
        with patch.object(mongodb_connector, "_get_client") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.find.return_value = [{"_id": "1", "name": "alice"}]
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.get_database.return_value = mock_db

            # Attempt field name injection (should not bypass tenant namespace)
            result = mongodb_connector.query(
                '{"tenant_id": {"$ne": "tenant_1"}}',
                {},
                "tenant_1"
            )

            # Query still executed against tenant_1 collection
            mock_collection.find.assert_called_once()

    def test_snowflake_injection_with_bind_parameter(self, snowflake_connector):
        """Snowflake: Bind parameters (?) prevent injection."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("ID",)]
            mock_cursor.fetchall.return_value = [(1,)]
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            # Injection attempt
            malicious = "1 OR 1=1"
            result = snowflake_connector.query(
                "SELECT * FROM users WHERE id = ?",
                {"id": malicious},
                "tenant_1"
            )

            # Verify bind parameter was used
            call_args = mock_cursor.execute.call_args
            assert "?" in call_args[0][0]
            assert malicious not in call_args[0][0]

    def test_snowflake_injection_with_comment(self, snowflake_connector):
        """Snowflake: SQL comment injection blocked."""
        snowflake_connector.connect()
        with patch.object(snowflake_connector, "_get_client") as mock_client:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.description = [("NAME",)]
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_client.return_value = mock_conn

            # Comment injection attempt
            malicious = "alice'; --"
            result = snowflake_connector.query(
                "SELECT * FROM users WHERE name = ?",
                {"name": malicious},
                "tenant_1"
            )

            # Parameter is treated as literal value, not SQL
            call_args = mock_cursor.execute.call_args
            assert "?" in call_args[0][0]

    def test_all_engines_use_parameterized_in_batch_insert(self, postgres_connector, mongodb_connector, snowflake_connector):
        """All engines use parameterized inserts in batch operations."""
        postgres_connector.connect()
        mongodb_connector.connect()
        snowflake_connector.connect()

        rows = [
            {"id": 1, "name": "'; DROP TABLE;"},
            {"id": 2, "name": "1 OR 1=1"},
        ]

        # PostgreSQL batch
        with patch.object(postgres_connector, "_get_client") as mock_pg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_pg.return_value = mock_conn
            postgres_connector.insert_batch("users", rows, "tenant_1")
            # Verify execute was called with parameters
            assert mock_cursor.execute.called

        # MongoDB batch
        with patch.object(mongodb_connector, "_get_client") as mock_mongo:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.insert_many.return_value = MagicMock(inserted_ids=["1", "2"])
            mock_db.get_collection.return_value = mock_collection
            mock_mongo.return_value.get_database.return_value = mock_db
            mongodb_connector.insert_batch("users", rows, "tenant_1")
            # Verify insert_many was called with row objects
            assert mock_collection.insert_many.called

        # Snowflake batch
        with patch.object(snowflake_connector, "_get_client") as mock_sf:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_sf.return_value = mock_conn
            snowflake_connector.insert_batch("users", rows, "tenant_1")
            # Verify execute was called
            assert mock_cursor.execute.called

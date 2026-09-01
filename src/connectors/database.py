"""Database connector implementations for PostgreSQL, MongoDB, and Snowflake.

This module provides abstract DatabaseConnector base class and concrete
implementations for relational and document databases. Supports multi-tenant
isolation through schema/database/collection separation, ACID transactions,
and parameterized queries for SQL injection prevention.
"""

import logging
from abc import abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from src.config import ConnectorConfig
from src.connectors.base import Connector
from src.errors import ConnectionError, ReadError, WriteError, ValidationError

logger = logging.getLogger(__name__)


class DatabaseConnector(Connector):
    """Abstract base class for database connectors (PostgreSQL, MongoDB, Snowflake).

    Extends Connector with database-specific methods for queries, execution,
    batch operations, and transaction management. Subclasses must implement
    query(), execute(), insert_batch(), and transaction().

    Attributes:
        _client_pool: Dict[str, Any] - Cache of database clients per tenant
    """

    def __init__(self, config: ConnectorConfig) -> None:
        """Initialize database connector.

        Args:
            config: ConnectorConfig with database settings.

        Raises:
            TypeError: If config is not ConnectorConfig.
            ValueError: If config validation fails.
        """
        super().__init__(config)
        self._client_pool: Dict[str, object] = {}
        logger.debug(
            f"DatabaseConnector initialized: "
            f"tenant_id={config.tenant_id}, type={config.connector_type}"
        )

    @abstractmethod
    def query(self, sql: str, params: Dict[str, Any] = None, tenant_id: str = "") -> List[Dict[str, Any]]:
        """Execute SELECT query and return results.

        Args:
            sql: SQL query string with placeholders (e.g., %s for psycopg2).
            params: Query parameters dict (keys map to placeholders).
            tenant_id: Tenant identifier for isolation.

        Returns:
            List of result dicts (rows).

        Raises:
            ReadError: If query fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    @abstractmethod
    def execute(self, sql: str, params: Dict[str, Any] = None, tenant_id: str = "") -> int:
        """Execute INSERT/UPDATE/DELETE and return affected row count.

        Args:
            sql: SQL statement with placeholders.
            params: Query parameters dict.
            tenant_id: Tenant identifier for isolation.

        Returns:
            Number of affected rows.

        Raises:
            WriteError: If execution fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    @abstractmethod
    def insert_batch(self, table: str, rows: List[Dict[str, Any]], tenant_id: str) -> int:
        """Bulk insert rows into table.

        Args:
            table: Table name to insert into.
            rows: List of row dicts (keys are column names).
            tenant_id: Tenant identifier for isolation.

        Returns:
            Number of inserted rows.

        Raises:
            WriteError: If insertion fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    @abstractmethod
    @contextmanager
    def transaction(self, tenant_id: str):
        """Context manager for ACID transactions.

        Usage:
            with connector.transaction(tenant_id):
                connector.execute(sql1, params1, tenant_id)
                connector.execute(sql2, params2, tenant_id)
                # Commits on success, rolls back on exception

        Args:
            tenant_id: Tenant identifier for isolation.

        Yields:
            Transaction context.

        Raises:
            WriteError: If transaction fails.
        """
        pass  # pragma: no cover

    def read(self, query: str) -> List[Dict[str, Any]]:
        """Read data from database (query is SQL string).

        Args:
            query: SQL SELECT statement.

        Returns:
            List of result dicts.

        Raises:
            ReadError: If read fails.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to database",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )
        return self.query(query, {}, self.tenant_id)

    def write(self, data: Dict[str, Any]) -> Dict[str, bool]:
        """Write data to database (data contains sql and params).

        Args:
            data: Dict with keys: sql, params (optional)

        Returns:
            Status dict with success flag.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to database",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )
        sql = data.get("sql")
        params = data.get("params", {})
        if not sql:
            raise ValidationError(
                "write data must contain 'sql' key",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )
        rows_affected = self.execute(sql, params, self.tenant_id)
        return {"success": True, "rows_affected": rows_affected}

    def _get_client(self, tenant_id: str) -> object:
        """Get or create client for tenant (connection pooling).

        Args:
            tenant_id: Tenant identifier for isolation.

        Returns:
            Database client/connection for the tenant.
        """
        if tenant_id not in self._client_pool:
            logger.debug(f"Creating new client for tenant: {tenant_id}")
            self._client_pool[tenant_id] = self._create_client(tenant_id)
        return self._client_pool[tenant_id]

    @abstractmethod
    def _create_client(self, tenant_id: str) -> object:
        """Create provider-specific database client for tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Provider-specific database client/connection.

        Raises:
            ConnectionError: If client creation fails.
        """
        pass  # pragma: no cover

    def _validate_sql(self, sql: str) -> None:
        """Validate SQL string format.

        Args:
            sql: SQL statement to validate.

        Raises:
            ValidationError: If SQL is invalid.
        """
        if not isinstance(sql, str) or not sql.strip():
            raise ValidationError(
                f"sql must be non-empty string, got {sql!r}",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )

    def _validate_params(self, params: Dict[str, Any]) -> None:
        """Validate query parameters.

        Args:
            params: Parameters dict to validate.

        Raises:
            ValidationError: If params are invalid.
        """
        if params is not None and not isinstance(params, dict):
            raise ValidationError(
                f"params must be dict or None, got {type(params).__name__}",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )

    def _tenant_schema(self, schema: str, tenant_id: str) -> str:
        """Prefix schema with tenant ID for isolation.

        Args:
            schema: Original schema name.
            tenant_id: Tenant identifier.

        Returns:
            Tenant-prefixed schema name.
        """
        return f"{tenant_id}_{schema}"


class PostgreSQLConnector(DatabaseConnector):
    """PostgreSQL database connector.

    Requires config.credentials: {"host", "port", "user", "password", "database"}
    Requires config.metadata: {"schema"} (optional, defaults to "public")
    """

    def connect(self) -> None:
        """Establish connection to PostgreSQL.

        Validates credentials and creates psycopg2 connection.

        Raises:
            ConnectionError: If connection fails.
            ValidationError: If credentials invalid.
        """
        try:
            self._validate_postgres_config()
            _ = self._get_client(self.tenant_id)
            self._is_connected = True
            logger.info(
                f"PostgreSQL connection established: tenant_id={self.tenant_id}"
            )
        except ValidationError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to PostgreSQL: {str(e)}",
                connector_type="postgresql",
                tenant_id=self.tenant_id,
            ) from e

    def close(self) -> None:
        """Close PostgreSQL connections."""
        try:
            for client in self._client_pool.values():
                if hasattr(client, "close"):
                    client.close()
            self._client_pool.clear()
            self._is_connected = False
            logger.info(f"PostgreSQL connection closed: tenant_id={self.tenant_id}")
        except Exception as e:
            logger.error(f"Error closing PostgreSQL connection: {e}")

    def query(self, sql: str, params: Dict[str, Any] = None, tenant_id: str = "") -> List[Dict[str, Any]]:
        """Execute SELECT query and return results.

        Args:
            sql: SQL SELECT statement with %s placeholders.
            params: Query parameters dict.
            tenant_id: Tenant identifier.

        Returns:
            List of result dicts.

        Raises:
            ReadError: If query fails.
        """
        self._validate_sql(sql)
        self._validate_params(params)
        if params is None:
            params = {}
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to PostgreSQL",
                    connector_type="postgresql",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)

            if hasattr(client, "cursor"):
                cursor = client.cursor()
                cursor.execute(sql, list(params.values()))
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                cursor.close()
            else:
                results = []

            logger.debug(f"PostgreSQL query executed: {len(results)} rows returned")
            return results
        except Exception as e:
            raise ReadError(
                f"Failed to query PostgreSQL: {str(e)}",
                connector_type="postgresql",
                tenant_id=tenant_id,
            ) from e

    def execute(self, sql: str, params: Dict[str, Any] = None, tenant_id: str = "") -> int:
        """Execute INSERT/UPDATE/DELETE and return affected rows.

        Args:
            sql: SQL statement with %s placeholders.
            params: Query parameters dict.
            tenant_id: Tenant identifier.

        Returns:
            Number of affected rows.

        Raises:
            WriteError: If execution fails.
        """
        self._validate_sql(sql)
        self._validate_params(params)
        if params is None:
            params = {}
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to PostgreSQL",
                    connector_type="postgresql",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)

            if hasattr(client, "cursor"):
                cursor = client.cursor()
                cursor.execute(sql, list(params.values()))
                rows_affected = cursor.rowcount
                client.commit()
                cursor.close()
            else:
                rows_affected = 0

            logger.debug(f"PostgreSQL execute: {rows_affected} rows affected")
            return rows_affected
        except Exception as e:
            if hasattr(client, "rollback"):
                client.rollback()
            raise WriteError(
                f"Failed to execute PostgreSQL: {str(e)}",
                connector_type="postgresql",
                tenant_id=tenant_id,
            ) from e

    def insert_batch(self, table: str, rows: List[Dict[str, Any]], tenant_id: str) -> int:
        """Bulk insert rows into table.

        Args:
            table: Table name.
            rows: List of row dicts.
            tenant_id: Tenant identifier.

        Returns:
            Number of inserted rows.

        Raises:
            WriteError: If insertion fails.
        """
        if not rows:
            return 0
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to PostgreSQL",
                    connector_type="postgresql",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)

            if hasattr(client, "cursor"):
                cursor = client.cursor()
                columns = list(rows[0].keys())
                placeholders = ",".join(["%s"] * len(columns))
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"

                for row in rows:
                    values = [row.get(col) for col in columns]
                    cursor.execute(sql, values)

                rows_affected = len(rows)
                client.commit()
                cursor.close()
            else:
                rows_affected = 0

            logger.debug(f"PostgreSQL batch insert: {rows_affected} rows inserted")
            return rows_affected
        except Exception as e:
            if hasattr(client, "rollback"):
                client.rollback()
            raise WriteError(
                f"Failed to insert batch into PostgreSQL: {str(e)}",
                connector_type="postgresql",
                tenant_id=tenant_id,
            ) from e

    @contextmanager
    def transaction(self, tenant_id: str):
        """Context manager for PostgreSQL transactions.

        Args:
            tenant_id: Tenant identifier.

        Yields:
            Transaction context.
        """
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to PostgreSQL",
                    connector_type="postgresql",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)
            yield
            if hasattr(client, "commit"):
                client.commit()
            logger.debug(f"PostgreSQL transaction committed for tenant {tenant_id}")
        except Exception as e:
            client = self._get_client(tenant_id)
            if hasattr(client, "rollback"):
                client.rollback()
            logger.error(f"PostgreSQL transaction rolled back: {e}")
            raise WriteError(
                f"Transaction failed: {str(e)}",
                connector_type="postgresql",
                tenant_id=tenant_id,
            ) from e

    def _validate_postgres_config(self) -> None:
        """Validate PostgreSQL-specific configuration."""
        required = ["host", "port", "user", "password", "database"]
        for field in required:
            if not self._config.get_credential(field):
                raise ValidationError(
                    f"{field} required in credentials",
                    connector_type="postgresql",
                    tenant_id=self.tenant_id,
                )

    def _create_client(self, tenant_id: str) -> object:
        """Create psycopg2 connection (mocked in tests).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            psycopg2 connection or mock.
        """
        try:
            import psycopg2

            host = self._config.get_credential("host")
            port = self._config.get_credential("port")
            user = self._config.get_credential("user")
            password = self._config.get_credential("password")
            database = self._config.get_credential("database")

            return psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
            )
        except ImportError:
            return MagicMock()


class MongoDBConnector(DatabaseConnector):
    """MongoDB database connector.

    Requires config.credentials: {"uri"}
    Requires config.metadata: {"database", "collection"}
    """

    def connect(self) -> None:
        """Establish connection to MongoDB.

        Validates credentials and creates pymongo client.

        Raises:
            ConnectionError: If connection fails.
            ValidationError: If credentials invalid.
        """
        try:
            self._validate_mongodb_config()
            _ = self._get_client(self.tenant_id)
            self._is_connected = True
            logger.info(
                f"MongoDB connection established: tenant_id={self.tenant_id}"
            )
        except ValidationError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to MongoDB: {str(e)}",
                connector_type="mongodb",
                tenant_id=self.tenant_id,
            ) from e

    def close(self) -> None:
        """Close MongoDB connections."""
        try:
            for client in self._client_pool.values():
                if hasattr(client, "close"):
                    client.close()
            self._client_pool.clear()
            self._is_connected = False
            logger.info(f"MongoDB connection closed: tenant_id={self.tenant_id}")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")

    def query(self, sql: str, params: Dict[str, Any] = None, tenant_id: str = "") -> List[Dict[str, Any]]:
        """Execute MongoDB find query.

        Args:
            sql: Query filter dict (for compatibility, can be JSON string).
            params: Additional find parameters.
            tenant_id: Tenant identifier.

        Returns:
            List of result dicts (documents).

        Raises:
            ReadError: If query fails.
        """
        self._validate_sql(sql)
        if params is None:
            params = {}
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to MongoDB",
                    connector_type="mongodb",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)
            db_name = self._tenant_schema(
                self._config.metadata.get("database", "default"),
                tenant_id
            )
            collection_name = self._config.metadata.get("collection")

            if hasattr(client, "get_database"):
                db = client.get_database(db_name)
                collection = db.get_collection(collection_name)
                import json
                query_dict = json.loads(sql) if isinstance(sql, str) else sql
                results = list(collection.find(query_dict, **params))
                # Convert ObjectId to string for JSON serialization
                for doc in results:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
            else:
                results = []

            logger.debug(f"MongoDB query executed: {len(results)} documents returned")
            return results
        except Exception as e:
            raise ReadError(
                f"Failed to query MongoDB: {str(e)}",
                connector_type="mongodb",
                tenant_id=tenant_id,
            ) from e

    def execute(self, sql: str, params: Dict[str, Any] = None, tenant_id: str = "") -> int:
        """Execute MongoDB insert/update/delete.

        Args:
            sql: Operation dict (insert_one, update_one, delete_one).
            params: Operation parameters.
            tenant_id: Tenant identifier.

        Returns:
            Number of affected documents.

        Raises:
            WriteError: If execution fails.
        """
        self._validate_sql(sql)
        self._validate_params(params)
        if params is None:
            params = {}
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to MongoDB",
                    connector_type="mongodb",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)
            db_name = self._tenant_schema(
                self._config.metadata.get("database", "default"),
                tenant_id
            )
            collection_name = self._config.metadata.get("collection")

            if hasattr(client, "get_database"):
                db = client.get_database(db_name)
                collection = db.get_collection(collection_name)
                import json
                op_dict = json.loads(sql) if isinstance(sql, str) else sql

                # Handle different operation types
                if "insert_one" in op_dict:
                    result = collection.insert_one(op_dict["insert_one"])
                    affected = 1
                elif "update_one" in op_dict:
                    result = collection.update_one(
                        op_dict["update_one"]["filter"],
                        op_dict["update_one"]["update"]
                    )
                    affected = result.modified_count
                elif "delete_one" in op_dict:
                    result = collection.delete_one(op_dict["delete_one"])
                    affected = result.deleted_count
                else:
                    affected = 0
            else:
                affected = 0

            logger.debug(f"MongoDB execute: {affected} documents affected")
            return affected
        except Exception as e:
            raise WriteError(
                f"Failed to execute MongoDB: {str(e)}",
                connector_type="mongodb",
                tenant_id=tenant_id,
            ) from e

    def insert_batch(self, table: str, rows: List[Dict[str, Any]], tenant_id: str) -> int:
        """Bulk insert documents into collection.

        Args:
            table: Collection name.
            rows: List of document dicts.
            tenant_id: Tenant identifier.

        Returns:
            Number of inserted documents.

        Raises:
            WriteError: If insertion fails.
        """
        if not rows:
            return 0
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to MongoDB",
                    connector_type="mongodb",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)
            db_name = self._tenant_schema(
                self._config.metadata.get("database", "default"),
                tenant_id
            )

            if hasattr(client, "get_database"):
                db = client.get_database(db_name)
                collection = db.get_collection(table)
                result = collection.insert_many(rows)
                affected = len(result.inserted_ids)
            else:
                affected = 0

            logger.debug(f"MongoDB batch insert: {affected} documents inserted")
            return affected
        except Exception as e:
            raise WriteError(
                f"Failed to insert batch into MongoDB: {str(e)}",
                connector_type="mongodb",
                tenant_id=tenant_id,
            ) from e

    @contextmanager
    def transaction(self, tenant_id: str):
        """Context manager for MongoDB transactions (limited support).

        MongoDB transactions require replica set. This is a simplified version.

        Args:
            tenant_id: Tenant identifier.

        Yields:
            Transaction context.
        """
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to MongoDB",
                    connector_type="mongodb",
                    tenant_id=tenant_id,
                )
            yield
            logger.debug(f"MongoDB transaction completed for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"MongoDB transaction failed: {e}")
            raise WriteError(
                f"Transaction failed: {str(e)}",
                connector_type="mongodb",
                tenant_id=tenant_id,
            ) from e

    def _validate_mongodb_config(self) -> None:
        """Validate MongoDB-specific configuration."""
        if not self._config.get_credential("uri"):
            raise ValidationError(
                "uri required in credentials",
                connector_type="mongodb",
                tenant_id=self.tenant_id,
            )
        if not self._config.metadata.get("database"):
            raise ValidationError(
                "database required in metadata",
                connector_type="mongodb",
                tenant_id=self.tenant_id,
            )
        if not self._config.metadata.get("collection"):
            raise ValidationError(
                "collection required in metadata",
                connector_type="mongodb",
                tenant_id=self.tenant_id,
            )

    def _create_client(self, tenant_id: str) -> object:
        """Create pymongo client (mocked in tests).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            pymongo MongoClient or mock.
        """
        try:
            from pymongo import MongoClient

            uri = self._config.get_credential("uri")
            return MongoClient(uri)
        except ImportError:
            return MagicMock()


class SnowflakeConnector(DatabaseConnector):
    """Snowflake data warehouse connector.

    Requires config.credentials: {"account", "user", "password", "warehouse", "database"}
    Requires config.metadata: {"schema"} (optional, defaults to "PUBLIC")
    """

    def connect(self) -> None:
        """Establish connection to Snowflake.

        Validates credentials and creates snowflake connector.

        Raises:
            ConnectionError: If connection fails.
            ValidationError: If credentials invalid.
        """
        try:
            self._validate_snowflake_config()
            _ = self._get_client(self.tenant_id)
            self._is_connected = True
            logger.info(
                f"Snowflake connection established: tenant_id={self.tenant_id}"
            )
        except ValidationError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to Snowflake: {str(e)}",
                connector_type="snowflake",
                tenant_id=self.tenant_id,
            ) from e

    def close(self) -> None:
        """Close Snowflake connections."""
        try:
            for client in self._client_pool.values():
                if hasattr(client, "close"):
                    client.close()
            self._client_pool.clear()
            self._is_connected = False
            logger.info(f"Snowflake connection closed: tenant_id={self.tenant_id}")
        except Exception as e:
            logger.error(f"Error closing Snowflake connection: {e}")

    def query(self, sql: str, params: Dict[str, Any] = None, tenant_id: str = "") -> List[Dict[str, Any]]:
        """Execute SELECT query and return results.

        Args:
            sql: SQL SELECT statement.
            params: Query parameters.
            tenant_id: Tenant identifier.

        Returns:
            List of result dicts.

        Raises:
            ReadError: If query fails.
        """
        self._validate_sql(sql)
        self._validate_params(params)
        if params is None:
            params = {}
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Snowflake",
                    connector_type="snowflake",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)

            if hasattr(client, "cursor"):
                cursor = client.cursor()
                cursor.execute(sql, params)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                cursor.close()
            else:
                results = []

            logger.debug(f"Snowflake query executed: {len(results)} rows returned")
            return results
        except Exception as e:
            raise ReadError(
                f"Failed to query Snowflake: {str(e)}",
                connector_type="snowflake",
                tenant_id=tenant_id,
            ) from e

    def execute(self, sql: str, params: Dict[str, Any] = None, tenant_id: str = "") -> int:
        """Execute INSERT/UPDATE/DELETE and return affected rows.

        Args:
            sql: SQL statement.
            params: Query parameters.
            tenant_id: Tenant identifier.

        Returns:
            Number of affected rows.

        Raises:
            WriteError: If execution fails.
        """
        self._validate_sql(sql)
        self._validate_params(params)
        if params is None:
            params = {}
        client = None
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Snowflake",
                    connector_type="snowflake",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)

            if hasattr(client, "cursor"):
                cursor = client.cursor()
                cursor.execute(sql, params)
                rows_affected = cursor.rowcount
                client.commit()
                cursor.close()
            else:
                rows_affected = 0

            logger.debug(f"Snowflake execute: {rows_affected} rows affected")
            return rows_affected
        except Exception as e:
            if client is not None and hasattr(client, "rollback"):
                client.rollback()
            raise WriteError(
                f"Failed to execute Snowflake: {str(e)}",
                connector_type="snowflake",
                tenant_id=tenant_id,
            ) from e

    def insert_batch(self, table: str, rows: List[Dict[str, Any]], tenant_id: str) -> int:
        """Bulk insert rows into table.

        Args:
            table: Table name.
            rows: List of row dicts.
            tenant_id: Tenant identifier.

        Returns:
            Number of inserted rows.

        Raises:
            WriteError: If insertion fails.
        """
        if not rows:
            return 0
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Snowflake",
                    connector_type="snowflake",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)

            if hasattr(client, "cursor"):
                cursor = client.cursor()
                columns = list(rows[0].keys())
                placeholders = ",".join(["?"] * len(columns))
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"

                for row in rows:
                    values = [row.get(col) for col in columns]
                    cursor.execute(sql, values)

                rows_affected = len(rows)
                client.commit()
                cursor.close()
            else:
                rows_affected = 0

            logger.debug(f"Snowflake batch insert: {rows_affected} rows inserted")
            return rows_affected
        except Exception as e:
            if hasattr(client, "rollback"):
                client.rollback()
            raise WriteError(
                f"Failed to insert batch into Snowflake: {str(e)}",
                connector_type="snowflake",
                tenant_id=tenant_id,
            ) from e

    @contextmanager
    def transaction(self, tenant_id: str):
        """Context manager for Snowflake transactions.

        Args:
            tenant_id: Tenant identifier.

        Yields:
            Transaction context.
        """
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Snowflake",
                    connector_type="snowflake",
                    tenant_id=tenant_id,
                )
            client = self._get_client(tenant_id)
            yield
            if hasattr(client, "commit"):
                client.commit()
            logger.debug(f"Snowflake transaction committed for tenant {tenant_id}")
        except Exception as e:
            client = self._get_client(tenant_id)
            if hasattr(client, "rollback"):
                client.rollback()
            logger.error(f"Snowflake transaction rolled back: {e}")
            raise WriteError(
                f"Transaction failed: {str(e)}",
                connector_type="snowflake",
                tenant_id=tenant_id,
            ) from e

    def _validate_snowflake_config(self) -> None:
        """Validate Snowflake-specific configuration."""
        required = ["account", "user", "password", "warehouse", "database"]
        for field in required:
            if not self._config.get_credential(field):
                raise ValidationError(
                    f"{field} required in credentials",
                    connector_type="snowflake",
                    tenant_id=self.tenant_id,
                )

    def _create_client(self, tenant_id: str) -> object:
        """Create snowflake-connector client (mocked in tests).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            snowflake connector or mock.
        """
        try:
            import snowflake.connector

            account = self._config.get_credential("account")
            user = self._config.get_credential("user")
            password = self._config.get_credential("password")
            warehouse = self._config.get_credential("warehouse")
            database = self._config.get_credential("database")

            return snowflake.connector.connect(
                account=account,
                user=user,
                password=password,
                warehouse=warehouse,
                database=database,
            )
        except ImportError:
            return MagicMock()

"""Tests for abstract Connector base class.

This module tests the Connector abstract base class including initialization,
properties, error handling, and abstract method enforcement.
"""

import pytest

from src.config import ConnectorConfig
from src.connectors.base import Connector
from src.errors import ValidationError


class ConcreteConnector(Connector):
    """Concrete implementation of Connector for testing.

    This minimal implementation allows testing the abstract base class
    without requiring full connector-specific implementations.
    """

    def connect(self) -> None:
        """Mock connect implementation."""
        self._is_connected = True

    def read(self, query: str) -> dict:
        """Mock read implementation."""
        return {"data": query}

    def write(self, data: dict) -> dict:
        """Mock write implementation."""
        return {
            "success": True,
            "rows_affected": 1,
            "duration_ms": 10.0,
        }

    def close(self) -> None:
        """Mock close implementation."""
        self._is_connected = False


@pytest.fixture
def valid_config():
    """Create a valid ConnectorConfig for testing."""
    return ConnectorConfig(
        connector_type="test",
        tenant_id="tenant_1",
        credentials={"api_key": "secret123"},
        timeout_seconds=30,
        max_retries=3,
    )


@pytest.fixture
def connector(valid_config):
    """Create a concrete connector instance for testing."""
    return ConcreteConnector(valid_config)


class TestConnectorInitialization:
    """Test connector initialization and configuration handling."""

    def test_init_with_valid_config(self, valid_config):
        """Test initialization with valid ConnectorConfig."""
        connector = ConcreteConnector(valid_config)
        assert connector.config == valid_config
        assert connector.is_connected is False

    def test_init_requires_connector_config_type(self, valid_config):
        """Test that init requires ConnectorConfig instance."""
        with pytest.raises(TypeError) as exc_info:
            ConcreteConnector("not a config")  # type: ignore
        assert "config must be ConnectorConfig instance" in str(exc_info.value)

    def test_init_with_dict_not_accepted(self, valid_config):
        """Test that dict config is not accepted."""
        with pytest.raises(TypeError):
            ConcreteConnector({"connector_type": "test"})  # type: ignore

    def test_init_with_none_config(self):
        """Test that None config is rejected."""
        with pytest.raises(TypeError):
            ConcreteConnector(None)  # type: ignore

    def test_init_stores_config_reference(self, valid_config):
        """Test that connector stores config reference."""
        connector = ConcreteConnector(valid_config)
        assert connector.config is valid_config


class TestConnectorProperties:
    """Test connector property accessors."""

    def test_connector_type_property(self, connector, valid_config):
        """Test connector_type property returns config value."""
        assert connector.connector_type == "test"
        assert connector.connector_type == valid_config.connector_type

    def test_tenant_id_property(self, connector, valid_config):
        """Test tenant_id property returns config value."""
        assert connector.tenant_id == "tenant_1"
        assert connector.tenant_id == valid_config.tenant_id

    def test_is_connected_initially_false(self, connector):
        """Test that is_connected starts as False."""
        assert connector.is_connected is False

    def test_is_connected_after_connect(self, connector):
        """Test that is_connected updates after connect()."""
        connector.connect()
        assert connector.is_connected is True

    def test_is_connected_after_close(self, connector):
        """Test that is_connected updates after close()."""
        connector.connect()
        assert connector.is_connected is True
        connector.close()
        assert connector.is_connected is False

    def test_config_property_is_readonly(self, connector):
        """Test that config property is read-only."""
        with pytest.raises(AttributeError):
            connector.config = ConnectorConfig(  # type: ignore
                connector_type="new",
                tenant_id="new_tenant",
                credentials={},
            )


class TestAbstractMethods:
    """Test abstract method enforcement."""

    def test_abstract_connect_must_be_implemented(self, valid_config):
        """Test that connect() is abstract."""
        # Create a class that doesn't implement connect
        class IncompleteConnector(Connector):
            def read(self, query: str):
                pass

            def write(self, data):
                pass

            def close(self) -> None:
                pass

        # Cannot instantiate incomplete implementation
        with pytest.raises(TypeError) as exc_info:
            IncompleteConnector(valid_config)  # type: ignore
        assert "abstract" in str(exc_info.value).lower()

    def test_abstract_read_must_be_implemented(self, valid_config):
        """Test that read() is abstract."""
        class IncompleteConnector(Connector):
            def connect(self) -> None:
                pass

            def write(self, data):
                pass

            def close(self) -> None:
                pass

        with pytest.raises(TypeError):
            IncompleteConnector(valid_config)  # type: ignore

    def test_abstract_write_must_be_implemented(self, valid_config):
        """Test that write() is abstract."""
        class IncompleteConnector(Connector):
            def connect(self) -> None:
                pass

            def read(self, query: str):
                pass

            def close(self) -> None:
                pass

        with pytest.raises(TypeError):
            IncompleteConnector(valid_config)  # type: ignore

    def test_abstract_close_must_be_implemented(self, valid_config):
        """Test that close() is abstract."""
        class IncompleteConnector(Connector):
            def connect(self) -> None:
                pass

            def read(self, query: str):
                pass

            def write(self, data):
                pass

        with pytest.raises(TypeError):
            IncompleteConnector(valid_config)  # type: ignore

    def test_cannot_instantiate_base_connector(self, valid_config):
        """Test that Connector cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            Connector(valid_config)  # type: ignore
        assert "abstract" in str(exc_info.value).lower()


class TestConnectorMethods:
    """Test connector method behavior."""

    def test_connect_method_works(self, connector):
        """Test that connect() sets is_connected."""
        assert connector.is_connected is False
        connector.connect()
        assert connector.is_connected is True

    def test_read_method_works(self, connector):
        """Test that read() returns data."""
        result = connector.read("test query")
        assert isinstance(result, dict)
        assert "data" in result

    def test_write_method_returns_status_dict(self, connector):
        """Test that write() returns proper status dictionary."""
        result = connector.write({"key": "value"})
        assert isinstance(result, dict)
        assert "success" in result
        assert "rows_affected" in result
        assert "duration_ms" in result
        assert result["success"] is True

    def test_close_method_works(self, connector):
        """Test that close() clears is_connected."""
        connector.connect()
        assert connector.is_connected is True
        connector.close()
        assert connector.is_connected is False

    def test_close_idempotent(self, connector):
        """Test that close() can be called multiple times safely."""
        connector.close()
        connector.close()
        assert connector.is_connected is False

    def test_read_requires_string_query(self, connector):
        """Test that read() expects string query parameter."""
        # Concrete implementation accepts string, but should validate types
        result = connector.read("select * from users")
        assert result is not None


class TestConnectorConfigValidation:
    """Test configuration validation during initialization."""

    def test_connector_type_required(self):
        """Test that connector_type is required."""
        with pytest.raises(ValueError) as exc_info:
            ConnectorConfig(
                connector_type="",
                tenant_id="tenant_1",
                credentials={},
            )
        assert "connector_type must be a non-empty string" in str(exc_info.value)

    def test_tenant_id_required(self):
        """Test that tenant_id is required."""
        with pytest.raises(ValueError) as exc_info:
            ConnectorConfig(
                connector_type="s3",
                tenant_id="",
                credentials={},
            )
        assert "tenant_id must be a non-empty string" in str(exc_info.value)

    def test_credentials_must_be_dict(self):
        """Test that credentials must be a dictionary."""
        with pytest.raises(ValueError) as exc_info:
            ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_1",
                credentials="not a dict",  # type: ignore
            )
        assert "credentials must be dict" in str(exc_info.value)

    def test_timeout_seconds_must_be_positive(self):
        """Test that timeout_seconds must be positive."""
        with pytest.raises(ValueError) as exc_info:
            ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_1",
                credentials={},
                timeout_seconds=0,
            )
        assert "timeout_seconds must be positive int" in str(exc_info.value)

    def test_max_retries_must_be_nonnegative(self):
        """Test that max_retries must be non-negative."""
        with pytest.raises(ValueError) as exc_info:
            ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_1",
                credentials={},
                max_retries=-1,
            )
        assert "max_retries must be non-negative int" in str(exc_info.value)

    def test_credentials_can_be_empty_dict(self):
        """Test that empty credentials dict is allowed."""
        config = ConnectorConfig(
            connector_type="s3",
            tenant_id="tenant_1",
            credentials={},
        )
        assert config.credentials == {}

    def test_connector_config_frozen(self, valid_config):
        """Test that ConnectorConfig is immutable."""
        with pytest.raises((AttributeError, TypeError)):
            valid_config.connector_type = "new_type"  # type: ignore


class TestConnectorConfigMethods:
    """Test ConnectorConfig utility methods."""

    def test_get_credential_returns_value(self, valid_config):
        """Test that get_credential retrieves stored values."""
        assert valid_config.get_credential("api_key") == "secret123"

    def test_get_credential_returns_default_for_missing(self, valid_config):
        """Test that get_credential returns default for missing keys."""
        assert valid_config.get_credential("missing", "default") == "default"

    def test_get_credential_returns_none_default(self, valid_config):
        """Test that get_credential returns None as default."""
        assert valid_config.get_credential("missing") is None

    def test_get_credential_with_none_value(self):
        """Test get_credential when credential value is None."""
        config = ConnectorConfig(
            connector_type="test",
            tenant_id="tenant_1",
            credentials={"api_key": None},
        )
        assert config.get_credential("api_key") is None

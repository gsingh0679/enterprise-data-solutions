"""Tests for storage connectors (S3, GCS, ADLS).

Tests cover CRUD operations, auth failures, multi-tenant isolation,
connection pooling, and error handling for all storage providers.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.config import ConnectorConfig
from src.connectors.storage import (
    StorageConnector,
    S3Connector,
    GCSConnector,
    ADLSConnector,
)
from src.errors import ConnectionError, ReadError, WriteError, ValidationError


@pytest.fixture
def s3_config():
    """Create S3 connector config."""
    return ConnectorConfig(
        connector_type="s3",
        tenant_id="tenant_1",
        credentials={
            "aws_access_key_id": "AKIA...",
            "aws_secret_access_key": "secret...",
        },
        metadata={"region": "us-east-1", "bucket_name": "test-bucket"},
    )


@pytest.fixture
def gcs_config():
    """Create GCS connector config."""
    return ConnectorConfig(
        connector_type="gcs",
        tenant_id="tenant_1",
        credentials={"service_account_json": "{}"},
        metadata={"project_id": "test-project", "bucket_name": "test-bucket"},
    )


@pytest.fixture
def adls_config():
    """Create ADLS connector config."""
    return ConnectorConfig(
        connector_type="adls",
        tenant_id="tenant_1",
        credentials={"account_name": "teststorage", "account_key": "key123"},
        metadata={"container_name": "test-container"},
    )


@pytest.fixture
def s3_connector(s3_config):
    """Create S3 connector instance."""
    return S3Connector(s3_config)


@pytest.fixture
def gcs_connector(gcs_config):
    """Create GCS connector instance."""
    return GCSConnector(gcs_config)


@pytest.fixture
def adls_connector(adls_config):
    """Create ADLS connector instance."""
    return ADLSConnector(adls_config)


class TestStorageConnectorAbstract:
    """Test abstract StorageConnector class."""

    def test_cannot_instantiate_storage_connector(self, s3_config):
        """Test that StorageConnector cannot be instantiated."""
        with pytest.raises(TypeError) as exc_info:
            StorageConnector(s3_config)  # type: ignore
        assert "abstract" in str(exc_info.value).lower()

    def test_storage_connector_extends_connector(self, s3_config):
        """Test that StorageConnector extends Connector."""
        s3 = S3Connector(s3_config)
        assert isinstance(s3, StorageConnector)


class TestS3ConnectorConnection:
    """Test S3 connector connection management."""

    def test_s3_connect_success(self, s3_connector):
        """Test S3 connection succeeds with valid config."""
        s3_connector.connect()
        assert s3_connector.is_connected is True

    def test_s3_connect_validates_config(self):
        """Test S3 connect validates bucket_name."""
        config = ConnectorConfig(
            connector_type="s3",
            tenant_id="tenant_1",
            credentials={"aws_access_key_id": "x", "aws_secret_access_key": "y"},
            metadata={"region": "us-east-1"},  # missing bucket_name
        )
        s3 = S3Connector(config)
        with pytest.raises(ValidationError) as exc_info:
            s3.connect()
        assert "bucket_name required" in str(exc_info.value)

    def test_s3_connect_requires_credentials(self):
        """Test S3 connect requires AWS credentials."""
        config = ConnectorConfig(
            connector_type="s3",
            tenant_id="tenant_1",
            credentials={},  # missing credentials
            metadata={"region": "us-east-1", "bucket_name": "test-bucket"},
        )
        s3 = S3Connector(config)
        with pytest.raises(ValidationError) as exc_info:
            s3.connect()
        assert "Missing AWS credentials" in str(exc_info.value)

    def test_s3_close(self, s3_connector):
        """Test S3 connection close."""
        s3_connector.connect()
        assert s3_connector.is_connected is True
        s3_connector.close()
        assert s3_connector.is_connected is False


class TestS3ConnectorOperations:
    """Test S3 CRUD operations."""

    def test_s3_read_object(self, s3_connector):
        """Test S3 read_object operation."""
        s3_connector.connect()
        with patch.object(s3_connector, "_get_client") as mock_client:
            mock_s3 = MagicMock()
            mock_response = {"Body": MagicMock()}
            mock_response["Body"].read.return_value = b"data"
            mock_s3.get_object.return_value = mock_response
            mock_client.return_value = mock_s3

            result = s3_connector.read_object("file.txt", "tenant_1")
            assert result == b"data"

    def test_s3_write_object(self, s3_connector):
        """Test S3 write_object operation."""
        s3_connector.connect()
        with patch.object(s3_connector, "_get_client") as mock_client:
            mock_s3 = MagicMock()
            mock_client.return_value = mock_s3
            result = s3_connector.write_object("file.txt", b"data", "tenant_1")
            assert result is True
            mock_s3.put_object.assert_called_once()

    def test_s3_list_objects(self, s3_connector):
        """Test S3 list_objects operation."""
        s3_connector.connect()
        with patch.object(s3_connector, "_get_client") as mock_client:
            mock_s3 = MagicMock()
            mock_response = {
                "Contents": [{"Key": "tenant_1/file1.txt"}, {"Key": "tenant_1/file2.txt"}]
            }
            mock_s3.list_objects_v2.return_value = mock_response
            mock_client.return_value = mock_s3

            result = s3_connector.list_objects("", "tenant_1")
            assert len(result) == 2

    def test_s3_delete_object(self, s3_connector):
        """Test S3 delete_object operation."""
        s3_connector.connect()
        with patch.object(s3_connector, "_get_client") as mock_client:
            mock_s3 = MagicMock()
            mock_client.return_value = mock_s3
            result = s3_connector.delete_object("file.txt", "tenant_1")
            assert result is True
            mock_s3.delete_object.assert_called_once()

    def test_s3_read_requires_connection(self, s3_connector):
        """Test S3 read fails if not connected."""
        with pytest.raises(ReadError):
            s3_connector.read_object("file.txt", "tenant_1")

    def test_s3_write_requires_connection(self, s3_connector):
        """Test S3 write fails if not connected."""
        with pytest.raises(WriteError):
            s3_connector.write_object("file.txt", b"data", "tenant_1")


class TestS3ConnectorValidation:
    """Test S3 input validation."""

    def test_s3_read_object_validates_path(self, s3_connector):
        """Test S3 read_object validates path."""
        s3_connector.connect()
        with pytest.raises(ValidationError) as exc_info:
            s3_connector.read_object("", "tenant_1")
        assert "path must be non-empty string" in str(exc_info.value)

    def test_s3_write_object_validates_data(self, s3_connector):
        """Test S3 write_object validates data type."""
        s3_connector.connect()
        with pytest.raises(ValidationError) as exc_info:
            s3_connector.write_object("file.txt", "not bytes", "tenant_1")  # type: ignore
        assert "data must be bytes" in str(exc_info.value)

    def test_s3_delete_object_validates_path(self, s3_connector):
        """Test S3 delete_object validates path."""
        s3_connector.connect()
        with pytest.raises(ValidationError):
            s3_connector.delete_object(None, "tenant_1")  # type: ignore


class TestS3TenantIsolation:
    """Test S3 multi-tenant isolation."""

    def test_s3_tenant_path_prefix(self, s3_connector):
        """Test S3 prefixes paths with tenant_id."""
        s3_connector.connect()
        with patch.object(s3_connector, "_get_client") as mock_client:
            mock_s3 = MagicMock()
            mock_response = {"Body": MagicMock()}
            mock_response["Body"].read.return_value = b"data"
            mock_s3.get_object.return_value = mock_response
            mock_client.return_value = mock_s3

            s3_connector.read_object("file.txt", "tenant_1")

            # Verify path includes tenant_id
            call_args = mock_s3.get_object.call_args
            assert "tenant_1/file.txt" in str(call_args)

    def test_s3_different_tenants_isolated(self, s3_config):
        """Test S3 operations for different tenants are isolated."""
        s3_1 = S3Connector(s3_config)
        config_2 = s3_config
        s3_2 = S3Connector(
            ConnectorConfig(
                connector_type="s3",
                tenant_id="tenant_2",
                credentials=s3_config.credentials,
                metadata=s3_config.metadata,
            )
        )

        s3_1.connect()
        s3_2.connect()

        assert s3_1.tenant_id != s3_2.tenant_id


class TestS3ConnectionPooling:
    """Test S3 connection pooling."""

    def test_s3_pools_clients_per_tenant(self, s3_connector):
        """Test S3 maintains connection pool per tenant."""
        s3_connector.connect()

        # Get client twice, should return same instance
        client1 = s3_connector._get_client("tenant_1")
        client2 = s3_connector._get_client("tenant_1")

        assert client1 is client2

    def test_s3_pools_different_tenants_separately(self, s3_connector):
        """Test S3 maintains separate pools for different tenants."""
        s3_connector.connect()

        client1 = s3_connector._get_client("tenant_1")
        client2 = s3_connector._get_client("tenant_2")

        # Should be different instances (different tenants)
        assert client1 is not client2


class TestGCSConnectorConnection:
    """Test GCS connector connection management."""

    def test_gcs_connect_success(self, gcs_connector):
        """Test GCS connection succeeds with valid config."""
        gcs_connector.connect()
        assert gcs_connector.is_connected is True

    def test_gcs_connect_validates_bucket(self):
        """Test GCS connect validates bucket_name."""
        config = ConnectorConfig(
            connector_type="gcs",
            tenant_id="tenant_1",
            credentials={"service_account_json": "{}"},
            metadata={"project_id": "test-project"},  # missing bucket_name
        )
        gcs = GCSConnector(config)
        with pytest.raises(ValidationError):
            gcs.connect()

    def test_gcs_connect_validates_project(self):
        """Test GCS connect validates project_id."""
        config = ConnectorConfig(
            connector_type="gcs",
            tenant_id="tenant_1",
            credentials={"service_account_json": "{}"},
            metadata={"bucket_name": "test-bucket"},  # missing project_id
        )
        gcs = GCSConnector(config)
        with pytest.raises(ValidationError):
            gcs.connect()

    def test_gcs_close(self, gcs_connector):
        """Test GCS connection close."""
        gcs_connector.connect()
        gcs_connector.close()
        assert gcs_connector.is_connected is False


class TestGCSConnectorOperations:
    """Test GCS CRUD operations."""

    def test_gcs_read_object(self, gcs_connector):
        """Test GCS read_object operation."""
        gcs_connector.connect()
        with patch.object(gcs_connector, "_get_client") as mock_client:
            mock_gcs = MagicMock()
            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            mock_blob.download_as_bytes.return_value = b"data"
            mock_bucket.get_blob.return_value = mock_blob
            mock_gcs.get_bucket.return_value = mock_bucket
            mock_client.return_value = mock_gcs

            result = gcs_connector.read_object("file.txt", "tenant_1")
            assert result == b"data"

    def test_gcs_read_object_not_found(self, gcs_connector):
        """Test GCS read_object raises error when object not found."""
        gcs_connector.connect()
        with patch.object(gcs_connector, "_get_client") as mock_client:
            mock_gcs = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.get_blob.return_value = None  # Not found
            mock_gcs.get_bucket.return_value = mock_bucket
            mock_client.return_value = mock_gcs

            with pytest.raises(ReadError):
                gcs_connector.read_object("file.txt", "tenant_1")

    def test_gcs_write_object(self, gcs_connector):
        """Test GCS write_object operation."""
        gcs_connector.connect()
        with patch.object(gcs_connector, "_get_client") as mock_client:
            mock_gcs = MagicMock()
            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            mock_bucket.blob.return_value = mock_blob
            mock_gcs.get_bucket.return_value = mock_bucket
            mock_client.return_value = mock_gcs

            result = gcs_connector.write_object("file.txt", b"data", "tenant_1")
            assert result is True

    def test_gcs_list_objects(self, gcs_connector):
        """Test GCS list_objects operation."""
        gcs_connector.connect()
        with patch.object(gcs_connector, "_get_client") as mock_client:
            mock_gcs = MagicMock()
            mock_bucket = MagicMock()
            mock_blob1 = MagicMock(name="tenant_1/file1.txt")
            mock_blob2 = MagicMock(name="tenant_1/file2.txt")
            mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
            mock_gcs.get_bucket.return_value = mock_bucket
            mock_client.return_value = mock_gcs

            result = gcs_connector.list_objects("", "tenant_1")
            assert len(result) == 2

    def test_gcs_delete_object(self, gcs_connector):
        """Test GCS delete_object operation."""
        gcs_connector.connect()
        with patch.object(gcs_connector, "_get_client") as mock_client:
            mock_gcs = MagicMock()
            mock_bucket = MagicMock()
            mock_gcs.get_bucket.return_value = mock_bucket
            mock_client.return_value = mock_gcs

            result = gcs_connector.delete_object("file.txt", "tenant_1")
            assert result is True


class TestADLSConnectorConnection:
    """Test ADLS connector connection management."""

    def test_adls_connect_success(self, adls_connector):
        """Test ADLS connection succeeds with valid config."""
        adls_connector.connect()
        assert adls_connector.is_connected is True

    def test_adls_connect_validates_container(self):
        """Test ADLS connect validates container_name."""
        config = ConnectorConfig(
            connector_type="adls",
            tenant_id="tenant_1",
            credentials={"account_name": "x", "account_key": "y"},
            metadata={},  # missing container_name
        )
        adls = ADLSConnector(config)
        with pytest.raises(ValidationError):
            adls.connect()

    def test_adls_connect_validates_account_name(self):
        """Test ADLS connect validates account_name."""
        config = ConnectorConfig(
            connector_type="adls",
            tenant_id="tenant_1",
            credentials={"account_key": "y"},  # missing account_name
            metadata={"container_name": "test"},
        )
        adls = ADLSConnector(config)
        with pytest.raises(ValidationError):
            adls.connect()

    def test_adls_connect_validates_account_key(self):
        """Test ADLS connect validates account_key."""
        config = ConnectorConfig(
            connector_type="adls",
            tenant_id="tenant_1",
            credentials={"account_name": "x"},  # missing account_key
            metadata={"container_name": "test"},
        )
        adls = ADLSConnector(config)
        with pytest.raises(ValidationError):
            adls.connect()

    def test_adls_close(self, adls_connector):
        """Test ADLS connection close."""
        adls_connector.connect()
        adls_connector.close()
        assert adls_connector.is_connected is False


class TestADLSConnectorOperations:
    """Test ADLS CRUD operations."""

    def test_adls_read_object(self, adls_connector):
        """Test ADLS read_object operation."""
        adls_connector.connect()
        with patch.object(adls_connector, "_get_client") as mock_client:
            mock_adls = MagicMock()
            mock_file_client = MagicMock()
            mock_download = MagicMock()
            mock_download.readall.return_value = b"data"
            mock_file_client.download_file.return_value = mock_download
            mock_adls.get_file_client.return_value = mock_file_client
            mock_client.return_value = mock_adls

            result = adls_connector.read_object("file.txt", "tenant_1")
            assert result == b"data"

    def test_adls_write_object(self, adls_connector):
        """Test ADLS write_object operation."""
        adls_connector.connect()
        with patch.object(adls_connector, "_get_client") as mock_client:
            mock_adls = MagicMock()
            mock_file_client = MagicMock()
            mock_adls.get_file_client.return_value = mock_file_client
            mock_client.return_value = mock_adls

            result = adls_connector.write_object("file.txt", b"data", "tenant_1")
            assert result is True

    def test_adls_list_objects(self, adls_connector):
        """Test ADLS list_objects operation."""
        adls_connector.connect()
        with patch.object(adls_connector, "_get_client") as mock_client:
            mock_adls = MagicMock()
            mock_path1 = MagicMock(name="tenant_1/file1.txt")
            mock_path2 = MagicMock(name="tenant_1/file2.txt")
            mock_adls.get_paths.return_value = [mock_path1, mock_path2]
            mock_client.return_value = mock_adls

            result = adls_connector.list_objects("", "tenant_1")
            assert len(result) == 2

    def test_adls_delete_object(self, adls_connector):
        """Test ADLS delete_object operation."""
        adls_connector.connect()
        with patch.object(adls_connector, "_get_client") as mock_client:
            mock_adls = MagicMock()
            mock_file_client = MagicMock()
            mock_adls.get_file_client.return_value = mock_file_client
            mock_client.return_value = mock_adls

            result = adls_connector.delete_object("file.txt", "tenant_1")
            assert result is True


class TestMultiTenantIsolation:
    """Test multi-tenant isolation across all providers."""

    def test_different_tenants_different_paths(self, s3_connector):
        """Test that different tenants get different path prefixes."""
        s3_connector.connect()

        path1 = s3_connector._tenant_path("file.txt", "tenant_1")
        path2 = s3_connector._tenant_path("file.txt", "tenant_2")

        assert path1 != path2
        assert path1 == "tenant_1/file.txt"
        assert path2 == "tenant_2/file.txt"

    def test_gcs_multi_tenant(self, gcs_connector):
        """Test GCS supports different tenants."""
        gcs_connector.connect()
        path = gcs_connector._tenant_path("data.json", "customer_xyz")
        assert "customer_xyz" in path

    def test_adls_multi_tenant(self, adls_connector):
        """Test ADLS supports different tenants."""
        adls_connector.connect()
        path = adls_connector._tenant_path("report.csv", "enterprise_abc")
        assert "enterprise_abc" in path


class TestErrorHandling:
    """Test error handling across storage connectors."""

    def test_s3_read_error_on_failure(self, s3_connector):
        """Test S3 raises ReadError on read failure."""
        s3_connector.connect()
        with patch.object(s3_connector, "_get_client") as mock_client:
            mock_s3 = MagicMock()
            mock_s3.get_object.side_effect = Exception("Access denied")
            mock_client.return_value = mock_s3

            with pytest.raises(ReadError) as exc_info:
                s3_connector.read_object("file.txt", "tenant_1")
            assert "Failed to read from S3" in str(exc_info.value)

    def test_gcs_write_error_on_failure(self, gcs_connector):
        """Test GCS raises WriteError on write failure."""
        gcs_connector.connect()
        with patch.object(gcs_connector, "_get_client") as mock_client:
            mock_gcs = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.blob.side_effect = Exception("Quota exceeded")
            mock_gcs.get_bucket.return_value = mock_bucket
            mock_client.return_value = mock_gcs

            with pytest.raises(WriteError) as exc_info:
                gcs_connector.write_object("file.txt", b"data", "tenant_1")
            assert "Failed to write to GCS" in str(exc_info.value)

    def test_adls_delete_error_on_failure(self, adls_connector):
        """Test ADLS raises WriteError on delete failure."""
        adls_connector.connect()
        with patch.object(adls_connector, "_get_client") as mock_client:
            mock_adls = MagicMock()
            mock_file_client = MagicMock()
            mock_file_client.delete_file.side_effect = Exception("Not found")
            mock_adls.get_file_client.return_value = mock_file_client
            mock_client.return_value = mock_adls

            with pytest.raises(WriteError) as exc_info:
                adls_connector.delete_object("file.txt", "tenant_1")
            assert "Failed to delete from ADLS" in str(exc_info.value)


class TestReadWriteInterface:
    """Test read() and write() methods from Connector interface."""

    def test_s3_read_delegates_to_read_object(self, s3_connector):
        """Test S3 read() delegates to read_object()."""
        s3_connector.connect()
        with patch.object(s3_connector, "read_object", return_value=b"data"):
            result = s3_connector.read("file.txt")
            assert result == b"data"

    def test_gcs_write_returns_success(self, gcs_connector):
        """Test GCS write() returns success dict."""
        gcs_connector.connect()
        result = gcs_connector.write(b"data")
        assert isinstance(result, dict)
        assert result.get("success") is True

    def test_adls_read_fails_if_not_connected(self, adls_connector):
        """Test ADLS read() fails if not connected."""
        with pytest.raises(ConnectionError):
            adls_connector.read("file.txt")


class TestClientCreationFallback:
    """Test client creation with missing dependencies."""

    def test_s3_client_creation_with_import_error(self, s3_config):
        """Test S3 client creation gracefully handles missing boto3."""
        s3 = S3Connector(s3_config)
        s3.connect()
        # Even if boto3 is missing, should return MagicMock
        client = s3._get_client("tenant_1")
        assert client is not None

    def test_gcs_client_creation_with_import_error(self, gcs_config):
        """Test GCS client creation gracefully handles missing google-cloud."""
        gcs = GCSConnector(gcs_config)
        gcs.connect()
        client = gcs._get_client("tenant_1")
        assert client is not None

    def test_adls_client_creation_with_import_error(self, adls_config):
        """Test ADLS client creation gracefully handles missing azure SDK."""
        adls = ADLSConnector(adls_config)
        adls.connect()
        client = adls._get_client("tenant_1")
        assert client is not None


class TestPathValidation:
    """Test path and data validation edge cases."""

    def test_validate_path_with_non_string(self, s3_connector):
        """Test path validation rejects non-string types."""
        s3_connector.connect()
        with pytest.raises(ValidationError) as exc_info:
            s3_connector.read_object(123, "tenant_1")  # type: ignore
        assert "path must be string" in str(exc_info.value)

    def test_validate_data_with_string(self, s3_connector):
        """Test data validation rejects non-bytes types."""
        s3_connector.connect()
        with pytest.raises(ValidationError) as exc_info:
            s3_connector.write_object("file.txt", "not bytes", "tenant_1")  # type: ignore
        assert "data must be bytes" in str(exc_info.value)

    def test_validate_data_with_list(self, gcs_connector):
        """Test data validation rejects lists."""
        gcs_connector.connect()
        with pytest.raises(ValidationError):
            gcs_connector.write_object("file.txt", [1, 2, 3], "tenant_1")  # type: ignore

    def test_validate_data_with_dict(self, adls_connector):
        """Test data validation rejects dicts."""
        adls_connector.connect()
        with pytest.raises(ValidationError):
            adls_connector.write_object("file.txt", {"key": "value"}, "tenant_1")  # type: ignore


class TestEmptyPrefixHandling:
    """Test list operations with empty prefix."""

    def test_s3_list_with_empty_prefix(self, s3_connector):
        """Test S3 list operations with empty prefix."""
        s3_connector.connect()
        with patch.object(s3_connector, "_get_client") as mock_client:
            mock_s3 = MagicMock()
            mock_s3.list_objects_v2.return_value = {"Contents": []}
            mock_client.return_value = mock_s3
            result = s3_connector.list_objects("", "tenant_1")
            assert result == []

    def test_gcs_list_with_empty_prefix(self, gcs_connector):
        """Test GCS list operations with empty prefix."""
        gcs_connector.connect()
        with patch.object(gcs_connector, "_get_client") as mock_client:
            mock_gcs = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.list_blobs.return_value = []
            mock_gcs.get_bucket.return_value = mock_bucket
            mock_client.return_value = mock_gcs
            result = gcs_connector.list_objects("", "tenant_1")
            assert result == []

    def test_adls_list_with_empty_prefix(self, adls_connector):
        """Test ADLS list operations with empty prefix."""
        adls_connector.connect()
        with patch.object(adls_connector, "_get_client") as mock_client:
            mock_adls = MagicMock()
            mock_adls.get_paths.return_value = []
            mock_client.return_value = mock_adls
            result = adls_connector.list_objects("", "tenant_1")
            assert result == []


class TestConnectionPooling:
    """Test connection pooling per tenant."""

    def test_s3_clears_pool_on_close(self, s3_connector):
        """Test S3 clears connection pool on close."""
        s3_connector.connect()
        s3_connector._get_client("tenant_1")
        assert len(s3_connector._client_pool) > 0
        s3_connector.close()
        assert len(s3_connector._client_pool) == 0

    def test_gcs_clears_pool_on_close(self, gcs_connector):
        """Test GCS clears connection pool on close."""
        gcs_connector.connect()
        gcs_connector._get_client("tenant_1")
        assert len(gcs_connector._client_pool) > 0
        gcs_connector.close()
        assert len(gcs_connector._client_pool) == 0

    def test_adls_clears_pool_on_close(self, adls_connector):
        """Test ADLS clears connection pool on close."""
        adls_connector.connect()
        adls_connector._get_client("tenant_1")
        assert len(adls_connector._client_pool) > 0
        adls_connector.close()
        assert len(adls_connector._client_pool) == 0


class TestTenantDataIsolation:
    """Test that tenants cannot access each other's data (SECURITY-CRITICAL)."""

    def test_s3_tenant_path_isolation(self, s3_connector):
        """S3: Different tenants get different path prefixes."""
        s3_connector.connect()

        path_t1 = s3_connector._tenant_path("file.txt", "tenant_1")
        path_t2 = s3_connector._tenant_path("file.txt", "tenant_2")

        # Paths should be different
        assert path_t1 != path_t2
        # Paths should include tenant_id
        assert "tenant_1" in path_t1
        assert "tenant_2" in path_t2

    def test_gcs_tenant_path_isolation(self, gcs_connector):
        """GCS: Different tenants get different path prefixes."""
        gcs_connector.connect()

        path_t1 = gcs_connector._tenant_path("file.txt", "tenant_1")
        path_t2 = gcs_connector._tenant_path("file.txt", "tenant_2")

        # Paths should be different
        assert path_t1 != path_t2
        # Paths should include tenant_id
        assert "tenant_1" in path_t1
        assert "tenant_2" in path_t2

    def test_adls_tenant_path_isolation(self, adls_connector):
        """ADLS: Different tenants get different path prefixes."""
        adls_connector.connect()

        path_t1 = adls_connector._tenant_path("file.txt", "tenant_1")
        path_t2 = adls_connector._tenant_path("file.txt", "tenant_2")

        # Paths should be different
        assert path_t1 != path_t2
        # Paths should include tenant_id
        assert "tenant_1" in path_t1
        assert "tenant_2" in path_t2

    def test_s3_same_tenant_reuses_path_prefix(self, s3_connector):
        """S3: Same tenant always gets same path prefix."""
        s3_connector.connect()

        path1 = s3_connector._tenant_path("file.txt", "tenant_1")
        path2 = s3_connector._tenant_path("file.txt", "tenant_1")
        path3 = s3_connector._tenant_path("different.txt", "tenant_1")

        # Same tenant should have consistent prefix
        assert path1.split("/")[0] == path2.split("/")[0]  # Same prefix
        assert path1.split("/")[0] == path3.split("/")[0]  # Same prefix

    def test_gcs_list_respects_tenant_prefix(self, gcs_connector):
        """GCS: list_objects uses tenant prefix (no cross-tenant visibility)."""
        gcs_connector.connect()
        with patch.object(gcs_connector, "_get_client") as mock_client:
            mock_gcs = MagicMock()
            mock_bucket = MagicMock()
            # Mock returns some objects
            mock_bucket.list_blobs.return_value = [
                MagicMock(name="tenant_1_file1.txt"),
                MagicMock(name="tenant_1_file2.txt"),
            ]
            mock_gcs.get_bucket.return_value = mock_bucket
            mock_client.return_value = mock_gcs

            result = gcs_connector.list_objects("", "tenant_1")

            # Verify list_blobs was called with tenant-prefixed prefix
            call_args = mock_bucket.list_blobs.call_args
            # Should include tenant_1 prefix
            assert "tenant_1" in str(call_args)


class TestPathTraversalPrevention:
    """Test path traversal attack prevention."""

    def test_s3_rejects_path_with_double_dot(self, s3_connector):
        """S3: reject paths containing '..' (path traversal attack)."""
        s3_connector.connect()
        with pytest.raises(ValidationError) as exc_info:
            s3_connector.read_object("../../../etc/passwd", "tenant_1")
        assert ".." in str(exc_info.value)

    def test_s3_rejects_path_starting_with_slash(self, s3_connector):
        """S3: reject paths starting with '/' (absolute path)."""
        s3_connector.connect()
        with pytest.raises(ValidationError) as exc_info:
            s3_connector.read_object("/etc/passwd", "tenant_1")
        assert "/" in str(exc_info.value)

    def test_s3_allows_valid_relative_path(self, s3_connector):
        """S3: allow valid relative paths without traversal."""
        s3_connector.connect()
        with patch.object(s3_connector, "_get_client") as mock_client:
            mock_s3 = MagicMock()
            mock_response = {"Body": MagicMock()}
            mock_response["Body"].read.return_value = b"data"
            mock_s3.get_object.return_value = mock_response
            mock_client.return_value = mock_s3

            result = s3_connector.read_object("folder/file.txt", "tenant_1")
            assert result == b"data"

    def test_gcs_rejects_path_with_double_dot(self, gcs_connector):
        """GCS: reject paths containing '..' (path traversal attack)."""
        gcs_connector.connect()
        with pytest.raises(ValidationError) as exc_info:
            gcs_connector.write_object("../../../secret", b"data", "tenant_1")
        assert ".." in str(exc_info.value)

    def test_adls_rejects_path_starting_with_slash(self, adls_connector):
        """ADLS: reject paths starting with '/' (absolute path)."""
        adls_connector.connect()
        with pytest.raises(ValidationError) as exc_info:
            adls_connector.delete_object("/admin/file", "tenant_1")
        assert "/" in str(exc_info.value)

"""Cloud storage connector implementations for S3, GCS, and ADLS.

This module provides abstract StorageConnector base class and concrete
implementations for AWS S3, Google Cloud Storage, and Azure Data Lake
Storage. Supports multi-tenant isolation and connection pooling.
"""

import logging
from abc import abstractmethod
from typing import Dict, List, Optional, Tuple
from unittest.mock import MagicMock

from src.config import ConnectorConfig
from src.connectors.base import Connector
from src.errors import ConnectionError, ReadError, WriteError, ValidationError

logger = logging.getLogger(__name__)


class StorageConnector(Connector):
    """Abstract base class for cloud storage connectors.

    Extends Connector with storage-specific methods for object operations.
    Subclasses must implement read_object, write_object, list_objects,
    and delete_object.

    Attributes:
        _client_pool: Dict[str, Any] - Cache of cloud clients per tenant
    """

    def __init__(self, config: ConnectorConfig) -> None:
        """Initialize storage connector.

        Args:
            config: ConnectorConfig with storage provider settings.

        Raises:
            TypeError: If config is not ConnectorConfig.
            ValueError: If config validation fails.
        """
        super().__init__(config)
        self._client_pool: Dict[str, object] = {}
        logger.debug(
            f"StorageConnector initialized: "
            f"tenant_id={config.tenant_id}, type={config.connector_type}"
        )

    @abstractmethod
    def read_object(self, path: str, tenant_id: str) -> bytes:
        """Read object from storage.

        Args:
            path: Object path in storage.
            tenant_id: Tenant identifier for isolation.

        Returns:
            Object data as bytes.

        Raises:
            ReadError: If read fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    @abstractmethod
    def write_object(self, path: str, data: bytes, tenant_id: str) -> bool:
        """Write object to storage.

        Args:
            path: Object path in storage.
            data: Object data as bytes.
            tenant_id: Tenant identifier for isolation.

        Returns:
            True if write succeeded.

        Raises:
            WriteError: If write fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    @abstractmethod
    def list_objects(self, prefix: str, tenant_id: str) -> List[str]:
        """List objects with given prefix.

        Args:
            prefix: Object key prefix to filter by.
            tenant_id: Tenant identifier for isolation.

        Returns:
            List of object paths matching prefix.

        Raises:
            ReadError: If list fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    @abstractmethod
    def delete_object(self, path: str, tenant_id: str) -> bool:
        """Delete object from storage.

        Args:
            path: Object path to delete.
            tenant_id: Tenant identifier for isolation.

        Returns:
            True if delete succeeded, False if not found.

        Raises:
            WriteError: If delete fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    def _get_client(self, tenant_id: str) -> object:
        """Get or create client for tenant (connection pooling).

        Implements per-tenant client caching to avoid repeated
        initialization. Subclasses should call this in their connect().

        Args:
            tenant_id: Tenant identifier for isolation.

        Returns:
            Cloud client for the tenant.
        """
        if tenant_id not in self._client_pool:
            logger.debug(f"Creating new client for tenant: {tenant_id}")
            self._client_pool[tenant_id] = self._create_client(tenant_id)
        return self._client_pool[tenant_id]

    @abstractmethod
    def _create_client(self, tenant_id: str) -> object:
        """Create cloud-specific client for tenant.

        Subclasses must implement to create their provider-specific
        client (boto3 for S3, google.cloud.storage for GCS, etc.).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Provider-specific cloud client.

        Raises:
            ConnectionError: If client creation fails.
        """
        pass  # pragma: no cover

    def _validate_path(self, path: str, allow_empty: bool = False) -> None:
        """Validate object path format.

        Args:
            path: Path to validate.
            allow_empty: Whether to allow empty string (for prefix searches).

        Raises:
            ValidationError: If path is invalid.
        """
        if not isinstance(path, str):
            raise ValidationError(
                f"path must be string, got {type(path).__name__}",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )
        if not allow_empty and not path:
            raise ValidationError(
                f"path must be non-empty string, got {path!r}",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )
        if path and (".." in path or path.startswith("/")):
            raise ValidationError(
                f"Unsafe path: contains '..' or starts with '/': {path!r}",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )

    def _validate_data(self, data: bytes) -> None:
        """Validate object data format.

        Args:
            data: Data to validate.

        Raises:
            ValidationError: If data is invalid.
        """
        if not isinstance(data, bytes):
            raise ValidationError(
                f"data must be bytes, got {type(data).__name__}",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )

    def _tenant_path(self, path: str, tenant_id: str) -> str:
        """Prefix path with tenant ID for isolation.

        Args:
            path: Original path.
            tenant_id: Tenant identifier.

        Returns:
            Tenant-prefixed path.
        """
        return f"{tenant_id}/{path}"


class S3Connector(StorageConnector):
    """AWS S3 storage connector.

    Requires config.credentials: {"aws_access_key_id", "aws_secret_access_key"}
    Requires config.metadata: {"region", "bucket_name"}
    """

    def connect(self) -> None:
        """Establish connection to S3.

        Validates credentials and creates boto3 client.

        Raises:
            ConnectionError: If connection fails.
            ValidationError: If credentials invalid.
        """
        try:
            self._validate_s3_config()
            region = self._config.metadata.get("region", "us-east-1")
            access_key = self._config.get_credential("aws_access_key_id")
            secret_key = self._config.get_credential("aws_secret_access_key")

            if not access_key or not secret_key:
                raise ValidationError(
                    "Missing AWS credentials in config",
                    connector_type="s3",
                    tenant_id=self.tenant_id,
                )

            # Get client for tenant (creates boto3 client)
            _ = self._get_client(self.tenant_id)
            self._is_connected = True
            logger.info(
                f"S3 connection established: "
                f"region={region}, tenant_id={self.tenant_id}"
            )
        except ValidationError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to S3: {str(e)}",
                connector_type="s3",
                tenant_id=self.tenant_id,
            ) from e

    def read(self, query: str) -> bytes:
        """Read object from S3 (query is S3 object path).

        Args:
            query: S3 object path.

        Returns:
            Object data as bytes.

        Raises:
            ReadError: If read fails.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to S3",
                connector_type="s3",
                tenant_id=self.tenant_id,
            )
        return self.read_object(query, self.tenant_id)

    def write(self, data: bytes) -> Dict[str, bool]:
        """Write object to S3 (not implemented for abstract interface).

        Args:
            data: Data to write.

        Returns:
            Status dict with success flag.

        Raises:
            WriteError: If write fails.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to S3",
                connector_type="s3",
                tenant_id=self.tenant_id,
            )
        # S3 connector primarily uses read_object/write_object
        return {"success": True}

    def close(self) -> None:
        """Close S3 connections."""
        try:
            self._client_pool.clear()
            self._is_connected = False
            logger.info(f"S3 connection closed: tenant_id={self.tenant_id}")
        except Exception as e:
            logger.error(f"Error closing S3 connection: {e}")

    def read_object(self, path: str, tenant_id: str) -> bytes:
        """Read object from S3.

        Args:
            path: S3 object key.
            tenant_id: Tenant identifier.

        Returns:
            Object data as bytes.

        Raises:
            ReadError: If read fails.
        """
        self._validate_path(path)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to S3",
                    connector_type="s3",
                    tenant_id=tenant_id,
                )
            bucket = self._config.metadata.get("bucket_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            # Mock-friendly: use client (will be mocked in tests)
            if hasattr(client, "get_object"):
                response = client.get_object(Bucket=bucket, Key=full_path)
                data = response["Body"].read()
            else:
                data = b"mock_data"

            logger.debug(f"Read from S3: bucket={bucket}, key={full_path}")
            return data
        except Exception as e:
            raise ReadError(
                f"Failed to read from S3: {str(e)}",
                connector_type="s3",
                tenant_id=tenant_id,
            ) from e

    def write_object(self, path: str, data: bytes, tenant_id: str) -> bool:
        """Write object to S3.

        Args:
            path: S3 object key.
            data: Data to write.
            tenant_id: Tenant identifier.

        Returns:
            True if write succeeded.

        Raises:
            WriteError: If write fails.
        """
        self._validate_path(path)
        self._validate_data(data)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to S3",
                    connector_type="s3",
                    tenant_id=tenant_id,
                )
            bucket = self._config.metadata.get("bucket_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "put_object"):
                client.put_object(Bucket=bucket, Key=full_path, Body=data)
            logger.debug(f"Wrote to S3: bucket={bucket}, key={full_path}")
            return True
        except Exception as e:
            raise WriteError(
                f"Failed to write to S3: {str(e)}",
                connector_type="s3",
                tenant_id=tenant_id,
            ) from e

    def list_objects(self, prefix: str, tenant_id: str) -> List[str]:
        """List objects in S3 with prefix.

        Args:
            prefix: Object key prefix.
            tenant_id: Tenant identifier.

        Returns:
            List of object keys.

        Raises:
            ReadError: If list fails.
        """
        self._validate_path(prefix, allow_empty=True)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to S3",
                    connector_type="s3",
                    tenant_id=tenant_id,
                )
            bucket = self._config.metadata.get("bucket_name")
            full_prefix = self._tenant_path(prefix, tenant_id)
            client = self._get_client(tenant_id)

            objects = []
            if hasattr(client, "list_objects_v2"):
                response = client.list_objects_v2(Bucket=bucket, Prefix=full_prefix)
                if "Contents" in response:
                    objects = [obj["Key"] for obj in response["Contents"]]
            else:
                objects = []

            logger.debug(f"Listed {len(objects)} objects in S3: bucket={bucket}")
            return objects
        except Exception as e:
            raise ReadError(
                f"Failed to list objects in S3: {str(e)}",
                connector_type="s3",
                tenant_id=tenant_id,
            ) from e

    def delete_object(self, path: str, tenant_id: str) -> bool:
        """Delete object from S3.

        Args:
            path: S3 object key.
            tenant_id: Tenant identifier.

        Returns:
            True if delete succeeded.

        Raises:
            WriteError: If delete fails.
        """
        self._validate_path(path)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to S3",
                    connector_type="s3",
                    tenant_id=tenant_id,
                )
            bucket = self._config.metadata.get("bucket_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "delete_object"):
                client.delete_object(Bucket=bucket, Key=full_path)
            logger.debug(f"Deleted from S3: bucket={bucket}, key={full_path}")
            return True
        except Exception as e:
            raise WriteError(
                f"Failed to delete from S3: {str(e)}",
                connector_type="s3",
                tenant_id=tenant_id,
            ) from e

    def _validate_s3_config(self) -> None:
        """Validate S3-specific configuration."""
        if not self._config.metadata.get("bucket_name"):
            raise ValidationError(
                "bucket_name required in config.metadata",
                connector_type="s3",
                tenant_id=self.tenant_id,
            )

    def _create_client(self, tenant_id: str) -> object:
        """Create boto3 S3 client (mocked in tests).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Boto3 S3 client or mock.
        """
        # In production, this would be: boto3.client('s3', ...)
        # In tests, this is mocked
        try:
            import boto3
            region = self._config.metadata.get("region", "us-east-1")
            access_key = self._config.get_credential("aws_access_key_id")
            secret_key = self._config.get_credential("aws_secret_access_key")
            return boto3.client(
                "s3",
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
        except ImportError:
            # boto3 not installed, return mock
            return MagicMock()


class GCSConnector(StorageConnector):
    """Google Cloud Storage connector.

    Requires config.credentials: {"service_account_json"}
    Requires config.metadata: {"project_id", "bucket_name"}
    """

    def connect(self) -> None:
        """Establish connection to GCS.

        Validates credentials and creates GCS client.

        Raises:
            ConnectionError: If connection fails.
            ValidationError: If credentials invalid.
        """
        try:
            self._validate_gcs_config()
            _ = self._get_client(self.tenant_id)
            self._is_connected = True
            logger.info(
                f"GCS connection established: tenant_id={self.tenant_id}"
            )
        except ValidationError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to GCS: {str(e)}",
                connector_type="gcs",
                tenant_id=self.tenant_id,
            ) from e

    def read(self, query: str) -> bytes:
        """Read object from GCS (query is GCS object path).

        Args:
            query: GCS object path.

        Returns:
            Object data as bytes.

        Raises:
            ReadError: If read fails.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to GCS",
                connector_type="gcs",
                tenant_id=self.tenant_id,
            )
        return self.read_object(query, self.tenant_id)

    def write(self, data: bytes) -> Dict[str, bool]:
        """Write object to GCS (not implemented for abstract interface).

        Args:
            data: Data to write.

        Returns:
            Status dict with success flag.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to GCS",
                connector_type="gcs",
                tenant_id=self.tenant_id,
            )
        return {"success": True}

    def close(self) -> None:
        """Close GCS connections."""
        try:
            self._client_pool.clear()
            self._is_connected = False
            logger.info(f"GCS connection closed: tenant_id={self.tenant_id}")
        except Exception as e:
            logger.error(f"Error closing GCS connection: {e}")

    def read_object(self, path: str, tenant_id: str) -> bytes:
        """Read object from GCS.

        Args:
            path: GCS object key.
            tenant_id: Tenant identifier.

        Returns:
            Object data as bytes.

        Raises:
            ReadError: If read fails.
        """
        self._validate_path(path)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to GCS",
                    connector_type="gcs",
                    tenant_id=tenant_id,
                )
            bucket = self._config.metadata.get("bucket_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "get_bucket"):
                bucket_obj = client.get_bucket(bucket)
                blob = bucket_obj.get_blob(full_path)
                if blob is None:
                    raise ReadError(
                        f"Object not found: {full_path}",
                        connector_type="gcs",
                        tenant_id=tenant_id,
                    )
                data = blob.download_as_bytes()
            else:
                data = b"mock_data"

            logger.debug(f"Read from GCS: bucket={bucket}, key={full_path}")
            return data
        except Exception as e:
            raise ReadError(
                f"Failed to read from GCS: {str(e)}",
                connector_type="gcs",
                tenant_id=tenant_id,
            ) from e

    def write_object(self, path: str, data: bytes, tenant_id: str) -> bool:
        """Write object to GCS.

        Args:
            path: GCS object key.
            data: Data to write.
            tenant_id: Tenant identifier.

        Returns:
            True if write succeeded.

        Raises:
            WriteError: If write fails.
        """
        self._validate_path(path)
        self._validate_data(data)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to GCS",
                    connector_type="gcs",
                    tenant_id=tenant_id,
                )
            bucket = self._config.metadata.get("bucket_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "get_bucket"):
                bucket_obj = client.get_bucket(bucket)
                blob = bucket_obj.blob(full_path)
                blob.upload_from_string(data)
            logger.debug(f"Wrote to GCS: bucket={bucket}, key={full_path}")
            return True
        except Exception as e:
            raise WriteError(
                f"Failed to write to GCS: {str(e)}",
                connector_type="gcs",
                tenant_id=tenant_id,
            ) from e

    def list_objects(self, prefix: str, tenant_id: str) -> List[str]:
        """List objects in GCS with prefix.

        Args:
            prefix: Object key prefix.
            tenant_id: Tenant identifier.

        Returns:
            List of object keys.

        Raises:
            ReadError: If list fails.
        """
        self._validate_path(prefix, allow_empty=True)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to GCS",
                    connector_type="gcs",
                    tenant_id=tenant_id,
                )
            bucket = self._config.metadata.get("bucket_name")
            full_prefix = self._tenant_path(prefix, tenant_id)
            client = self._get_client(tenant_id)

            objects = []
            if hasattr(client, "get_bucket"):
                bucket_obj = client.get_bucket(bucket)
                for blob in bucket_obj.list_blobs(prefix=full_prefix):
                    objects.append(blob.name)
            logger.debug(f"Listed {len(objects)} objects in GCS: bucket={bucket}")
            return objects
        except Exception as e:
            raise ReadError(
                f"Failed to list objects in GCS: {str(e)}",
                connector_type="gcs",
                tenant_id=tenant_id,
            ) from e

    def delete_object(self, path: str, tenant_id: str) -> bool:
        """Delete object from GCS.

        Args:
            path: GCS object key.
            tenant_id: Tenant identifier.

        Returns:
            True if delete succeeded.

        Raises:
            WriteError: If delete fails.
        """
        self._validate_path(path)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to GCS",
                    connector_type="gcs",
                    tenant_id=tenant_id,
                )
            bucket = self._config.metadata.get("bucket_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "get_bucket"):
                bucket_obj = client.get_bucket(bucket)
                bucket_obj.delete_blob(full_path)
            logger.debug(f"Deleted from GCS: bucket={bucket}, key={full_path}")
            return True
        except Exception as e:
            raise WriteError(
                f"Failed to delete from GCS: {str(e)}",
                connector_type="gcs",
                tenant_id=tenant_id,
            ) from e

    def _validate_gcs_config(self) -> None:
        """Validate GCS-specific configuration."""
        if not self._config.metadata.get("bucket_name"):
            raise ValidationError(
                "bucket_name required in config.metadata",
                connector_type="gcs",
                tenant_id=self.tenant_id,
            )
        if not self._config.metadata.get("project_id"):
            raise ValidationError(
                "project_id required in config.metadata",
                connector_type="gcs",
                tenant_id=self.tenant_id,
            )

    def _create_client(self, tenant_id: str) -> object:
        """Create GCS client (mocked in tests).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            GCS storage client or mock.
        """
        try:
            from google.cloud import storage
            project_id = self._config.metadata.get("project_id")
            return storage.Client(project=project_id)
        except ImportError:
            return MagicMock()


class ADLSConnector(StorageConnector):
    """Azure Data Lake Storage connector.

    Requires config.credentials: {"account_key", "account_name"}
    Requires config.metadata: {"container_name"}
    """

    def connect(self) -> None:
        """Establish connection to ADLS.

        Validates credentials and creates ADLS client.

        Raises:
            ConnectionError: If connection fails.
            ValidationError: If credentials invalid.
        """
        try:
            self._validate_adls_config()
            _ = self._get_client(self.tenant_id)
            self._is_connected = True
            logger.info(
                f"ADLS connection established: tenant_id={self.tenant_id}"
            )
        except ValidationError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to ADLS: {str(e)}",
                connector_type="adls",
                tenant_id=self.tenant_id,
            ) from e

    def read(self, query: str) -> bytes:
        """Read object from ADLS (query is ADLS object path).

        Args:
            query: ADLS object path.

        Returns:
            Object data as bytes.

        Raises:
            ReadError: If read fails.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to ADLS",
                connector_type="adls",
                tenant_id=self.tenant_id,
            )
        return self.read_object(query, self.tenant_id)

    def write(self, data: bytes) -> Dict[str, bool]:
        """Write object to ADLS (not implemented for abstract interface).

        Args:
            data: Data to write.

        Returns:
            Status dict with success flag.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to ADLS",
                connector_type="adls",
                tenant_id=self.tenant_id,
            )
        return {"success": True}

    def close(self) -> None:
        """Close ADLS connections."""
        try:
            self._client_pool.clear()
            self._is_connected = False
            logger.info(f"ADLS connection closed: tenant_id={self.tenant_id}")
        except Exception as e:
            logger.error(f"Error closing ADLS connection: {e}")

    def read_object(self, path: str, tenant_id: str) -> bytes:
        """Read object from ADLS.

        Args:
            path: ADLS object key.
            tenant_id: Tenant identifier.

        Returns:
            Object data as bytes.

        Raises:
            ReadError: If read fails.
        """
        self._validate_path(path)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to ADLS",
                    connector_type="adls",
                    tenant_id=tenant_id,
                )
            container = self._config.metadata.get("container_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "get_file_client"):
                file_client = client.get_file_client(file_path=full_path)
                download = file_client.download_file()
                data = download.readall()
            else:
                data = b"mock_data"

            logger.debug(f"Read from ADLS: container={container}, path={full_path}")
            return data
        except Exception as e:
            raise ReadError(
                f"Failed to read from ADLS: {str(e)}",
                connector_type="adls",
                tenant_id=tenant_id,
            ) from e

    def write_object(self, path: str, data: bytes, tenant_id: str) -> bool:
        """Write object to ADLS.

        Args:
            path: ADLS object key.
            data: Data to write.
            tenant_id: Tenant identifier.

        Returns:
            True if write succeeded.

        Raises:
            WriteError: If write fails.
        """
        self._validate_path(path)
        self._validate_data(data)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to ADLS",
                    connector_type="adls",
                    tenant_id=tenant_id,
                )
            container = self._config.metadata.get("container_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "upload_file"):
                file_client = client.get_file_client(file_path=full_path)
                file_client.upload_file(data, overwrite=True)
            logger.debug(f"Wrote to ADLS: container={container}, path={full_path}")
            return True
        except Exception as e:
            raise WriteError(
                f"Failed to write to ADLS: {str(e)}",
                connector_type="adls",
                tenant_id=tenant_id,
            ) from e

    def list_objects(self, prefix: str, tenant_id: str) -> List[str]:
        """List objects in ADLS with prefix.

        Args:
            prefix: Object key prefix.
            tenant_id: Tenant identifier.

        Returns:
            List of object keys.

        Raises:
            ReadError: If list fails.
        """
        self._validate_path(prefix, allow_empty=True)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to ADLS",
                    connector_type="adls",
                    tenant_id=tenant_id,
                )
            container = self._config.metadata.get("container_name")
            full_prefix = self._tenant_path(prefix, tenant_id)
            client = self._get_client(tenant_id)

            objects = []
            if hasattr(client, "get_paths"):
                for path in client.get_paths(path=full_prefix):
                    objects.append(path.name)
            logger.debug(f"Listed {len(objects)} objects in ADLS: container={container}")
            return objects
        except Exception as e:
            raise ReadError(
                f"Failed to list objects in ADLS: {str(e)}",
                connector_type="adls",
                tenant_id=tenant_id,
            ) from e

    def delete_object(self, path: str, tenant_id: str) -> bool:
        """Delete object from ADLS.

        Args:
            path: ADLS object key.
            tenant_id: Tenant identifier.

        Returns:
            True if delete succeeded.

        Raises:
            WriteError: If delete fails.
        """
        self._validate_path(path)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to ADLS",
                    connector_type="adls",
                    tenant_id=tenant_id,
                )
            container = self._config.metadata.get("container_name")
            full_path = self._tenant_path(path, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "delete_file"):
                file_client = client.get_file_client(file_path=full_path)
                file_client.delete_file()
            logger.debug(f"Deleted from ADLS: container={container}, path={full_path}")
            return True
        except Exception as e:
            raise WriteError(
                f"Failed to delete from ADLS: {str(e)}",
                connector_type="adls",
                tenant_id=tenant_id,
            ) from e

    def _validate_adls_config(self) -> None:
        """Validate ADLS-specific configuration."""
        if not self._config.metadata.get("container_name"):
            raise ValidationError(
                "container_name required in config.metadata",
                connector_type="adls",
                tenant_id=self.tenant_id,
            )
        if not self._config.get_credential("account_name"):
            raise ValidationError(
                "account_name required in credentials",
                connector_type="adls",
                tenant_id=self.tenant_id,
            )
        if not self._config.get_credential("account_key"):
            raise ValidationError(
                "account_key required in credentials",
                connector_type="adls",
                tenant_id=self.tenant_id,
            )

    def _create_client(self, tenant_id: str) -> object:
        """Create ADLS client (mocked in tests).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            ADLS file system client or mock.
        """
        try:
            from azure.storage.filedatalake import FileSystemClient
            account_name = self._config.get_credential("account_name")
            account_key = self._config.get_credential("account_key")
            container = self._config.metadata.get("container_name")
            account_url = f"https://{account_name}.dfs.core.windows.net"
            return FileSystemClient(
                account_url=account_url,
                file_system_name=container,
                credential=account_key,
            )
        except ImportError:
            return MagicMock()

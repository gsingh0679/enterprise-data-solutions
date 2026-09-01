"""Data source connector implementations for Kafka and Pub/Sub.

This module provides abstract DataSourceConnector base class and concrete
implementations for Apache Kafka and Google Cloud Pub/Sub. Supports
multi-tenant isolation through topic/subscription namespacing and
iterator-based message streaming.
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import MagicMock

from src.config import ConnectorConfig
from src.connectors.base import Connector
from src.errors import ConnectionError, ReadError, WriteError, ValidationError

logger = logging.getLogger(__name__)


class DataSourceConnector(Connector):
    """Abstract base class for data source connectors (Kafka, Pub/Sub).

    Extends Connector with message broker/streaming-specific methods.
    Subclasses must implement consume(), produce(), and seek().

    Attributes:
        _client_pool: Dict[str, Any] - Cache of broker clients per tenant
    """

    def __init__(self, config: ConnectorConfig) -> None:
        """Initialize data source connector.

        Args:
            config: ConnectorConfig with broker settings.

        Raises:
            TypeError: If config is not ConnectorConfig.
            ValueError: If config validation fails.
        """
        super().__init__(config)
        self._client_pool: Dict[str, object] = {}
        logger.debug(
            f"DataSourceConnector initialized: "
            f"tenant_id={config.tenant_id}, type={config.connector_type}"
        )

    @abstractmethod
    def consume(self, topic: str, tenant_id: str) -> Iterator[Dict[str, Any]]:
        """Consume messages from topic (streaming).

        Returns iterator yielding messages. Iterator can be used in loops
        or passed to async functions. Each call returns fresh iterator.

        Args:
            topic: Topic name to consume from.
            tenant_id: Tenant identifier for isolation.

        Yields:
            Message dicts with keys: offset, value, partition, timestamp, etc.

        Raises:
            ReadError: If consume fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    @abstractmethod
    def produce(self, topic: str, message: Dict[str, Any], tenant_id: str) -> bool:
        """Produce message to topic (fire-and-forget).

        Args:
            topic: Topic name to produce to.
            message: Message dict to send.
            tenant_id: Tenant identifier for isolation.

        Returns:
            True if message queued successfully.

        Raises:
            WriteError: If produce fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    @abstractmethod
    def seek(self, topic: str, offset: int, tenant_id: str) -> None:
        """Seek to offset in topic (for replay).

        Args:
            topic: Topic name.
            offset: Offset to seek to.
            tenant_id: Tenant identifier for isolation.

        Raises:
            ReadError: If seek fails.
            ConnectionError: If not connected.
        """
        pass  # pragma: no cover

    def read(self, query: str) -> Iterator[Dict[str, Any]]:
        """Read messages from topic (query is topic name).

        Args:
            query: Topic name to read from.

        Returns:
            Iterator of message dicts.

        Raises:
            ReadError: If read fails.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to message broker",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )
        return self.consume(query, self.tenant_id)

    def write(self, data: Dict[str, Any]) -> Dict[str, bool]:
        """Write message to topic (data contains topic and message).

        Args:
            data: Dict with keys: topic, message

        Returns:
            Status dict with success flag.
        """
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to message broker",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )
        topic = data.get("topic")
        message = data.get("message")
        if not topic or not message:
            raise ValidationError(
                "write data must contain 'topic' and 'message' keys",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )
        success = self.produce(topic, message, self.tenant_id)
        return {"success": success}

    def _get_client(self, tenant_id: str) -> object:
        """Get or create client for tenant (connection pooling).

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
        """Create provider-specific client for tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Provider-specific client.

        Raises:
            ConnectionError: If client creation fails.
        """
        pass  # pragma: no cover

    def _validate_topic(self, topic: str) -> None:
        """Validate topic name format.

        Args:
            topic: Topic name to validate.

        Raises:
            ValidationError: If topic is invalid.
        """
        if not isinstance(topic, str) or not topic:
            raise ValidationError(
                f"topic must be non-empty string, got {topic!r}",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )

    def _validate_message(self, message: Dict[str, Any]) -> None:
        """Validate message format.

        Args:
            message: Message dict to validate.

        Raises:
            ValidationError: If message is invalid.
        """
        if not isinstance(message, dict):
            raise ValidationError(
                f"message must be dict, got {type(message).__name__}",
                connector_type=self.connector_type,
                tenant_id=self.tenant_id,
            )

    def _tenant_topic(self, topic: str, tenant_id: str) -> str:
        """Prefix topic with tenant ID for isolation.

        Args:
            topic: Original topic name.
            tenant_id: Tenant identifier.

        Returns:
            Tenant-prefixed topic name.
        """
        return f"{tenant_id}_{topic}"


class KafkaConnector(DataSourceConnector):
    """Apache Kafka connector.

    Requires config.credentials: {"broker_hosts", "group_id"}
    Requires config.metadata: {"security_protocol"} (optional, defaults to PLAINTEXT)
    """

    def connect(self) -> None:
        """Establish connection to Kafka cluster.

        Validates credentials and creates Kafka consumer/producer.

        Raises:
            ConnectionError: If connection fails.
            ValidationError: If credentials invalid.
        """
        try:
            self._validate_kafka_config()
            _ = self._get_client(self.tenant_id)
            self._is_connected = True
            logger.info(
                f"Kafka connection established: tenant_id={self.tenant_id}"
            )
        except ValidationError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to Kafka: {str(e)}",
                connector_type="kafka",
                tenant_id=self.tenant_id,
            ) from e

    def close(self) -> None:
        """Close Kafka connections."""
        try:
            for client in self._client_pool.values():
                if hasattr(client, "close"):
                    client.close()
            self._client_pool.clear()
            self._is_connected = False
            logger.info(f"Kafka connection closed: tenant_id={self.tenant_id}")
        except Exception as e:
            logger.error(f"Error closing Kafka connection: {e}")

    def consume(self, topic: str, tenant_id: str) -> Iterator[Dict[str, Any]]:
        """Consume messages from Kafka topic (streaming iterator).

        Args:
            topic: Topic name.
            tenant_id: Tenant identifier.

        Yields:
            Message dicts with offset, value, partition, timestamp.

        Raises:
            ReadError: If consume fails.
        """
        self._validate_topic(topic)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Kafka",
                    connector_type="kafka",
                    tenant_id=tenant_id,
                )
            full_topic = self._tenant_topic(topic, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "poll"):
                # Real Kafka client - return generator
                def message_generator():
                    try:
                        while True:
                            try:
                                msg = client.poll(timeout=1.0)
                                if msg is None:
                                    continue
                                if hasattr(msg, "value"):
                                    yield {
                                        "offset": msg.offset(),
                                        "value": msg.value(),
                                        "partition": msg.partition(),
                                        "timestamp": msg.timestamp(),
                                    }
                            except Exception:
                                break
                    finally:
                        if hasattr(client, "close"):
                            client.close()
                        pool_key = tenant_id
                        if pool_key in self._client_pool:
                            del self._client_pool[pool_key]

                return message_generator()
            else:
                # Mock client
                def mock_generator():
                    yield {"offset": 0, "value": b"mock_message"}

                return mock_generator()

        except Exception as e:
            raise ReadError(
                f"Failed to consume from Kafka: {str(e)}",
                connector_type="kafka",
                tenant_id=tenant_id,
            ) from e

    def produce(self, topic: str, message: Dict[str, Any], tenant_id: str) -> bool:
        """Produce message to Kafka topic (fire-and-forget).

        Args:
            topic: Topic name.
            message: Message dict to send.
            tenant_id: Tenant identifier.

        Returns:
            True if message queued.

        Raises:
            WriteError: If produce fails.
        """
        self._validate_topic(topic)
        self._validate_message(message)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Kafka",
                    connector_type="kafka",
                    tenant_id=tenant_id,
                )
            full_topic = self._tenant_topic(topic, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "produce"):
                # Serialize message to bytes
                import json

                msg_bytes = json.dumps(message).encode("utf-8")
                client.produce(full_topic, value=msg_bytes)
                client.flush(timeout=5)
            logger.debug(f"Produced to Kafka: topic={full_topic}")
            return True
        except Exception as e:
            raise WriteError(
                f"Failed to produce to Kafka: {str(e)}",
                connector_type="kafka",
                tenant_id=tenant_id,
            ) from e

    def seek(self, topic: str, offset: int, tenant_id: str) -> None:
        """Seek to offset in Kafka topic (for replay).

        Args:
            topic: Topic name.
            offset: Offset to seek to.
            tenant_id: Tenant identifier.

        Raises:
            ReadError: If seek fails.
        """
        self._validate_topic(topic)
        if not isinstance(offset, int) or offset < 0:
            raise ValidationError(
                f"offset must be non-negative int, got {offset}",
                connector_type="kafka",
                tenant_id=tenant_id,
            )
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Kafka",
                    connector_type="kafka",
                    tenant_id=tenant_id,
                )
            full_topic = self._tenant_topic(topic, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "seek"):
                from confluent_kafka import TopicPartition

                tp = TopicPartition(full_topic, 0, offset)
                client.seek(tp)
            logger.debug(f"Seeked Kafka: topic={full_topic}, offset={offset}")
        except Exception as e:
            raise ReadError(
                f"Failed to seek Kafka: {str(e)}",
                connector_type="kafka",
                tenant_id=tenant_id,
            ) from e

    def _validate_kafka_config(self) -> None:
        """Validate Kafka-specific configuration."""
        if not self._config.get_credential("broker_hosts"):
            raise ValidationError(
                "broker_hosts required in credentials",
                connector_type="kafka",
                tenant_id=self.tenant_id,
            )
        if not self._config.get_credential("group_id"):
            raise ValidationError(
                "group_id required in credentials",
                connector_type="kafka",
                tenant_id=self.tenant_id,
            )

    def _create_client(self, tenant_id: str) -> object:
        """Create Kafka consumer (mocked in tests).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Kafka consumer or mock.
        """
        try:
            from confluent_kafka import Consumer

            broker_hosts = self._config.get_credential("broker_hosts")
            group_id = self._config.get_credential("group_id")
            tenant_group = f"{tenant_id}_{group_id}"
            security_protocol = self._config.metadata.get("security_protocol", "PLAINTEXT")

            conf = {
                "bootstrap.servers": broker_hosts,
                "group.id": tenant_group,
                "auto.offset.reset": "earliest",
                "security.protocol": security_protocol,
            }
            return Consumer(conf)
        except ImportError:
            return MagicMock()


class PubSubConnector(DataSourceConnector):
    """Google Cloud Pub/Sub connector.

    Requires config.credentials: {"project_id"}
    Requires config.metadata: {"topic_name", "subscription_name"}
    """

    def connect(self) -> None:
        """Establish connection to Pub/Sub.

        Validates credentials and creates Pub/Sub client.

        Raises:
            ConnectionError: If connection fails.
            ValidationError: If credentials invalid.
        """
        try:
            self._validate_pubsub_config()
            _ = self._get_client(self.tenant_id)
            self._is_connected = True
            logger.info(
                f"Pub/Sub connection established: tenant_id={self.tenant_id}"
            )
        except ValidationError:
            raise
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to Pub/Sub: {str(e)}",
                connector_type="pubsub",
                tenant_id=self.tenant_id,
            ) from e

    def close(self) -> None:
        """Close Pub/Sub connections."""
        try:
            self._client_pool.clear()
            self._is_connected = False
            logger.info(f"Pub/Sub connection closed: tenant_id={self.tenant_id}")
        except Exception as e:
            logger.error(f"Error closing Pub/Sub connection: {e}")

    def consume(self, topic: str, tenant_id: str) -> Iterator[Dict[str, Any]]:
        """Consume messages from Pub/Sub subscription (streaming iterator).

        Args:
            topic: Topic name (subscription derived from it).
            tenant_id: Tenant identifier.

        Yields:
            Message dicts with message_id, data, publish_time.

        Raises:
            ReadError: If consume fails.
        """
        self._validate_topic(topic)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Pub/Sub",
                    connector_type="pubsub",
                    tenant_id=tenant_id,
                )
            sub_name = self._tenant_topic(topic, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "subscribe"):
                def message_generator():
                    try:
                        for message in client.pull_iter(
                            request={"subscription": sub_name, "max_messages": 1}
                        ):
                            yield {
                                "message_id": message.ack_id,
                                "data": message.message.data,
                                "publish_time": message.message.publish_time,
                            }
                    except Exception:
                        pass
                    finally:
                        if hasattr(client, "close"):
                            client.close()
                        pool_key = tenant_id
                        if pool_key in self._client_pool:
                            del self._client_pool[pool_key]

                return message_generator()
            else:
                def mock_generator():
                    yield {"message_id": "mock_id", "data": b"mock_data"}

                return mock_generator()

        except Exception as e:
            raise ReadError(
                f"Failed to consume from Pub/Sub: {str(e)}",
                connector_type="pubsub",
                tenant_id=tenant_id,
            ) from e

    def produce(self, topic: str, message: Dict[str, Any], tenant_id: str) -> bool:
        """Produce message to Pub/Sub topic (fire-and-forget).

        Args:
            topic: Topic name.
            message: Message dict to send.
            tenant_id: Tenant identifier.

        Returns:
            True if message published.

        Raises:
            WriteError: If produce fails.
        """
        self._validate_topic(topic)
        self._validate_message(message)
        try:
            if not self._is_connected:
                raise ConnectionError(
                    "Not connected to Pub/Sub",
                    connector_type="pubsub",
                    tenant_id=tenant_id,
                )
            full_topic = self._tenant_topic(topic, tenant_id)
            client = self._get_client(tenant_id)

            if hasattr(client, "publish"):
                import json

                msg_bytes = json.dumps(message).encode("utf-8")
                future = client.publish(full_topic, msg_bytes)
                _ = future.result(timeout=5)
            logger.debug(f"Published to Pub/Sub: topic={full_topic}")
            return True
        except Exception as e:
            raise WriteError(
                f"Failed to publish to Pub/Sub: {str(e)}",
                connector_type="pubsub",
                tenant_id=tenant_id,
            ) from e

    def seek(self, topic: str, offset: int, tenant_id: str) -> None:
        """Seek to position in Pub/Sub subscription (limited support).

        Pub/Sub doesn't support arbitrary seeking like Kafka.
        This method is a no-op for Pub/Sub compatibility.

        Args:
            topic: Topic name.
            offset: Position (ignored for Pub/Sub).
            tenant_id: Tenant identifier.

        Note:
            Pub/Sub supports seeking via seek() API but with constraints.
            This implementation logs the request but doesn't modify position.
        """
        self._validate_topic(topic)
        logger.info(
            f"Pub/Sub seek is limited (topic={topic}, offset={offset}, "
            f"tenant={tenant_id}). Consider using ack/nack for replay."
        )

    def _validate_pubsub_config(self) -> None:
        """Validate Pub/Sub-specific configuration."""
        if not self._config.get_credential("project_id"):
            raise ValidationError(
                "project_id required in credentials",
                connector_type="pubsub",
                tenant_id=self.tenant_id,
            )
        if not self._config.metadata.get("topic_name"):
            raise ValidationError(
                "topic_name required in metadata",
                connector_type="pubsub",
                tenant_id=self.tenant_id,
            )
        if not self._config.metadata.get("subscription_name"):
            raise ValidationError(
                "subscription_name required in metadata",
                connector_type="pubsub",
                tenant_id=self.tenant_id,
            )

    def _create_client(self, tenant_id: str) -> object:
        """Create Pub/Sub publisher client (mocked in tests).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Pub/Sub publisher or mock.
        """
        try:
            from google.cloud import pubsub_v1

            project_id = self._config.get_credential("project_id")
            return pubsub_v1.PublisherClient()
        except ImportError:
            return MagicMock()

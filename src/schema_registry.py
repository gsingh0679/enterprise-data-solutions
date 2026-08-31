"""Schema registry module for managing data schemas.

This module provides a singleton SchemaRegistry for managing, validating, and
retrieving data schemas, along with a frozen Schema dataclass for immutable
schema storage.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Schema:
    """Immutable schema definition.

    This dataclass holds a schema definition and is frozen to ensure immutability
    after initialization. Schema is validated upon creation.

    Attributes:
        schema_id (str): Unique identifier for the schema.
        name (str): Human-readable name of the schema.
        version (str): Version of the schema (e.g., "1.0", "2.1").
        fields (Dict[str, Any]): Schema fields with their definitions.
            Each field maps to a type and optional metadata.
        description (Optional[str]): Human-readable description of the schema.

    Raises:
        ValueError: If validation fails during initialization.

    Example:
        >>> schema = Schema(
        ...     schema_id="user_v1",
        ...     name="User",
        ...     version="1.0",
        ...     fields={"id": {"type": "string"}, "age": {"type": "int"}},
        ...     description="User profile schema"
        ... )
    """

    schema_id: str
    name: str
    version: str
    fields: Dict[str, Any]
    description: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate schema after initialization.

        This method is called automatically by the dataclass after all fields
        are set. It validates the schema and raises ValueError if any field
        is invalid.

        Raises:
            ValueError: If any field fails validation.
        """
        self.validate()

    def validate(self) -> None:
        """Validate schema invariants.

        Checks that all schema fields contain valid values and raises ValueError
        with descriptive messages if validation fails.

        Raises:
            ValueError: If schema_id, name, version are empty, or if fields
                is empty or not a dictionary.
        """
        if not self.schema_id or not isinstance(self.schema_id, str):
            raise ValueError(
                f"schema_id must be a non-empty string, got {self.schema_id!r}"
            )

        if not self.name or not isinstance(self.name, str):
            raise ValueError(
                f"name must be a non-empty string, got {self.name!r}"
            )

        if not self.version or not isinstance(self.version, str):
            raise ValueError(
                f"version must be a non-empty string, got {self.version!r}"
            )

        if not isinstance(self.fields, dict) or not self.fields:
            raise ValueError(
                f"fields must be a non-empty dictionary, "
                f"got {type(self.fields).__name__}"
            )

        logger.info(
            f"Schema validated: schema_id={self.schema_id}, "
            f"name={self.name}, version={self.version}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert schema to dictionary representation.

        Returns:
            Dictionary containing all schema fields.
        """
        return {
            "schema_id": self.schema_id,
            "name": self.name,
            "version": self.version,
            "fields": self.fields,
            "description": self.description,
        }


class SchemaRegistry:
    """Singleton registry for managing data schemas.

    This class implements the singleton pattern to ensure only one instance
    of the schema registry exists throughout the application lifecycle.
    It provides methods to register, retrieve, validate, and manage schemas.

    Example:
        >>> registry = SchemaRegistry()
        >>> schema = Schema(
        ...     schema_id="user_v1",
        ...     name="User",
        ...     version="1.0",
        ...     fields={"id": {"type": "string"}}
        ... )
        >>> registry.register(schema)
        >>> retrieved = registry.get("user_v1")
    """

    _instance: Optional["SchemaRegistry"] = None
    _schemas: Dict[str, Schema] = {}

    def __new__(cls) -> "SchemaRegistry":
        """Create or return existing singleton instance.

        Ensures that only one SchemaRegistry instance exists by returning
        the cached instance if it already exists, or creating a new one.

        Returns:
            The singleton SchemaRegistry instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._schemas = {}
            logger.info("SchemaRegistry singleton instance created")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (testing only).

        Clears the cached singleton instance and all registered schemas,
        allowing a new instance to be created on the next access. This method
        is intended for testing purposes only.

        Example:
            >>> SchemaRegistry.reset()  # In tests only
        """
        cls._instance = None
        cls._schemas = {}
        logger.debug("SchemaRegistry singleton instance reset (testing)")

    def register(self, schema: Schema) -> None:
        """Register a schema in the registry.

        Registers a schema with its schema_id as the key. If a schema with
        the same ID already exists, it is replaced.

        Args:
            schema: Schema object to register.

        Raises:
            TypeError: If schema is not a Schema instance.
            ValueError: If schema validation fails.

        Example:
            >>> registry = SchemaRegistry()
            >>> schema = Schema(
            ...     schema_id="user_v1",
            ...     name="User",
            ...     version="1.0",
            ...     fields={"id": {"type": "string"}}
            ... )
            >>> registry.register(schema)
        """
        if not isinstance(schema, Schema):
            raise TypeError(
                f"Expected Schema instance, got {type(schema).__name__}"
            )

        try:
            self._schemas[schema.schema_id] = schema
            logger.info(f"Schema registered: {schema.schema_id} v{schema.version}")
        except Exception as e:
            logger.error(f"Failed to register schema {schema.schema_id}: {e}")
            raise ValueError(f"Failed to register schema: {e}") from e

    def get(self, schema_id: str) -> Optional[Schema]:
        """Retrieve a schema by its ID.

        Args:
            schema_id: The unique identifier of the schema to retrieve.

        Returns:
            The Schema object if found, None otherwise.

        Example:
            >>> registry = SchemaRegistry()
            >>> schema = registry.get("user_v1")
        """
        schema = self._schemas.get(schema_id)
        if schema:
            logger.debug(f"Schema retrieved: {schema_id}")
        else:
            logger.warning(f"Schema not found: {schema_id}")
        return schema

    def list_schemas(self) -> List[str]:
        """List all registered schema IDs.

        Returns:
            List of all registered schema IDs.

        Example:
            >>> registry = SchemaRegistry()
            >>> ids = registry.list_schemas()
            >>> print(ids)
            ['user_v1', 'product_v1']
        """
        logger.info(f"Listing {len(self._schemas)} registered schemas")
        return list(self._schemas.keys())

    def list_all(self) -> List[Schema]:
        """List all registered schemas.

        Returns:
            List of all Schema objects currently registered.

        Example:
            >>> registry = SchemaRegistry()
            >>> schemas = registry.list_all()
        """
        logger.info(f"Retrieving all {len(self._schemas)} registered schemas")
        return list(self._schemas.values())

    def unregister(self, schema_id: str) -> bool:
        """Unregister a schema by its ID.

        Removes a schema from the registry if it exists.

        Args:
            schema_id: The unique identifier of the schema to remove.

        Returns:
            True if the schema was removed, False if it did not exist.

        Example:
            >>> registry = SchemaRegistry()
            >>> removed = registry.unregister("user_v1")
        """
        if schema_id in self._schemas:
            del self._schemas[schema_id]
            logger.info(f"Schema unregistered: {schema_id}")
            return True
        logger.warning(f"Attempted to unregister non-existent schema: {schema_id}")
        return False

    def exists(self, schema_id: str) -> bool:
        """Check if a schema exists in the registry.

        Args:
            schema_id: The unique identifier to check.

        Returns:
            True if the schema exists, False otherwise.

        Example:
            >>> registry = SchemaRegistry()
            >>> exists = registry.exists("user_v1")
        """
        return schema_id in self._schemas

    def validate_data(
        self, schema_id: str, data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate data against a registered schema.

        Performs basic validation that all required fields from the schema
        are present in the data dictionary.

        Args:
            schema_id: The ID of the schema to validate against.
            data: The data dictionary to validate.

        Returns:
            Tuple of (is_valid, error_message). If valid, error_message is None.

        Example:
            >>> registry = SchemaRegistry()
            >>> is_valid, error = registry.validate_data(
            ...     "user_v1",
            ...     {"id": "123", "age": 30}
            ... )
        """
        schema = self.get(schema_id)
        if not schema:
            error_msg = f"Schema not found: {schema_id}"
            logger.error(error_msg)
            return False, error_msg

        if not isinstance(data, dict):
            error_msg = f"Expected dict, got {type(data).__name__}"
            logger.error(error_msg)
            return False, error_msg

        missing_fields = set(schema.fields.keys()) - set(data.keys())
        if missing_fields:
            error_msg = f"Missing required fields: {missing_fields}"
            logger.warning(f"Validation failed for {schema_id}: {error_msg}")
            return False, error_msg

        logger.info(f"Data validation passed for schema {schema_id}")
        return True, None

    def get_schema_count(self) -> int:
        """Get the total number of registered schemas.

        Returns:
            Count of registered schemas.

        Example:
            >>> registry = SchemaRegistry()
            >>> count = registry.get_schema_count()
        """
        return len(self._schemas)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    registry = SchemaRegistry()

    try:
        # Register a schema
        user_schema = Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
                "age": {"type": "int", "required": False},
            },
            description="User profile schema",
        )
        registry.register(user_schema)

        # Retrieve and validate
        schema = registry.get("user_v1")
        print(f"Retrieved schema: {schema.name} (v{schema.version})")

        # Validate data
        test_data = {"id": "123", "email": "user@example.com"}
        is_valid, error = registry.validate_data("user_v1", test_data)
        print(f"Validation result: {is_valid}, Error: {error}")

        # List all schemas
        print(f"Total schemas: {registry.get_schema_count()}")
        print(f"Schema IDs: {registry.list_schemas()}")

    except Exception as e:
        print(f"Error: {e}")

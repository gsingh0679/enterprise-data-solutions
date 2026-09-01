"""Unit tests for schema_registry module.

This test suite covers the Schema dataclass and SchemaRegistry singleton class,
including validation, registration, retrieval, and data validation.
"""

import pytest
import logging
from dataclasses import FrozenInstanceError

from src.data_ops.schema_registry import Schema, SchemaRegistry


class TestSchema:
    """Test suite for Schema dataclass."""

    @pytest.fixture
    def valid_schema_dict(self):
        """Provide valid schema data for tests."""
        return {
            "schema_id": "user_v1",
            "name": "User",
            "version": "1.0",
            "fields": {"id": {"type": "string"}, "email": {"type": "string"}},
            "description": "User profile schema",
        }

    def test_schema_creation_happy_path(self, valid_schema_dict):
        """Test successful schema creation with all fields."""
        schema = Schema(**valid_schema_dict)
        assert schema.schema_id == "user_v1"
        assert schema.name == "User"
        assert schema.version == "1.0"
        assert schema.description == "User profile schema"
        assert len(schema.fields) == 2

    def test_schema_creation_without_description(self):
        """Test schema creation without optional description."""
        schema = Schema(
            schema_id="product_v1",
            name="Product",
            version="1.0",
            fields={"sku": {"type": "string"}},
        )
        assert schema.description is None
        assert schema.schema_id == "product_v1"

    def test_schema_validation_empty_schema_id(self):
        """Test validation fails when schema_id is empty."""
        with pytest.raises(ValueError, match="schema_id must be a non-empty string"):
            Schema(
                schema_id="",
                name="User",
                version="1.0",
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_none_schema_id(self):
        """Test validation fails when schema_id is None."""
        with pytest.raises(ValueError, match="schema_id must be a non-empty string"):
            Schema(
                schema_id=None,
                name="User",
                version="1.0",
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_non_string_schema_id(self):
        """Test validation fails when schema_id is not a string."""
        with pytest.raises(ValueError, match="schema_id must be a non-empty string"):
            Schema(
                schema_id=123,
                name="User",
                version="1.0",
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_empty_name(self):
        """Test validation fails when name is empty."""
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            Schema(
                schema_id="user_v1",
                name="",
                version="1.0",
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_none_name(self):
        """Test validation fails when name is None."""
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            Schema(
                schema_id="user_v1",
                name=None,
                version="1.0",
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_non_string_name(self):
        """Test validation fails when name is not a string."""
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            Schema(
                schema_id="user_v1",
                name=42,
                version="1.0",
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_empty_version(self):
        """Test validation fails when version is empty."""
        with pytest.raises(ValueError, match="version must be a non-empty string"):
            Schema(
                schema_id="user_v1",
                name="User",
                version="",
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_none_version(self):
        """Test validation fails when version is None."""
        with pytest.raises(ValueError, match="version must be a non-empty string"):
            Schema(
                schema_id="user_v1",
                name="User",
                version=None,
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_non_string_version(self):
        """Test validation fails when version is not a string."""
        with pytest.raises(ValueError, match="version must be a non-empty string"):
            Schema(
                schema_id="user_v1",
                name="User",
                version=1.0,
                fields={"id": {"type": "string"}},
            )

    def test_schema_validation_empty_fields(self):
        """Test validation fails when fields is empty dictionary."""
        with pytest.raises(ValueError, match="fields must be a non-empty dictionary"):
            Schema(
                schema_id="user_v1",
                name="User",
                version="1.0",
                fields={},
            )

    def test_schema_validation_none_fields(self):
        """Test validation fails when fields is None."""
        with pytest.raises(ValueError, match="fields must be a non-empty dictionary"):
            Schema(
                schema_id="user_v1",
                name="User",
                version="1.0",
                fields=None,
            )

    def test_schema_validation_non_dict_fields(self):
        """Test validation fails when fields is not a dictionary."""
        with pytest.raises(ValueError, match="fields must be a non-empty dictionary"):
            Schema(
                schema_id="user_v1",
                name="User",
                version="1.0",
                fields=["id", "email"],
            )

    def test_schema_immutability(self, valid_schema_dict):
        """Test that frozen dataclass cannot be modified."""
        schema = Schema(**valid_schema_dict)
        with pytest.raises(FrozenInstanceError):
            schema.schema_id = "user_v2"

    def test_schema_immutability_name(self, valid_schema_dict):
        """Test that name field cannot be modified."""
        schema = Schema(**valid_schema_dict)
        with pytest.raises(FrozenInstanceError):
            schema.name = "UpdatedUser"

    def test_schema_to_dict_complete(self, valid_schema_dict):
        """Test to_dict() returns all fields."""
        schema = Schema(**valid_schema_dict)
        result = schema.to_dict()

        assert result["schema_id"] == "user_v1"
        assert result["name"] == "User"
        assert result["version"] == "1.0"
        assert result["description"] == "User profile schema"
        assert result["fields"] == valid_schema_dict["fields"]

    def test_schema_to_dict_without_description(self):
        """Test to_dict() when description is None."""
        schema = Schema(
            schema_id="product_v1",
            name="Product",
            version="1.0",
            fields={"sku": {"type": "string"}},
        )
        result = schema.to_dict()
        assert result["description"] is None

    def test_schema_with_complex_fields(self):
        """Test schema with complex field definitions."""
        complex_fields = {
            "id": {"type": "string", "required": True},
            "age": {"type": "int", "required": False, "min": 0, "max": 150},
            "email": {"type": "string", "required": True, "format": "email"},
        }
        schema = Schema(
            schema_id="user_v2",
            name="User",
            version="2.0",
            fields=complex_fields,
        )
        assert len(schema.fields) == 3
        assert schema.fields["age"]["max"] == 150


class TestSchemaRegistry:
    """Test suite for SchemaRegistry singleton."""

    @pytest.fixture(autouse=True)
    def cleanup_registry(self):
        """Reset registry before and after each test."""
        SchemaRegistry.reset()
        yield
        SchemaRegistry.reset()

    @pytest.fixture
    def user_schema(self):
        """Provide a valid user schema for tests."""
        return Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={"id": {"type": "string"}, "email": {"type": "string"}},
            description="User profile schema",
        )

    @pytest.fixture
    def product_schema(self):
        """Provide a valid product schema for tests."""
        return Schema(
            schema_id="product_v1",
            name="Product",
            version="1.0",
            fields={"sku": {"type": "string"}, "name": {"type": "string"}},
            description="Product catalog schema",
        )

    def test_singleton_only_one_instance(self, user_schema):
        """Test that SchemaRegistry creates only one instance."""
        registry1 = SchemaRegistry()
        registry2 = SchemaRegistry()
        assert registry1 is registry2

    def test_register_valid_schema(self, user_schema):
        """Test successful schema registration."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        assert registry.exists("user_v1")

    def test_register_multiple_schemas(self, user_schema, product_schema):
        """Test registering multiple schemas."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        registry.register(product_schema)
        assert registry.get_schema_count() == 2

    def test_register_non_schema_type(self):
        """Test registration fails with non-Schema object."""
        registry = SchemaRegistry()
        with pytest.raises(TypeError, match="Expected Schema instance"):
            registry.register({"schema_id": "user_v1"})

    def test_register_non_schema_string(self):
        """Test registration fails when passing string."""
        registry = SchemaRegistry()
        with pytest.raises(TypeError, match="Expected Schema instance"):
            registry.register("user_v1")

    def test_register_non_schema_none(self):
        """Test registration fails when passing None."""
        registry = SchemaRegistry()
        with pytest.raises(TypeError, match="Expected Schema instance"):
            registry.register(None)

    def test_register_replaces_existing_schema(self, user_schema):
        """Test that registering with same ID replaces existing schema."""
        registry = SchemaRegistry()
        registry.register(user_schema)

        updated_schema = Schema(
            schema_id="user_v1",
            name="User",
            version="2.0",
            fields={"id": {"type": "string"}},
        )
        registry.register(updated_schema)

        retrieved = registry.get("user_v1")
        assert retrieved.version == "2.0"
        assert registry.get_schema_count() == 1

    def test_get_existing_schema(self, user_schema):
        """Test retrieving an existing schema."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        retrieved = registry.get("user_v1")
        assert retrieved is user_schema
        assert retrieved.name == "User"

    def test_get_non_existent_schema(self):
        """Test retrieving a schema that doesn't exist."""
        registry = SchemaRegistry()
        result = registry.get("non_existent")
        assert result is None

    def test_list_schemas_empty(self):
        """Test list_schemas returns empty list when no schemas registered."""
        registry = SchemaRegistry()
        schemas = registry.list_schemas()
        assert schemas == []

    def test_list_schemas_multiple(self, user_schema, product_schema):
        """Test list_schemas returns all registered schema IDs."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        registry.register(product_schema)
        schemas = registry.list_schemas()
        assert len(schemas) == 2
        assert "user_v1" in schemas
        assert "product_v1" in schemas

    def test_list_all_empty(self):
        """Test list_all returns empty list when no schemas registered."""
        registry = SchemaRegistry()
        schemas = registry.list_all()
        assert schemas == []

    def test_list_all_multiple(self, user_schema, product_schema):
        """Test list_all returns all Schema objects."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        registry.register(product_schema)
        schemas = registry.list_all()
        assert len(schemas) == 2
        assert user_schema in schemas
        assert product_schema in schemas

    def test_unregister_existing_schema(self, user_schema):
        """Test unregistering an existing schema."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        assert registry.exists("user_v1")

        result = registry.unregister("user_v1")
        assert result is True
        assert not registry.exists("user_v1")

    def test_unregister_non_existent_schema(self):
        """Test unregistering a schema that doesn't exist."""
        registry = SchemaRegistry()
        result = registry.unregister("non_existent")
        assert result is False

    def test_exists_true(self, user_schema):
        """Test exists returns True for registered schema."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        assert registry.exists("user_v1") is True

    def test_exists_false(self):
        """Test exists returns False for non-registered schema."""
        registry = SchemaRegistry()
        assert registry.exists("user_v1") is False

    def test_validate_data_valid(self, user_schema):
        """Test validating data that matches schema."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        data = {"id": "123", "email": "user@example.com"}
        is_valid, error = registry.validate_data("user_v1", data)
        assert is_valid is True
        assert error is None

    def test_validate_data_missing_fields(self, user_schema):
        """Test validation fails when required fields are missing."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        data = {"id": "123"}  # Missing email
        is_valid, error = registry.validate_data("user_v1", data)
        assert is_valid is False
        assert "Missing required fields" in error
        assert "email" in error

    def test_validate_data_extra_fields_ok(self, user_schema):
        """Test validation passes when data has extra fields."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        data = {"id": "123", "email": "user@example.com", "age": 30}
        is_valid, error = registry.validate_data("user_v1", data)
        assert is_valid is True
        assert error is None

    def test_validate_data_schema_not_found(self):
        """Test validation fails when schema doesn't exist."""
        registry = SchemaRegistry()
        data = {"id": "123", "email": "user@example.com"}
        is_valid, error = registry.validate_data("non_existent", data)
        assert is_valid is False
        assert "Schema not found" in error

    def test_validate_data_not_dict(self, user_schema):
        """Test validation fails when data is not a dictionary."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        is_valid, error = registry.validate_data("user_v1", "not a dict")
        assert is_valid is False
        assert "Expected dict" in error

    def test_validate_data_with_list(self, user_schema):
        """Test validation fails when data is a list."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        is_valid, error = registry.validate_data("user_v1", [])
        assert is_valid is False
        assert "Expected dict" in error

    def test_get_schema_count_empty(self):
        """Test get_schema_count returns 0 when no schemas."""
        registry = SchemaRegistry()
        assert registry.get_schema_count() == 0

    def test_get_schema_count_multiple(self, user_schema, product_schema):
        """Test get_schema_count returns correct count."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        assert registry.get_schema_count() == 1
        registry.register(product_schema)
        assert registry.get_schema_count() == 2

    def test_reset_clears_singleton(self, user_schema):
        """Test reset clears the singleton instance."""
        registry1 = SchemaRegistry()
        registry1.register(user_schema)
        assert registry1.get_schema_count() == 1

        SchemaRegistry.reset()
        registry2 = SchemaRegistry()
        assert registry2.get_schema_count() == 0

    def test_reset_creates_new_instance(self, user_schema):
        """Test reset allows new instance to be created."""
        registry1 = SchemaRegistry()
        registry1.register(user_schema)
        registry1_id = id(registry1)

        SchemaRegistry.reset()
        registry2 = SchemaRegistry()
        registry2_id = id(registry2)

        assert registry1_id != registry2_id

    def test_workflow_full_cycle(self, user_schema):
        """Test complete workflow: register, validate, retrieve, unregister."""
        registry = SchemaRegistry()

        # Register
        registry.register(user_schema)
        assert registry.exists("user_v1")

        # Validate data
        valid_data = {"id": "123", "email": "test@example.com"}
        is_valid, error = registry.validate_data("user_v1", valid_data)
        assert is_valid

        # Retrieve
        retrieved = registry.get("user_v1")
        assert retrieved.schema_id == "user_v1"

        # Unregister
        result = registry.unregister("user_v1")
        assert result is True
        assert not registry.exists("user_v1")

    def test_validate_data_multiple_missing_fields(self, user_schema):
        """Test error message includes all missing fields."""
        registry = SchemaRegistry()
        registry.register(user_schema)
        data = {}
        is_valid, error = registry.validate_data("user_v1", data)
        assert is_valid is False
        assert "id" in error or "email" in error

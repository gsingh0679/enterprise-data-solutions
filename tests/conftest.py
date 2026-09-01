"""Pytest configuration and shared fixtures for integration tests.

This module provides reusable pytest fixtures for:
- ConfigManager instances
- SchemaRegistry instances
- QualityValidator instances
- Sample schemas
- Sample data records
- Test pipelines
"""

import pytest

from src.config import ConfigManager, PlatformConfig
from src.data_ops.masking_engine import MaskingEngine, MaskingStrategy
from src.data_ops.quality_validator import CircuitBreaker, QualityValidator
from src.data_ops.schema_registry import Schema, SchemaRegistry


@pytest.fixture
def masking_engine():
    """Provide a fresh MaskingEngine instance for testing.

    Returns:
        MaskingEngine: Engine instance for masking records
    """
    return MaskingEngine()


@pytest.fixture
def config_manager():
    """Provide a fresh ConfigManager instance for testing.

    Yields:
        ConfigManager: Singleton instance (reset for each test)
    """
    ConfigManager.reset()
    manager = ConfigManager()
    yield manager
    ConfigManager.reset()


@pytest.fixture
def platform_config():
    """Provide a default PlatformConfig for testing.

    Returns:
        PlatformConfig: Configuration with standard test values
    """
    return PlatformConfig(
        app_env="test",
        storage_path="/tmp/test_data"
    )


@pytest.fixture
def schema_registry():
    """Provide a fresh SchemaRegistry instance for testing.

    Yields:
        SchemaRegistry: Singleton instance (reset for each test)
    """
    SchemaRegistry.reset()
    registry = SchemaRegistry()
    yield registry
    SchemaRegistry.reset()


@pytest.fixture
def quality_validator():
    """Provide a QualityValidator instance for testing.

    Returns:
        QualityValidator: Validator instance
    """
    return QualityValidator()


@pytest.fixture
def circuit_breaker():
    """Provide a default CircuitBreaker for testing.

    Returns:
        CircuitBreaker: Breaker with standard threshold
    """
    return CircuitBreaker(threshold=0.95)


@pytest.fixture
def masking_schema():
    """Provide a schema with masking strategies for testing.

    Returns:
        Schema: Banking schema with PII masking configuration
    """
    return Schema(
        schema_id="banking_v1",
        name="Banking",
        version="1.0",
        fields={
            "customer_id": {"type": "string", "sensitive": False},
            "email": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            "ssn": {"type": "string", "sensitive": True, "masking_strategy": "redact"},
            "credit_card": {
                "type": "string",
                "sensitive": True,
                "masking_strategy": "tokenize",
            },
        },
        description="Banking schema with PII masking",
    )


@pytest.fixture
def simple_schema():
    """Provide a simple test schema.

    Returns:
        Schema: Basic schema with id and email fields
    """
    return Schema(
        schema_id="user_v1",
        name="User",
        version="1.0",
        fields={
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        },
        description="Basic user schema for testing"
    )


@pytest.fixture
def kyc_schema():
    """Provide a KYC (Know Your Customer) schema for testing.

    Returns:
        Schema: Comprehensive KYC schema
    """
    return Schema(
        schema_id="customer_kyc",
        name="Customer KYC",
        version="1.0",
        fields={
            "customer_id": {"type": "string", "required": True},
            "first_name": {"type": "string", "required": True},
            "last_name": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
            "ssn": {"type": "string", "required": False},
            "dob": {"type": "date", "required": True},
            "status": {"type": "string", "required": False},
        },
        description="KYC schema for customer verification"
    )


@pytest.fixture
def valid_records():
    """Provide sample valid records.

    Returns:
        list: Records that pass all validation checks
    """
    return [
        {"id": "1", "email": "alice@example.com"},
        {"id": "2", "email": "bob@example.com"},
        {"id": "3", "email": "charlie@example.com"},
    ]


@pytest.fixture
def invalid_records():
    """Provide sample invalid records.

    Returns:
        list: Records that fail validation checks
    """
    return [
        {"id": "1", "email": None},  # null email
        {"id": "2"},  # missing email
        {"email": "charlie@example.com"},  # missing id
    ]


@pytest.fixture
def mixed_records():
    """Provide sample records with mix of valid and invalid.

    Returns:
        list: 50% valid, 50% invalid records
    """
    return [
        {"id": "1", "email": "alice@example.com"},  # valid
        {"id": "2", "email": None},  # invalid: null email
        {"id": "3", "email": "charlie@example.com"},  # valid
        {"id": "4"},  # invalid: missing email
    ]


@pytest.fixture
def valid_kyc_records():
    """Provide sample valid KYC records.

    Returns:
        list: Records that pass KYC validation
    """
    return [
        {
            "customer_id": "cust_001",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "ssn": "123-45-6789",
            "dob": "1990-01-15",
            "status": "active",
        },
        {
            "customer_id": "cust_002",
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com",
            "dob": "1985-06-20",
            "status": "verified",
        },
    ]


@pytest.fixture
def invalid_kyc_records():
    """Provide sample invalid KYC records.

    Returns:
        list: Records that fail KYC validation
    """
    return [
        {
            "customer_id": "cust_003",
            "first_name": None,  # invalid
            "last_name": "Patel",
            "email": "patel@example.com",
            "dob": "1992-03-10",
        },
        {
            "customer_id": "cust_004",
            "first_name": "Bob",
            "last_name": "Johnson",
            # missing email
            "dob": "1988-11-25",
        },
    ]


@pytest.fixture
def large_batch_records():
    """Provide a large batch of valid records.

    Returns:
        list: 1000 valid records for performance testing
    """
    return [
        {"id": str(i), "email": f"user{i}@example.com"}
        for i in range(1000)
    ]


@pytest.fixture
def schema_dict():
    """Provide a schema as dictionary (not Schema object).

    Returns:
        dict: Schema in dictionary format
    """
    return {
        "id": {"type": "string", "required": True},
        "email": {"type": "string", "required": True},
        "age": {"type": "int", "required": False},
    }


@pytest.fixture
def validation_pipeline(
    config_manager, schema_registry, quality_validator, circuit_breaker
):
    """Provide a complete validation pipeline with all components.

    Args:
        config_manager: ConfigManager instance
        schema_registry: SchemaRegistry instance
        quality_validator: QualityValidator instance
        circuit_breaker: CircuitBreaker instance

    Returns:
        dict: Pipeline dictionary with all components
    """
    return {
        "config": config_manager,
        "registry": schema_registry,
        "validator": quality_validator,
        "breaker": circuit_breaker,
    }


@pytest.fixture
def tenant_configs():
    """Provide configurations for multiple tenants.

    Returns:
        dict: Tenant IDs mapped to configs
    """
    return {
        "bankcorp": PlatformConfig(app_env="prod", storage_path="/data/bankcorp"),
        "fintech": PlatformConfig(app_env="prod", storage_path="/data/fintech"),
        "test": PlatformConfig(app_env="test", storage_path="/tmp/test"),
    }


@pytest.fixture
def multiple_schemas(schema_registry):
    """Register multiple schemas in the registry.

    Args:
        schema_registry: SchemaRegistry instance

    Returns:
        dict: Schema IDs mapped to Schema objects
    """
    schemas = {
        "user_v1": Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            },
        ),
        "customer_v1": Schema(
            schema_id="customer_v1",
            name="Customer",
            version="1.0",
            fields={
                "customer_id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            },
        ),
        "order_v1": Schema(
            schema_id="order_v1",
            name="Order",
            version="1.0",
            fields={
                "order_id": {"type": "string", "required": True},
                "customer_id": {"type": "string", "required": True},
                "amount": {"type": "float", "required": True},
            },
        ),
    }

    for schema in schemas.values():
        schema_registry.register(schema)

    return schemas

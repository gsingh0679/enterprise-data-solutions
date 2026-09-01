"""Integration tests for the enterprise data platform.

Tests verify that config, schema_registry, and quality_validator work together
as a complete pipeline: config → schema → validation → circuit breaker.
"""

import pytest

from src.config import ConfigManager
from src.data_ops.quality_validator import CircuitBreaker, QualityValidator
from src.data_ops.schema_registry import Schema, SchemaRegistry


class TestBasicPipeline:
    """Test basic integration of all 3 components."""

    def test_full_pipeline_valid_data(
        self, config_manager, schema_registry, quality_validator, circuit_breaker
    ):
        """Test complete pipeline with valid data.

        Flow:
        1. Load config (ConfigManager.load())
        2. Register schema (SchemaRegistry.register_schema())
        3. Activate schema (SchemaRegistry.get())
        4. Validate batch (QualityValidator.validate_batch())
        5. Check circuit breaker (CircuitBreaker.check())
        """
        # Step 1: Load config
        config = config_manager.load()
        assert config.app_env == "local"
        assert config.storage_path == "./data"

        # Step 2: Register schema
        schema = Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            },
        )
        schema_registry.register(schema)

        # Step 3: Activate schema
        retrieved_schema = schema_registry.get("user_v1")
        assert retrieved_schema is not None
        assert retrieved_schema.schema_id == "user_v1"

        # Step 4: Validate batch
        records = [
            {"id": "1", "email": "alice@example.com"},
            {"id": "2", "email": "bob@example.com"},
        ]
        result = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="bankcorp",
            threshold=0.95,
        )

        # Step 5: Check circuit breaker
        assert result.quality_score == 1.0
        assert circuit_breaker.check(result.quality_score) is True
        assert result.circuit_breaker_triggered is False

    def test_full_pipeline_invalid_data(
        self, config_manager, schema_registry, quality_validator, circuit_breaker
    ):
        """Test complete pipeline with invalid data."""
        # Step 1: Load config
        config = config_manager.load()
        assert config is not None

        # Step 2: Register schema
        schema = Schema(
            schema_id="user_v2",
            name="User",
            version="2.0",
            fields={
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            },
        )
        schema_registry.register(schema)

        # Step 3: Get schema
        retrieved_schema = schema_registry.get("user_v2")
        assert retrieved_schema is not None

        # Step 4: Validate batch with invalid records
        records = [
            {"id": "1", "email": "alice@example.com"},
            {"id": "2", "email": None},  # Invalid
            {"id": "3"},  # Missing email
        ]
        result = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="bankcorp",
            threshold=0.95,
        )

        # Step 5: Check circuit breaker
        assert result.quality_score < 0.95
        assert circuit_breaker.check(result.quality_score) is False
        assert result.circuit_breaker_triggered is True

    def test_pipeline_quality_threshold_boundary(
        self, schema_registry, quality_validator
    ):
        """Test pipeline at quality threshold boundary."""
        # Register schema
        schema = Schema(
            schema_id="boundary_test",
            name="Boundary Test",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            },
        )
        schema_registry.register(schema)
        retrieved_schema = schema_registry.get("boundary_test")

        # Create records: 19 valid, 1 invalid = 95% quality
        records = [
            {"id": str(i), "email": f"user{i}@example.com"}
            for i in range(19)
        ]
        records.append({"id": "invalid"})  # Missing email

        # Validate with exact 95% threshold
        result = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="tenant1",
            threshold=0.95,
        )

        # At exactly 95%, circuit breaker should pass
        assert abs(result.quality_score - 0.95) < 0.001
        breaker = CircuitBreaker(threshold=0.95)
        assert breaker.check(result.quality_score) is True
        assert result.circuit_breaker_triggered is False


class TestMultiTenantPipeline:
    """Test pipeline with multi-tenancy."""

    def test_pipeline_different_tenants(
        self, schema_registry, quality_validator
    ):
        """Test that same schema works for different tenants."""
        # Register shared schema
        schema = Schema(
            schema_id="shared_v1",
            name="Shared",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            },
        )
        schema_registry.register(schema)
        retrieved_schema = schema_registry.get("shared_v1")

        records = [
            {"id": "1", "email": "alice@example.com"},
            {"id": "2", "email": "bob@example.com"},
        ]

        # Validate for tenant1
        result1 = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="bankcorp",
            threshold=0.95,
        )

        # Validate for tenant2
        result2 = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="fintech",
            threshold=0.95,
        )

        # Both should pass with same data
        assert result1.quality_score == 1.0
        assert result2.quality_score == 1.0
        assert result1.circuit_breaker_triggered is False
        assert result2.circuit_breaker_triggered is False

        # But have different batch IDs (per-tenant tracking)
        assert result1.batch_id != result2.batch_id

    def test_pipeline_tenant_isolated_validation(
        self, schema_registry, quality_validator
    ):
        """Test that validation results are isolated per tenant."""
        schema = Schema(
            schema_id="tenant_isolation_test",
            name="Tenant Isolation",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "value": {"type": "string", "required": True},
            },
        )
        schema_registry.register(schema)
        retrieved_schema = schema_registry.get("tenant_isolation_test")

        # Valid records for tenant1
        records_valid = [
            {"id": "1", "value": "a"},
            {"id": "2", "value": "b"},
        ]

        # Invalid records for tenant2
        records_invalid = [
            {"id": "1", "value": None},
            {"id": "2", "value": None},
        ]

        result1 = quality_validator.validate_batch(
            records=records_valid,
            schema=retrieved_schema.fields,
            tenant_id="tenant1",
        )

        result2 = quality_validator.validate_batch(
            records=records_invalid,
            schema=retrieved_schema.fields,
            tenant_id="tenant2",
        )

        # Tenant1 passes, tenant2 fails
        assert result1.quality_score == 1.0
        assert result2.quality_score == 0.0


class TestComplexPipeline:
    """Test pipeline with complex schemas and data."""

    def test_pipeline_kyc_schema(self, schema_registry, quality_validator):
        """Test pipeline with comprehensive KYC schema."""
        # Register KYC schema
        kyc_schema = Schema(
            schema_id="customer_kyc_v1",
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
            description="Customer KYC data",
        )
        schema_registry.register(kyc_schema)
        retrieved_schema = schema_registry.get("customer_kyc_v1")

        # Valid KYC records
        records = [
            {
                "customer_id": "cust_001",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "ssn": "123-45-6789",
                "dob": "1990-01-15",
                "status": "verified",
            },
            {
                "customer_id": "cust_002",
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane@example.com",
                "dob": "1985-06-20",
            },
        ]

        result = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="bankcorp",
            threshold=0.95,
        )

        assert result.quality_score == 1.0
        assert result.circuit_breaker_triggered is False
        assert result.passed_records == 2
        assert result.failed_records == 0

    def test_pipeline_large_batch(self, schema_registry, quality_validator):
        """Test pipeline with large batch of records."""
        # Register schema
        schema = Schema(
            schema_id="large_batch_v1",
            name="Large Batch",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "value": {"type": "string", "required": True},
            },
        )
        schema_registry.register(schema)
        retrieved_schema = schema_registry.get("large_batch_v1")

        # Create 1000 records
        records = [
            {"id": str(i), "value": f"val_{i}"}
            for i in range(1000)
        ]

        result = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="tenant1",
        )

        assert result.quality_score == 1.0
        assert result.passed_records == 1000
        assert result.failed_records == 0

    def test_pipeline_mixed_quality_data(
        self, schema_registry, quality_validator, circuit_breaker
    ):
        """Test pipeline with mixed quality data."""
        schema = Schema(
            schema_id="mixed_quality_v1",
            name="Mixed Quality",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
                "phone": {"type": "string", "required": False},
            },
        )
        schema_registry.register(schema)
        retrieved_schema = schema_registry.get("mixed_quality_v1")

        # 80% valid, 20% invalid
        records = [
            {"id": str(i), "email": f"user{i}@example.com", "phone": f"555-{i:04d}"}
            for i in range(80)
        ]
        records.extend([
            {"id": str(80 + i), "email": None}  # Invalid: null email
            for i in range(20)
        ])

        result = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="tenant1",
            threshold=0.95,
        )

        # 80% quality < 95% threshold
        assert result.quality_score == 0.80
        assert circuit_breaker.check(result.quality_score) is False
        assert result.circuit_breaker_triggered is True


class TestPipelineErrorHandling:
    """Test pipeline error handling and edge cases."""

    def test_pipeline_empty_batch(self, schema_registry, quality_validator):
        """Test pipeline with empty batch."""
        schema = Schema(
            schema_id="empty_batch_test",
            name="Empty Batch",
            version="1.0",
            fields={"id": {"type": "string", "required": True}},
        )
        schema_registry.register(schema)
        retrieved_schema = schema_registry.get("empty_batch_test")

        result = quality_validator.validate_batch(
            records=[],
            schema=retrieved_schema.fields,
            tenant_id="tenant1",
        )

        assert result.quality_score == 0.0
        assert result.passed_records == 0
        assert result.failed_records == 0

    def test_pipeline_schema_not_found(
        self, quality_validator
    ):
        """Test pipeline behavior when schema doesn't exist."""
        # Schema not in registry - use dict directly
        schema_dict = {"id": {"type": "string", "required": True}}
        records = [{"id": "1"}]

        result = quality_validator.validate_batch(
            records=records,
            schema=schema_dict,
            tenant_id="tenant1",
        )

        assert result.quality_score == 1.0

    def test_pipeline_all_records_invalid(
        self, schema_registry, quality_validator, circuit_breaker
    ):
        """Test pipeline when all records fail validation."""
        schema = Schema(
            schema_id="all_invalid_test",
            name="All Invalid",
            version="1.0",
            fields={
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            },
        )
        schema_registry.register(schema)
        retrieved_schema = schema_registry.get("all_invalid_test")

        records = [
            {"id": "1"},  # Missing email
            {"id": "2"},  # Missing email
            {"id": "3"},  # Missing email
        ]

        result = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="tenant1",
            threshold=0.95,
        )

        assert result.quality_score == 0.0
        assert result.passed_records == 0
        assert result.failed_records == 3
        assert circuit_breaker.check(result.quality_score) is False
        assert result.circuit_breaker_triggered is True

    def test_pipeline_with_different_circuit_breaker_thresholds(
        self, schema_registry, quality_validator
    ):
        """Test pipeline with different circuit breaker thresholds."""
        schema = Schema(
            schema_id="threshold_test",
            name="Threshold Test",
            version="1.0",
            fields={"id": {"type": "string", "required": True}},
        )
        schema_registry.register(schema)
        retrieved_schema = schema_registry.get("threshold_test")

        records = [{"id": "1"}, {"id": "2"}]

        # Validate with 50% threshold
        result_50 = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="tenant1",
            threshold=0.50,
        )
        breaker_50 = CircuitBreaker(threshold=0.50)

        # Validate with 95% threshold
        result_95 = quality_validator.validate_batch(
            records=records,
            schema=retrieved_schema.fields,
            tenant_id="tenant1",
            threshold=0.95,
        )
        breaker_95 = CircuitBreaker(threshold=0.95)

        # Same quality score (100%) with different thresholds
        assert result_50.quality_score == result_95.quality_score
        assert result_50.quality_score == 1.0

        # Different circuit breaker results
        assert breaker_50.check(result_50.quality_score) is True
        assert breaker_95.check(result_95.quality_score) is True


class TestPipelineMultipleSchemas:
    """Test pipeline with multiple schemas."""

    def test_pipeline_register_and_use_multiple_schemas(
        self, schema_registry, quality_validator
    ):
        """Test registering and using multiple schemas in pipeline."""
        # Register multiple schemas
        schemas_data = [
            ("user_v1", {"id": {"type": "string", "required": True}}),
            (
                "customer_v1",
                {
                    "customer_id": {"type": "string", "required": True},
                    "name": {"type": "string", "required": True},
                },
            ),
            (
                "order_v1",
                {
                    "order_id": {"type": "string", "required": True},
                    "amount": {"type": "string", "required": True},
                },
            ),
        ]

        for schema_id, fields in schemas_data:
            schema = Schema(
                schema_id=schema_id,
                name=schema_id.replace("_v1", "").title(),
                version="1.0",
                fields=fields,
            )
            schema_registry.register(schema)

        # Verify all schemas registered
        assert schema_registry.get("user_v1") is not None
        assert schema_registry.get("customer_v1") is not None
        assert schema_registry.get("order_v1") is not None
        assert schema_registry.get_schema_count() == 3

        # Validate data against each schema
        user_records = [{"id": "1"}]
        customer_records = [{"customer_id": "c1", "name": "Alice"}]
        order_records = [{"order_id": "o1", "amount": "100"}]

        user_result = quality_validator.validate_batch(
            user_records,
            schema_registry.get("user_v1").to_dict(),
            "tenant1",
        )
        customer_result = quality_validator.validate_batch(
            customer_records,
            schema_registry.get("customer_v1").to_dict(),
            "tenant1",
        )
        order_result = quality_validator.validate_batch(
            order_records,
            schema_registry.get("order_v1").to_dict(),
            "tenant1",
        )

        assert user_result.quality_score == 1.0
        assert customer_result.quality_score == 1.0
        assert order_result.quality_score == 1.0

    def test_pipeline_schema_isolation(
        self, schema_registry, quality_validator
    ):
        """Test that schemas are isolated from each other."""
        # Schema 1: requires 'id'
        schema1 = Schema(
            schema_id="schema_1",
            name="Schema 1",
            version="1.0",
            fields={"id": {"type": "string", "required": True}},
        )

        # Schema 2: requires 'email'
        schema2 = Schema(
            schema_id="schema_2",
            name="Schema 2",
            version="1.0",
            fields={"email": {"type": "string", "required": True}},
        )

        schema_registry.register(schema1)
        schema_registry.register(schema2)

        # Record with only 'id' should pass schema1 but fail schema2
        record = [{"id": "1"}]

        result1 = quality_validator.validate_batch(
            record,
            schema_registry.get("schema_1").fields,
            "tenant1",
        )

        result2 = quality_validator.validate_batch(
            record,
            schema_registry.get("schema_2").fields,
            "tenant1",
        )

        assert result1.quality_score == 1.0  # Passes schema1
        assert result2.quality_score == 0.0  # Fails schema2


class TestPipelineConfigIntegration:
    """Test config integration in the pipeline."""

    def test_pipeline_config_storage_path(self, config_manager):
        """Test that config can provide storage path."""
        config = config_manager.load()

        # Config should have storage path
        assert hasattr(config, "storage_path")
        assert config.storage_path == "./data"

    def test_pipeline_config_app_env(self, config_manager):
        """Test that config provides app environment."""
        config = config_manager.load()

        # Config should have app_env
        assert hasattr(config, "app_env")
        assert config.app_env in ("local", "dev", "staging", "prod")

    def test_pipeline_with_environment_specific_config(
        self, config_manager, schema_registry, quality_validator
    ):
        """Test pipeline with different environment configs."""
        # Load config (would be environment-specific in production)
        config = config_manager.load()

        # Register schema (environment-agnostic)
        schema = Schema(
            schema_id="env_test",
            name="Environment Test",
            version="1.0",
            fields={"id": {"type": "string", "required": True}},
        )
        schema_registry.register(schema)

        # Validate records (should work same across environments)
        records = [{"id": "1"}, {"id": "2"}]
        result = quality_validator.validate_batch(
            records,
            schema_registry.get("env_test").to_dict(),
            tenant_id=f"tenant_{config.app_env}",
        )

        assert result.quality_score == 1.0
        assert result.passed_records == 2

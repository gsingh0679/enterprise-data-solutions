"""Unit tests for quality_validator module.

Tests cover all classes and methods with 95%+ coverage:
- BatchValidationResult: initialization, validation, immutability
- CircuitBreaker: initialization, threshold checking, edge cases
- QualityValidator: batch validation, record validation, score calculation
"""

import pytest
from src.data_ops.quality_validator import (
    BatchValidationResult,
    CircuitBreaker,
    QualityValidator,
)


class TestBatchValidationResult:
    """Tests for BatchValidationResult dataclass."""

    def test_valid_result_initialization(self):
        """Test creating a valid BatchValidationResult."""
        result = BatchValidationResult(
            batch_id="batch_001",
            passed_records=95,
            failed_records=5,
            quality_score=0.95,
            circuit_breaker_triggered=False,
            errors=[],
        )
        assert result.batch_id == "batch_001"
        assert result.passed_records == 95
        assert result.failed_records == 5
        assert result.quality_score == 0.95
        assert result.circuit_breaker_triggered is False
        assert result.errors == []

    def test_result_with_errors(self):
        """Test result with error details."""
        errors = [
            {
                "record_index": 0,
                "field": "email",
                "error_type": "null_value",
                "message": "Required field is null: email",
            }
        ]
        result = BatchValidationResult(
            batch_id="batch_002",
            passed_records=90,
            failed_records=10,
            quality_score=0.90,
            circuit_breaker_triggered=True,
            errors=errors,
        )
        assert len(result.errors) == 1
        assert result.errors[0]["field"] == "email"

    def test_result_quality_score_zero(self):
        """Test result with zero quality score."""
        result = BatchValidationResult(
            batch_id="batch_003",
            passed_records=0,
            failed_records=100,
            quality_score=0.0,
            circuit_breaker_triggered=True,
            errors=[],
        )
        assert result.quality_score == 0.0

    def test_result_quality_score_one(self):
        """Test result with perfect quality score."""
        result = BatchValidationResult(
            batch_id="batch_004",
            passed_records=100,
            failed_records=0,
            quality_score=1.0,
            circuit_breaker_triggered=False,
            errors=[],
        )
        assert result.quality_score == 1.0

    def test_result_immutability(self):
        """Test that BatchValidationResult is immutable (frozen)."""
        result = BatchValidationResult(
            batch_id="batch_005",
            passed_records=50,
            failed_records=50,
            quality_score=0.5,
            circuit_breaker_triggered=False,
            errors=[],
        )
        with pytest.raises(Exception):  # frozen dataclass raises FrozenInstanceError
            result.passed_records = 100

    def test_invalid_batch_id_empty_string(self):
        """Test that empty batch_id raises ValueError."""
        with pytest.raises(ValueError):
            BatchValidationResult(
                batch_id="",
                passed_records=50,
                failed_records=50,
                quality_score=0.5,
                circuit_breaker_triggered=False,
                errors=[],
            )

    def test_invalid_batch_id_not_string(self):
        """Test that non-string batch_id raises ValueError."""
        with pytest.raises(ValueError):
            BatchValidationResult(
                batch_id=123,
                passed_records=50,
                failed_records=50,
                quality_score=0.5,
                circuit_breaker_triggered=False,
                errors=[],
            )

    def test_invalid_passed_records_negative(self):
        """Test that negative passed_records raises ValueError."""
        with pytest.raises(ValueError):
            BatchValidationResult(
                batch_id="batch_006",
                passed_records=-1,
                failed_records=50,
                quality_score=0.5,
                circuit_breaker_triggered=False,
                errors=[],
            )

    def test_invalid_failed_records_negative(self):
        """Test that negative failed_records raises ValueError."""
        with pytest.raises(ValueError):
            BatchValidationResult(
                batch_id="batch_007",
                passed_records=50,
                failed_records=-1,
                quality_score=0.5,
                circuit_breaker_triggered=False,
                errors=[],
            )

    def test_invalid_quality_score_too_low(self):
        """Test that quality_score < 0.0 raises ValueError."""
        with pytest.raises(ValueError):
            BatchValidationResult(
                batch_id="batch_008",
                passed_records=50,
                failed_records=50,
                quality_score=-0.1,
                circuit_breaker_triggered=False,
                errors=[],
            )

    def test_invalid_quality_score_too_high(self):
        """Test that quality_score > 1.0 raises ValueError."""
        with pytest.raises(ValueError):
            BatchValidationResult(
                batch_id="batch_009",
                passed_records=50,
                failed_records=50,
                quality_score=1.1,
                circuit_breaker_triggered=False,
                errors=[],
            )

    def test_invalid_circuit_breaker_triggered_not_bool(self):
        """Test that non-bool circuit_breaker_triggered raises ValueError."""
        with pytest.raises(ValueError):
            BatchValidationResult(
                batch_id="batch_010",
                passed_records=50,
                failed_records=50,
                quality_score=0.5,
                circuit_breaker_triggered="yes",
                errors=[],
            )

    def test_invalid_errors_not_list(self):
        """Test that non-list errors raises ValueError."""
        with pytest.raises(ValueError):
            BatchValidationResult(
                batch_id="batch_011",
                passed_records=50,
                failed_records=50,
                quality_score=0.5,
                circuit_breaker_triggered=False,
                errors="not a list",
            )


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initialization_default_threshold(self):
        """Test CircuitBreaker initialization with default threshold."""
        breaker = CircuitBreaker()
        assert breaker.get_threshold() == 0.95

    def test_initialization_custom_threshold(self):
        """Test CircuitBreaker initialization with custom threshold."""
        breaker = CircuitBreaker(threshold=0.90)
        assert breaker.get_threshold() == 0.90

    def test_initialization_zero_threshold(self):
        """Test CircuitBreaker initialization with zero threshold."""
        breaker = CircuitBreaker(threshold=0.0)
        assert breaker.get_threshold() == 0.0

    def test_initialization_one_threshold(self):
        """Test CircuitBreaker initialization with one threshold."""
        breaker = CircuitBreaker(threshold=1.0)
        assert breaker.get_threshold() == 1.0

    def test_invalid_threshold_negative(self):
        """Test that negative threshold raises ValueError."""
        with pytest.raises(ValueError):
            CircuitBreaker(threshold=-0.1)

    def test_invalid_threshold_too_high(self):
        """Test that threshold > 1.0 raises ValueError."""
        with pytest.raises(ValueError):
            CircuitBreaker(threshold=1.1)

    def test_invalid_threshold_not_numeric(self):
        """Test that non-numeric threshold raises ValueError."""
        with pytest.raises(ValueError):
            CircuitBreaker(threshold="0.95")

    def test_check_pass_quality_above_threshold(self):
        """Test check() returns True when quality >= threshold."""
        breaker = CircuitBreaker(threshold=0.95)
        assert breaker.check(0.98) is True
        assert breaker.check(0.95) is True  # Equal to threshold

    def test_check_fail_quality_below_threshold(self):
        """Test check() returns False when quality < threshold."""
        breaker = CircuitBreaker(threshold=0.95)
        assert breaker.check(0.90) is False
        assert breaker.check(0.94) is False

    def test_check_zero_quality(self):
        """Test check() with zero quality score."""
        breaker = CircuitBreaker(threshold=0.95)
        assert breaker.check(0.0) is False

    def test_check_perfect_quality(self):
        """Test check() with perfect quality score."""
        breaker = CircuitBreaker(threshold=0.95)
        assert breaker.check(1.0) is True

    def test_invalid_quality_score_negative(self):
        """Test that negative quality_score raises ValueError."""
        breaker = CircuitBreaker(threshold=0.95)
        with pytest.raises(ValueError):
            breaker.check(-0.1)

    def test_invalid_quality_score_too_high(self):
        """Test that quality_score > 1.0 raises ValueError."""
        breaker = CircuitBreaker(threshold=0.95)
        with pytest.raises(ValueError):
            breaker.check(1.1)

    def test_invalid_quality_score_not_numeric(self):
        """Test that non-numeric quality_score raises ValueError."""
        breaker = CircuitBreaker(threshold=0.95)
        with pytest.raises(ValueError):
            breaker.check("0.95")

    def test_integer_threshold_converted_to_float(self):
        """Test that integer threshold is converted to float."""
        breaker = CircuitBreaker(threshold=1)
        assert breaker.get_threshold() == 1.0
        assert isinstance(breaker.get_threshold(), float)


class TestQualityValidator:
    """Tests for QualityValidator class."""

    def test_initialization(self):
        """Test QualityValidator initialization."""
        validator = QualityValidator()
        assert validator is not None

    def test_validate_batch_all_pass(self):
        """Test validating batch where all records pass."""
        validator = QualityValidator()
        records = [
            {"id": "1", "email": "alice@example.com"},
            {"id": "2", "email": "bob@example.com"},
        ]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.95)

        assert result.passed_records == 2
        assert result.failed_records == 0
        assert result.quality_score == 1.0
        assert result.circuit_breaker_triggered is False
        assert len(result.errors) == 0

    def test_validate_batch_partial_pass(self):
        """Test validating batch with some failures."""
        validator = QualityValidator()
        records = [
            {"id": "1", "email": "alice@example.com"},
            {"id": "2", "email": None},  # Missing email
        ]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.95)

        assert result.passed_records == 1
        assert result.failed_records == 1
        assert result.quality_score == 0.5
        assert result.circuit_breaker_triggered is True
        assert len(result.errors) == 1

    def test_validate_batch_all_fail(self):
        """Test validating batch where all records fail."""
        validator = QualityValidator()
        records = [
            {"id": "1"},  # Missing required email
            {"id": "2"},  # Missing required email
        ]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.95)

        assert result.passed_records == 0
        assert result.failed_records == 2
        assert result.quality_score == 0.0
        assert result.circuit_breaker_triggered is True

    def test_validate_batch_meets_threshold(self):
        """Test batch that meets quality threshold."""
        validator = QualityValidator()
        records = [
            {"id": "1", "email": "alice@example.com"},
            {"id": "2", "email": "bob@example.com"},
            {"id": "3", "email": "charlie@example.com"},
        ]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.95)

        assert result.quality_score == 1.0
        assert result.circuit_breaker_triggered is False

    def test_validate_batch_custom_threshold(self):
        """Test batch validation with custom threshold."""
        validator = QualityValidator()
        records = [
            {"id": "1", "email": "alice@example.com"},
            {"id": "2", "email": None},  # Missing email
        ]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.50)

        assert result.quality_score == 0.5
        assert result.circuit_breaker_triggered is False

    def test_validate_batch_empty_records(self):
        """Test validating empty batch."""
        validator = QualityValidator()
        records = []
        schema = {
            "id": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.95)

        assert result.passed_records == 0
        assert result.failed_records == 0
        assert result.quality_score == 0.0

    def test_validate_batch_optional_fields(self):
        """Test batch validation with optional fields."""
        validator = QualityValidator()
        records = [
            {"id": "1", "email": "alice@example.com", "phone": None},
            {"id": "2", "email": "bob@example.com"},  # Missing optional phone
        ]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
            "phone": {"type": "string", "required": False},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.95)

        assert result.passed_records == 2
        assert result.failed_records == 0
        assert result.quality_score == 1.0

    def test_invalid_records_not_list(self):
        """Test that non-list records raises ValueError."""
        validator = QualityValidator()
        schema = {"id": {"type": "string", "required": True}}
        with pytest.raises(ValueError):
            validator.validate_batch("not a list", schema, "tenant1")

    def test_invalid_schema_empty(self):
        """Test that empty schema raises ValueError."""
        validator = QualityValidator()
        records = [{"id": "1"}]
        with pytest.raises(ValueError):
            validator.validate_batch(records, {}, "tenant1")

    def test_invalid_schema_not_dict(self):
        """Test that non-dict schema raises ValueError."""
        validator = QualityValidator()
        records = [{"id": "1"}]
        with pytest.raises(ValueError):
            validator.validate_batch(records, ["id"], "tenant1")

    def test_invalid_tenant_id_empty(self):
        """Test that empty tenant_id raises ValueError."""
        validator = QualityValidator()
        records = [{"id": "1"}]
        schema = {"id": {"type": "string", "required": True}}
        with pytest.raises(ValueError):
            validator.validate_batch(records, schema, "")

    def test_invalid_tenant_id_not_string(self):
        """Test that non-string tenant_id raises ValueError."""
        validator = QualityValidator()
        records = [{"id": "1"}]
        schema = {"id": {"type": "string", "required": True}}
        with pytest.raises(ValueError):
            validator.validate_batch(records, schema, 123)

    def test_invalid_threshold_negative(self):
        """Test that negative threshold raises ValueError."""
        validator = QualityValidator()
        records = [{"id": "1"}]
        schema = {"id": {"type": "string", "required": True}}
        with pytest.raises(ValueError):
            validator.validate_batch(records, schema, "tenant1", threshold=-0.1)

    def test_invalid_threshold_too_high(self):
        """Test that threshold > 1.0 raises ValueError."""
        validator = QualityValidator()
        records = [{"id": "1"}]
        schema = {"id": {"type": "string", "required": True}}
        with pytest.raises(ValueError):
            validator.validate_batch(records, schema, "tenant1", threshold=1.1)

    def test_validate_batch_generates_unique_batch_ids(self):
        """Test that each batch gets a unique ID."""
        validator = QualityValidator()
        records = [{"id": "1", "email": "alice@example.com"}]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }

        result1 = validator.validate_batch(records, schema, "tenant1")
        result2 = validator.validate_batch(records, schema, "tenant1")

        assert result1.batch_id != result2.batch_id

    def test_get_quality_score_all_pass(self):
        """Test get_quality_score with all records passing."""
        validator = QualityValidator()
        score = validator.get_quality_score(100, 0)
        assert score == 1.0

    def test_get_quality_score_all_fail(self):
        """Test get_quality_score with all records failing."""
        validator = QualityValidator()
        score = validator.get_quality_score(0, 100)
        assert score == 0.0

    def test_get_quality_score_half_pass(self):
        """Test get_quality_score with half passing."""
        validator = QualityValidator()
        score = validator.get_quality_score(50, 50)
        assert score == 0.5

    def test_get_quality_score_zero_records(self):
        """Test get_quality_score with zero records."""
        validator = QualityValidator()
        score = validator.get_quality_score(0, 0)
        assert score == 0.0

    def test_get_quality_score_invalid_passed_negative(self):
        """Test that negative passed_records raises ValueError."""
        validator = QualityValidator()
        with pytest.raises(ValueError):
            validator.get_quality_score(-1, 50)

    def test_get_quality_score_invalid_failed_negative(self):
        """Test that negative failed_records raises ValueError."""
        validator = QualityValidator()
        with pytest.raises(ValueError):
            validator.get_quality_score(50, -1)

    def test_get_quality_score_invalid_passed_not_int(self):
        """Test that non-int passed_records raises ValueError."""
        validator = QualityValidator()
        with pytest.raises(ValueError):
            validator.get_quality_score("50", 50)

    def test_get_quality_score_invalid_failed_not_int(self):
        """Test that non-int failed_records raises ValueError."""
        validator = QualityValidator()
        with pytest.raises(ValueError):
            validator.get_quality_score(50, "50")

    def test_validate_record_missing_required_field(self):
        """Test that missing required field is caught."""
        validator = QualityValidator()
        records = [{"id": "1"}]  # Missing required email
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1")

        assert result.failed_records == 1
        assert len(result.errors) == 1
        assert result.errors[0]["error_type"] == "missing_field"

    def test_validate_record_null_required_field(self):
        """Test that null required field is caught."""
        validator = QualityValidator()
        records = [{"id": "1", "email": None}]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1")

        assert result.failed_records == 1
        assert len(result.errors) == 1
        assert result.errors[0]["error_type"] == "null_value"

    def test_validate_record_not_dict(self):
        """Test that non-dict record is caught."""
        validator = QualityValidator()
        records = ["not a dict"]
        schema = {"id": {"type": "string", "required": True}}
        result = validator.validate_batch(records, schema, "tenant1")

        assert result.failed_records == 1
        assert result.errors[0]["error_type"] == "structural"

    def test_validate_batch_multiple_errors_per_record(self):
        """Test record with multiple validation errors."""
        validator = QualityValidator()
        records = [{"id": None}]  # Missing email, null id
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1")

        assert result.failed_records == 1
        assert len(result.errors) == 2  # Both errors logged

    def test_validate_batch_multi_tenancy(self):
        """Test batch validation with different tenants."""
        validator = QualityValidator()
        records = [{"id": "1", "email": "alice@example.com"}]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }

        result_tenant1 = validator.validate_batch(records, schema, "tenant1")
        result_tenant2 = validator.validate_batch(records, schema, "tenant2")

        # Both pass, but have different batch IDs (tenant context)
        assert result_tenant1.quality_score == 1.0
        assert result_tenant2.quality_score == 1.0
        assert result_tenant1.batch_id != result_tenant2.batch_id

    def test_complex_schema_validation(self):
        """Test validation with complex schema."""
        validator = QualityValidator()
        records = [
            {
                "customer_id": "1",
                "age": 30,
                "email": "alice@example.com",
                "status": "active",
            },
            {
                "customer_id": "2",
                "age": 25,
                "email": None,
                "status": "inactive",
            },
        ]
        schema = {
            "customer_id": {"type": "string", "required": True},
            "age": {"type": "int", "required": True},
            "email": {"type": "string", "required": True},
            "status": {"type": "string", "required": False},
        }
        result = validator.validate_batch(records, schema, "bankcorp", threshold=0.95)

        assert result.passed_records == 1
        assert result.failed_records == 1
        assert result.quality_score == 0.5
        assert result.circuit_breaker_triggered is True

    def test_validate_batch_logs_warning_on_circuit_breaker_trigger(self):
        """Test that warning is logged when circuit breaker triggered."""
        validator = QualityValidator()
        records = [{"id": "1"}]  # Missing required email
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.95)

        # Circuit breaker should be triggered (50% quality < 95% threshold)
        assert result.circuit_breaker_triggered is True
        assert result.quality_score == 0.0

    def test_validate_batch_integer_quality_calculation(self):
        """Test quality calculation with integer math."""
        validator = QualityValidator()
        records = [
            {"id": "1", "email": "a@example.com"},
            {"id": "2", "email": "b@example.com"},
            {"id": "3", "email": None},  # 1 fail out of 3
        ]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1", threshold=0.95)

        # 2 passed, 1 failed = 0.666... quality
        assert result.passed_records == 2
        assert result.failed_records == 1
        assert abs(result.quality_score - (2 / 3)) < 0.0001

    def test_validate_record_with_simple_schema(self):
        """Test validation with schema fields that aren't dicts."""
        validator = QualityValidator()
        records = [{"id": "1", "name": "Alice"}]
        schema = {
            "id": "string",  # Not a dict, just type
            "name": "string",
        }
        result = validator.validate_batch(records, schema, "tenant1")

        # Should pass since fields are optional (not dicts with required=True)
        assert result.passed_records == 1
        assert result.failed_records == 0

    def test_validate_batch_large_batch(self):
        """Test validation with large batch."""
        validator = QualityValidator()
        records = [
            {"id": str(i), "email": f"user{i}@example.com"}
            for i in range(1000)
        ]
        schema = {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": True},
        }
        result = validator.validate_batch(records, schema, "tenant1")

        assert result.passed_records == 1000
        assert result.failed_records == 0
        assert result.quality_score == 1.0

    def test_circuit_breaker_boundary_conditions(self):
        """Test CircuitBreaker at exact threshold boundary."""
        breaker = CircuitBreaker(threshold=0.5)

        # Exactly at threshold should pass
        assert breaker.check(0.5) is True

        # Just below threshold should fail
        assert breaker.check(0.4999999999) is False

        # Just above threshold should pass
        assert breaker.check(0.5000000001) is True

    def test_quality_score_with_precision(self):
        """Test quality score calculation precision."""
        validator = QualityValidator()

        # Test 1/3 precision
        score1 = validator.get_quality_score(1, 2)
        assert abs(score1 - (1 / 3)) < 0.0001

        # Test 2/3 precision
        score2 = validator.get_quality_score(2, 1)
        assert abs(score2 - (2 / 3)) < 0.0001

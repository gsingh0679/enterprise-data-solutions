"""Quality validation module for the enterprise data platform.

This module provides quality gates for data validation, ensuring that only
high-quality data passes through the pipeline. It includes a two-layer
validation approach (structural + completeness) and a circuit breaker
pattern to fail fast on poor data quality.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchValidationResult:
    """Immutable validation result for a data batch.

    This dataclass holds the validation results for a batch of records,
    including metrics like passed/failed counts and quality score.

    Attributes:
        batch_id (str): Unique identifier for this validation batch.
        passed_records (int): Number of records that passed validation.
        failed_records (int): Number of records that failed validation.
        quality_score (float): Quality score as a percentage (0.0 to 1.0).
        circuit_breaker_triggered (bool): Whether circuit breaker was triggered.
        errors (List[Dict[str, Any]]): List of validation errors with details.

    Raises:
        ValueError: If validation fails during initialization.

    Example:
        >>> result = BatchValidationResult(
        ...     batch_id="batch_001",
        ...     passed_records=95,
        ...     failed_records=5,
        ...     quality_score=0.95,
        ...     circuit_breaker_triggered=False,
        ...     errors=[]
        ... )
    """

    batch_id: str
    passed_records: int
    failed_records: int
    quality_score: float
    circuit_breaker_triggered: bool
    errors: List[Dict[str, Any]]

    def __post_init__(self) -> None:
        """Validate result after initialization.

        Raises:
            ValueError: If any field fails validation.
        """
        self.validate()

    def validate(self) -> None:
        """Validate result invariants.

        Raises:
            ValueError: If quality_score is not between 0.0 and 1.0,
                or if passed/failed records are negative.
        """
        if not isinstance(self.batch_id, str) or not self.batch_id:
            raise ValueError(
                f"batch_id must be a non-empty string, got {self.batch_id!r}"
            )

        if not isinstance(self.passed_records, int) or self.passed_records < 0:
            raise ValueError(
                f"passed_records must be non-negative int, "
                f"got {self.passed_records!r}"
            )

        if not isinstance(self.failed_records, int) or self.failed_records < 0:
            raise ValueError(
                f"failed_records must be non-negative int, "
                f"got {self.failed_records!r}"
            )

        if not isinstance(self.quality_score, float) or not (0.0 <= self.quality_score <= 1.0):
            raise ValueError(
                f"quality_score must be float between 0.0 and 1.0, "
                f"got {self.quality_score!r}"
            )

        if not isinstance(self.circuit_breaker_triggered, bool):
            raise ValueError(
                f"circuit_breaker_triggered must be bool, "
                f"got {type(self.circuit_breaker_triggered).__name__}"
            )

        if not isinstance(self.errors, list):
            raise ValueError(
                f"errors must be list, got {type(self.errors).__name__}"
            )

        logger.info(
            f"Validation result validated: batch_id={self.batch_id}, "
            f"quality_score={self.quality_score:.2%}"
        )


class CircuitBreaker:
    """Safety circuit breaker for quality gates.

    This class implements a circuit breaker pattern to fail fast when data
    quality drops below an acceptable threshold. It prevents bad data from
    being processed further in the pipeline.

    Attributes:
        threshold (float): Quality threshold (0.0 to 1.0). Default is 0.95.

    Example:
        >>> breaker = CircuitBreaker(threshold=0.95)
        >>> if breaker.check(0.98):
        ...     print("Quality is acceptable")
        ... else:
        ...     print("Quality is unacceptable, circuit breaker triggered")
    """

    def __init__(self, threshold: float = 0.95) -> None:
        """Initialize circuit breaker with threshold.

        Args:
            threshold: Quality threshold (0.0 to 1.0). Default is 0.95.

        Raises:
            ValueError: If threshold is not between 0.0 and 1.0.
        """
        if not isinstance(threshold, (int, float)) or not (0.0 <= threshold <= 1.0):
            raise ValueError(
                f"threshold must be between 0.0 and 1.0, got {threshold!r}"
            )
        self.threshold = float(threshold)
        logger.info(f"CircuitBreaker initialized with threshold={self.threshold:.2%}")

    def check(self, quality_score: float) -> bool:
        """Check if quality score passes the circuit breaker.

        Args:
            quality_score: Quality score as float (0.0 to 1.0).

        Returns:
            True if quality_score >= threshold, False otherwise.

        Raises:
            ValueError: If quality_score is not a valid float between 0.0 and 1.0.

        Example:
            >>> breaker = CircuitBreaker(threshold=0.95)
            >>> breaker.check(0.98)
            True
            >>> breaker.check(0.90)
            False
        """
        if not isinstance(quality_score, (int, float)) or not (0.0 <= quality_score <= 1.0):
            raise ValueError(
                f"quality_score must be between 0.0 and 1.0, "
                f"got {quality_score!r}"
            )

        passed = quality_score >= self.threshold
        status = "PASS" if passed else "FAIL"
        logger.info(
            f"CircuitBreaker check: quality_score={quality_score:.2%}, "
            f"threshold={self.threshold:.2%}, result={status}"
        )
        return passed

    def get_threshold(self) -> float:
        """Get the circuit breaker threshold.

        Returns:
            The current threshold value.

        Example:
            >>> breaker = CircuitBreaker(threshold=0.95)
            >>> breaker.get_threshold()
            0.95
        """
        return self.threshold


class QualityValidator:
    """Two-layer data quality validator.

    This class validates data quality through two layers:
    1. Structural validation: Checks that records have expected fields
    2. Completeness validation: Checks that required fields are not null

    The validator calculates a quality score based on the percentage of
    records that pass both validation layers.

    Example:
        >>> validator = QualityValidator()
        >>> records = [
        ...     {"id": "1", "email": "alice@example.com"},
        ...     {"id": "2", "email": None},  # Missing email
        ... ]
        >>> schema = {"id": {"type": "string", "required": True},
        ...           "email": {"type": "string", "required": True}}
        >>> result = validator.validate_batch(records, schema, "tenant1")
    """

    def __init__(self) -> None:
        """Initialize quality validator.

        Example:
            >>> validator = QualityValidator()
        """
        logger.info("QualityValidator initialized")

    def validate_batch(
        self,
        records: List[Dict[str, Any]],
        schema: Dict[str, Any],
        tenant_id: str,
        threshold: float = 0.95,
    ) -> BatchValidationResult:
        """Validate a batch of records against a schema.

        Performs two-layer validation on all records:
        1. Structural: All required fields are present
        2. Completeness: Required fields are not null

        Args:
            records: List of data records to validate.
            schema: Schema definition with field requirements.
            tenant_id: Tenant identifier for multi-tenancy support.
            threshold: Quality threshold (0.0 to 1.0). Default is 0.95.

        Returns:
            BatchValidationResult with validation metrics.

        Raises:
            ValueError: If inputs are invalid.

        Example:
            >>> validator = QualityValidator()
            >>> records = [
            ...     {"id": "1", "email": "alice@example.com"},
            ...     {"id": "2", "email": None},
            ... ]
            >>> schema = {
            ...     "id": {"type": "string", "required": True},
            ...     "email": {"type": "string", "required": True}
            ... }
            >>> result = validator.validate_batch(records, schema, "tenant1")
            >>> print(f"Quality: {result.quality_score:.2%}")
        """
        if not isinstance(records, list):
            raise ValueError(
                f"records must be list, got {type(records).__name__}"
            )

        if not isinstance(schema, dict) or not schema:
            raise ValueError(
                f"schema must be non-empty dict, got {type(schema).__name__}"
            )

        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError(
                f"tenant_id must be non-empty string, got {tenant_id!r}"
            )

        if not isinstance(threshold, (int, float)) or not (0.0 <= threshold <= 1.0):
            raise ValueError(
                f"threshold must be between 0.0 and 1.0, got {threshold!r}"
            )

        batch_id = str(uuid4())
        passed_records = 0
        failed_records = 0
        errors: List[Dict[str, Any]] = []

        logger.info(
            f"Starting batch validation: batch_id={batch_id}, "
            f"tenant_id={tenant_id}, record_count={len(records)}"
        )

        for idx, record in enumerate(records):
            record_errors = self._validate_record(record, schema, idx)
            if record_errors:
                failed_records += 1
                errors.extend(record_errors)
            else:
                passed_records += 1

        # Calculate quality score
        total_records = passed_records + failed_records
        quality_score = (
            passed_records / total_records if total_records > 0 else 0.0
        )

        # Check circuit breaker
        breaker = CircuitBreaker(threshold=threshold)
        circuit_breaker_triggered = not breaker.check(quality_score)

        result = BatchValidationResult(
            batch_id=batch_id,
            passed_records=passed_records,
            failed_records=failed_records,
            quality_score=quality_score,
            circuit_breaker_triggered=circuit_breaker_triggered,
            errors=errors,
        )

        log_level = "warning" if circuit_breaker_triggered else "info"
        log_msg = (
            f"Batch validation completed: batch_id={batch_id}, "
            f"passed={passed_records}, failed={failed_records}, "
            f"quality={quality_score:.2%}, "
            f"circuit_breaker_triggered={circuit_breaker_triggered}"
        )
        if log_level == "warning":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return result

    def _validate_record(
        self, record: Dict[str, Any], schema: Dict[str, Any], record_idx: int
    ) -> List[Dict[str, Any]]:
        """Validate a single record against schema.

        Performs structural and completeness validation.

        Args:
            record: Record to validate.
            schema: Schema definition.
            record_idx: Index of record in batch (for error reporting).

        Returns:
            List of errors (empty if record is valid).
        """
        errors: List[Dict[str, Any]] = []

        # Structural validation
        if not isinstance(record, dict):
            errors.append({
                "record_index": record_idx,
                "error_type": "structural",
                "message": f"Record must be dict, got {type(record).__name__}"
            })
            return errors

        # Completeness validation
        for field_name, field_def in schema.items():
            if isinstance(field_def, dict):
                required = field_def.get("required", False)
            else:
                required = False

            if field_name not in record:
                if required:
                    errors.append({
                        "record_index": record_idx,
                        "field": field_name,
                        "error_type": "missing_field",
                        "message": f"Required field missing: {field_name}"
                    })
            elif record[field_name] is None:
                if required:
                    errors.append({
                        "record_index": record_idx,
                        "field": field_name,
                        "error_type": "null_value",
                        "message": f"Required field is null: {field_name}"
                    })

        return errors

    def get_quality_score(
        self, passed_records: int, failed_records: int
    ) -> float:
        """Calculate quality score from passed/failed counts.

        Args:
            passed_records: Number of records that passed validation.
            failed_records: Number of records that failed validation.

        Returns:
            Quality score as float (0.0 to 1.0).

        Raises:
            ValueError: If record counts are negative.

        Example:
            >>> validator = QualityValidator()
            >>> score = validator.get_quality_score(95, 5)
            >>> print(f"Quality: {score:.2%}")
            Quality: 95.00%
        """
        if not isinstance(passed_records, int) or passed_records < 0:
            raise ValueError(
                f"passed_records must be non-negative int, "
                f"got {passed_records!r}"
            )

        if not isinstance(failed_records, int) or failed_records < 0:
            raise ValueError(
                f"failed_records must be non-negative int, "
                f"got {failed_records!r}"
            )

        total = passed_records + failed_records
        if total == 0:
            return 0.0

        quality_score = passed_records / total
        logger.debug(
            f"Quality score calculated: passed={passed_records}, "
            f"failed={failed_records}, score={quality_score:.2%}"
        )
        return quality_score


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    validator = QualityValidator()

    # Example schema
    schema = {
        "customer_id": {"type": "string", "required": True},
        "age": {"type": "int", "required": True},
        "email": {"type": "string", "required": True},
    }

    # Example records
    records = [
        {"customer_id": "1", "age": 30, "email": "alice@example.com"},
        {"customer_id": "2", "age": 25, "email": None},  # Missing email
        {"customer_id": "3", "age": "invalid", "email": "bob@example.com"},
    ]

    try:
        result = validator.validate_batch(records, schema, "bankcorp", threshold=0.95)
        print(f"Quality: {result.quality_score:.2%}")
        print(f"Passed: {result.passed_records}, Failed: {result.failed_records}")
        print(f"Circuit breaker triggered: {result.circuit_breaker_triggered}")
        print(f"Errors: {result.errors}")
    except Exception as e:
        print(f"Error: {e}")

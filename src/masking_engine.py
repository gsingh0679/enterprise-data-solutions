"""Data masking engine for protecting sensitive information.

This module provides a masking engine for hiding sensitive banking data
(SSN, email, credit cards) in records using three strategies: HASH,
TOKENIZE, and REDACT. The engine works with the schema registry to apply
field-level masking strategies.
"""

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict
from uuid import uuid4

from .schema_registry import Schema

logger = logging.getLogger(__name__)


class MaskingStrategy(Enum):
    """Enum for supported masking strategies.

    Attributes:
        HASH: One-way hash using SHA256 (deterministic, non-reversible).
        TOKENIZE: Replace with a unique token (reversible via vault, Phase 2).
        REDACT: Replace with a placeholder string.
    """

    HASH = "hash"
    TOKENIZE = "tokenize"
    REDACT = "redact"


@dataclass(frozen=True)
class FieldMaskingConfig:
    """Immutable field-level masking configuration.

    This dataclass holds the masking strategy and metadata for a single field.

    Attributes:
        field_name (str): Name of the field to mask.
        strategy (MaskingStrategy): Masking strategy to apply.
        include_in_hash (bool): Whether to include field name in hash seed.
            Defaults to True for consistent field-based hashing.

    Raises:
        ValueError: If validation fails during initialization.
    """

    field_name: str
    strategy: MaskingStrategy
    include_in_hash: bool = True

    def __post_init__(self) -> None:
        """Validate config after initialization.

        Raises:
            ValueError: If any field fails validation.
        """
        self.validate()

    def validate(self) -> None:
        """Validate configuration invariants.

        Raises:
            ValueError: If field_name is empty or strategy is invalid.
        """
        if not self.field_name or not isinstance(self.field_name, str):
            raise ValueError(
                f"field_name must be a non-empty string, got {self.field_name!r}"
            )

        if not isinstance(self.strategy, MaskingStrategy):
            raise ValueError(
                f"strategy must be MaskingStrategy, got {type(self.strategy).__name__}"
            )

        if not isinstance(self.include_in_hash, bool):
            raise ValueError(
                f"include_in_hash must be bool, got {type(self.include_in_hash).__name__}"
            )

        logger.debug(f"FieldMaskingConfig validated: {self.field_name}")


class MaskingEngine:
    """Engine for masking sensitive data in records.

    This class applies masking strategies to record fields based on schema
    definitions. It supports three strategies: HASH (one-way), TOKENIZE
    (reversible via vault), and REDACT (placeholder).

    Attributes:
        token_cache (Dict[str, str]): In-memory cache for tokenization
            (Phase 1 only; Phase 2 uses vault.py).

    Example:
        >>> from schema_registry import Schema
        >>> engine = MaskingEngine()
        >>> schema = Schema(
        ...     schema_id="user_v1",
        ...     name="User",
        ...     version="1.0",
        ...     fields={
        ...         "id": {"type": "string"},
        ...         "email": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
        ...         "ssn": {"type": "string", "sensitive": True, "masking_strategy": "redact"}
        ...     }
        ... )
        >>> record = {"id": "user_123", "email": "john@example.com", "ssn": "123-45-6789"}
        >>> masked = engine.mask_record(record, schema)
    """

    def __init__(self) -> None:
        """Initialize masking engine.

        Sets up token cache for tokenization strategy (Phase 1).
        """
        self.token_cache: Dict[str, str] = {}
        logger.info("MaskingEngine initialized")

    def mask_record(self, record: Dict[str, Any], schema: Schema) -> Dict[str, Any]:
        """Apply masking to record fields based on schema.

        Iterates through record fields and applies masking strategies defined
        in the schema. Returns a new dictionary with masked values, leaving
        the original record unchanged (immutable).

        Args:
            record: The data record to mask (dict).
            schema: The Schema defining masking strategies for fields.

        Returns:
            New dictionary with masked values for sensitive fields.

        Raises:
            TypeError: If record is not a dict or schema is not Schema.
            ValueError: If masking strategy in schema is invalid.

        Example:
            >>> schema = Schema(
            ...     schema_id="user_v1",
            ...     name="User",
            ...     version="1.0",
            ...     fields={
            ...         "email": {"type": "string", "masking_strategy": "hash"}
            ...     }
            ... )
            >>> record = {"email": "user@example.com"}
            >>> masked = engine.mask_record(record, schema)
        """
        if not isinstance(record, dict):
            raise TypeError(
                f"record must be a dict, got {type(record).__name__}"
            )

        if not isinstance(schema, Schema):
            raise TypeError(
                f"schema must be Schema instance, got {type(schema).__name__}"
            )

        masked_record = {}

        for field_name, field_value in record.items():
            field_def = schema.fields.get(field_name, {})

            # If field is not in schema or doesn't require masking, pass through
            if not field_def.get("sensitive", False):
                masked_record[field_name] = field_value
                continue

            # Get masking strategy from field definition
            strategy_str = field_def.get("masking_strategy", "redact").lower()

            try:
                strategy = MaskingStrategy(strategy_str)
            except ValueError:
                logger.warning(
                    f"Invalid masking strategy '{strategy_str}' for field '{field_name}', "
                    f"defaulting to REDACT"
                )
                strategy = MaskingStrategy.REDACT

            # Apply masking strategy
            masked_value = self.apply_masking_strategy(
                field_value, strategy, field_name
            )
            masked_record[field_name] = masked_value

        logger.debug(
            f"Record masked successfully for schema {schema.schema_id}, "
            f"masked {len([f for f in record.keys() if schema.fields.get(f, {}).get('sensitive')])} fields"
        )

        return masked_record

    def apply_masking_strategy(
        self,
        value: Any,
        strategy: MaskingStrategy,
        field_name: str = "",
    ) -> Any:
        """Apply a masking strategy to a value.

        Handles None and null values gracefully by returning them as-is.
        Applies one of three strategies: HASH, TOKENIZE, or REDACT.

        Args:
            value: The value to mask.
            strategy: The MaskingStrategy to apply.
            field_name: Name of the field (optional, used for hash seed).

        Returns:
            Masked value (or original if None/null, or unsupported type).

        Raises:
            ValueError: If strategy is invalid.

        Example:
            >>> engine = MaskingEngine()
            >>> # HASH strategy
            >>> hashed = engine.apply_masking_strategy(
            ...     "user@example.com",
            ...     MaskingStrategy.HASH,
            ...     "email"
            ... )
            >>> # TOKENIZE strategy
            >>> token = engine.apply_masking_strategy(
            ...     "123-45-6789",
            ...     MaskingStrategy.TOKENIZE,
            ...     "ssn"
            ... )
            >>> # REDACT strategy
            >>> redacted = engine.apply_masking_strategy(
            ...     "4532-1234-5678-9010",
            ...     MaskingStrategy.REDACT,
            ...     "credit_card"
            ... )
        """
        # Handle None and null-like values
        if value is None or (isinstance(value, str) and value.lower() == "null"):
            logger.debug(
                f"Null value encountered for field '{field_name}', returning as-is"
            )
            return value

        # Handle empty strings
        if isinstance(value, str) and not value:
            return value

        if strategy == MaskingStrategy.HASH:
            return self._apply_hash(value, field_name)
        elif strategy == MaskingStrategy.TOKENIZE:
            return self._apply_tokenize(value, field_name)
        elif strategy == MaskingStrategy.REDACT:
            return self._apply_redact(value)
        else:
            raise ValueError(
                f"Unknown masking strategy: {strategy}"
            )

    def _apply_hash(self, value: Any, field_name: str = "") -> str:
        """Apply SHA256 hash strategy (one-way, deterministic).

        Converts value to string and applies SHA256 hash. Field name can be
        included in hash seed for field-specific hashing consistency.

        Args:
            value: Value to hash (will be converted to string).
            field_name: Optional field name to include in hash seed.

        Returns:
            Hex-encoded SHA256 hash string.
        """
        if not isinstance(value, (str, int, float, bool)):
            # For complex types, convert to string representation
            value_str = str(value)
        else:
            value_str = str(value)

        # Create hash seed with optional field name
        hash_seed = f"{field_name}:{value_str}" if field_name else value_str

        hash_result = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()

        logger.debug(
            f"Value hashed for field '{field_name}': "
            f"{value_str[:20]}... -> {hash_result[:16]}..."
        )

        return hash_result

    def _apply_tokenize(self, value: Any, field_name: str = "") -> str:
        """Apply tokenize strategy (reversible via vault).

        In Phase 1, uses in-memory token cache. Phase 2 will integrate
        with vault.py for secure token storage.

        Args:
            value: Value to tokenize (will be converted to string).
            field_name: Optional field name for tracking.

        Returns:
            Unique token string (prefix: token_).
        """
        value_str = str(value) if not isinstance(value, str) else value

        # Check if already tokenized
        if value_str in self.token_cache:
            token = self.token_cache[value_str]
            logger.debug(
                f"Token retrieved from cache for field '{field_name}': "
                f"{value_str[:20]}... -> {token}"
            )
            return token

        # Generate new token
        token = f"token_{uuid4().hex[:16]}"
        self.token_cache[value_str] = token

        logger.debug(
            f"Token generated for field '{field_name}': "
            f"{value_str[:20]}... -> {token}"
        )

        return token

    def _apply_redact(self, _value: Any) -> str:
        """Apply redact strategy (placeholder).

        Replaces any value with a standard redaction placeholder.

        Args:
            _value: Value to redact (ignored).

        Returns:
            Redaction placeholder string.
        """
        logger.debug("Value redacted: *** -> ***REDACTED***")
        return "***REDACTED***"

    def clear_token_cache(self) -> None:
        """Clear the token cache.

        Useful for testing or when rotating tokens. In production, tokens
        should be managed by vault.py (Phase 2).

        Example:
            >>> engine = MaskingEngine()
            >>> engine.apply_masking_strategy("secret", MaskingStrategy.TOKENIZE)
            >>> engine.clear_token_cache()
        """
        cache_size = len(self.token_cache)
        self.token_cache.clear()
        logger.info(f"Token cache cleared ({cache_size} entries removed)")

    def get_token_count(self) -> int:
        """Get the number of tokens in cache.

        Returns:
            Number of tokenized values currently cached.

        Example:
            >>> engine = MaskingEngine()
            >>> count = engine.get_token_count()
        """
        return len(self.token_cache)


def example_banking_masking() -> tuple[dict, dict, int]:
    """Example: Masking banking records with PII protection.

    Demonstrates masking a banking record with multiple sensitive fields
    using different strategies (HASH, TOKENIZE, REDACT).

    Returns:
        Tuple of (original_record, masked_record, token_count)
    """
    from .schema_registry import SchemaRegistry

    engine = MaskingEngine()
    registry = SchemaRegistry()

    # Register a test schema
    user_schema = Schema(
        schema_id="user_banking_v1",
        name="User Banking",
        version="1.0",
        fields={
            "id": {"type": "string", "sensitive": False},
            "name": {"type": "string", "sensitive": False},
            "email": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            "ssn": {"type": "string", "sensitive": True, "masking_strategy": "redact"},
            "credit_card": {
                "type": "string",
                "sensitive": True,
                "masking_strategy": "tokenize",
            },
        },
        description="User banking information with PII",
    )
    registry.register(user_schema)

    # Test masking
    record = {
        "id": "user_001",
        "name": "John Doe",
        "email": "john@example.com",
        "ssn": "123-45-6789",
        "credit_card": "4532-1234-5678-9010",
    }

    masked_record = engine.mask_record(record, user_schema)
    token_count = engine.get_token_count()

    return record, masked_record, token_count


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    original, masked, token_count = example_banking_masking()

    print("Original record:")
    print(original)
    print("\nMasked record:")
    print(masked)
    print(f"\nTokens in cache: {token_count}")

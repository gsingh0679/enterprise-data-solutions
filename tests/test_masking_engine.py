"""Comprehensive tests for the masking engine module.

Tests cover all three masking strategies (HASH, TOKENIZE, REDACT), null value
handling, edge cases, and error conditions. Target coverage: 95%+.
"""

import hashlib
import logging
import pytest
from typing import Any, Dict

from src.masking_engine import (
    FieldMaskingConfig,
    MaskingEngine,
    MaskingStrategy,
)
from src.schema_registry import Schema, SchemaRegistry

logger = logging.getLogger(__name__)


class TestMaskingStrategy:
    """Tests for MaskingStrategy enum."""

    def test_hash_strategy_value(self) -> None:
        """Test HASH strategy enum value."""
        assert MaskingStrategy.HASH.value == "hash"

    def test_tokenize_strategy_value(self) -> None:
        """Test TOKENIZE strategy enum value."""
        assert MaskingStrategy.TOKENIZE.value == "tokenize"

    def test_redact_strategy_value(self) -> None:
        """Test REDACT strategy enum value."""
        assert MaskingStrategy.REDACT.value == "redact"

    def test_strategy_comparison(self) -> None:
        """Test comparing strategies."""
        assert MaskingStrategy.HASH != MaskingStrategy.TOKENIZE
        assert MaskingStrategy.HASH == MaskingStrategy.HASH

    def test_strategy_from_value(self) -> None:
        """Test creating strategy from string value."""
        assert MaskingStrategy("hash") == MaskingStrategy.HASH
        assert MaskingStrategy("tokenize") == MaskingStrategy.TOKENIZE
        assert MaskingStrategy("redact") == MaskingStrategy.REDACT

    def test_strategy_from_invalid_value(self) -> None:
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            MaskingStrategy("invalid_strategy")


class TestFieldMaskingConfig:
    """Tests for FieldMaskingConfig dataclass."""

    def test_valid_config_creation(self) -> None:
        """Test creating valid field masking config."""
        config = FieldMaskingConfig(
            field_name="email",
            strategy=MaskingStrategy.HASH,
            include_in_hash=True,
        )
        assert config.field_name == "email"
        assert config.strategy == MaskingStrategy.HASH
        assert config.include_in_hash is True

    def test_config_defaults(self) -> None:
        """Test config defaults."""
        config = FieldMaskingConfig(
            field_name="ssn",
            strategy=MaskingStrategy.REDACT,
        )
        assert config.include_in_hash is True

    def test_config_immutable(self) -> None:
        """Test that config is frozen/immutable."""
        config = FieldMaskingConfig(
            field_name="email",
            strategy=MaskingStrategy.HASH,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            config.field_name = "new_email"

    def test_config_empty_field_name(self) -> None:
        """Test that empty field_name raises ValueError."""
        with pytest.raises(ValueError, match="field_name must be a non-empty string"):
            FieldMaskingConfig(
                field_name="",
                strategy=MaskingStrategy.HASH,
            )

    def test_config_none_field_name(self) -> None:
        """Test that None field_name raises ValueError."""
        with pytest.raises(ValueError, match="field_name must be a non-empty string"):
            FieldMaskingConfig(
                field_name=None,  # type: ignore
                strategy=MaskingStrategy.HASH,
            )

    def test_config_non_string_field_name(self) -> None:
        """Test that non-string field_name raises ValueError."""
        with pytest.raises(ValueError, match="field_name must be a non-empty string"):
            FieldMaskingConfig(
                field_name=123,  # type: ignore
                strategy=MaskingStrategy.HASH,
            )

    def test_config_invalid_strategy(self) -> None:
        """Test that invalid strategy raises ValueError."""
        with pytest.raises(ValueError, match="strategy must be MaskingStrategy"):
            FieldMaskingConfig(
                field_name="email",
                strategy="invalid",  # type: ignore
            )

    def test_config_invalid_include_in_hash_type(self) -> None:
        """Test that non-bool include_in_hash raises ValueError."""
        with pytest.raises(ValueError, match="include_in_hash must be bool"):
            FieldMaskingConfig(
                field_name="email",
                strategy=MaskingStrategy.HASH,
                include_in_hash="true",  # type: ignore
            )


class TestMaskingEngineInit:
    """Tests for MaskingEngine initialization."""

    def test_engine_initialization(self) -> None:
        """Test engine initializes with empty token cache."""
        engine = MaskingEngine()
        assert engine.token_cache == {}
        assert engine.get_token_count() == 0

    def test_multiple_engine_instances(self) -> None:
        """Test multiple engine instances have separate token caches."""
        engine1 = MaskingEngine()
        engine2 = MaskingEngine()
        assert engine1.token_cache is not engine2.token_cache


class TestApplyHashStrategy:
    """Tests for HASH masking strategy."""

    def test_hash_string_value(self) -> None:
        """Test hashing string value."""
        engine = MaskingEngine()
        value = "user@example.com"
        hashed = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "email"
        )
        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA256 hex is 64 chars
        assert hashed.lower() == hashed  # Hex is lowercase

    def test_hash_deterministic(self) -> None:
        """Test that hashing same value produces same hash."""
        engine = MaskingEngine()
        value = "test@example.com"
        hash1 = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "email"
        )
        hash2 = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "email"
        )
        assert hash1 == hash2

    def test_hash_different_values_produce_different_hashes(self) -> None:
        """Test that different values produce different hashes."""
        engine = MaskingEngine()
        hash1 = engine.apply_masking_strategy(
            "user1@example.com", MaskingStrategy.HASH, "email"
        )
        hash2 = engine.apply_masking_strategy(
            "user2@example.com", MaskingStrategy.HASH, "email"
        )
        assert hash1 != hash2

    def test_hash_includes_field_name_in_seed(self) -> None:
        """Test that field name affects hash value."""
        engine = MaskingEngine()
        value = "sensitive_data"
        hash_with_field = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "field1"
        )
        hash_different_field = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "field2"
        )
        assert hash_with_field != hash_different_field

    def test_hash_integer_value(self) -> None:
        """Test hashing integer value."""
        engine = MaskingEngine()
        hashed = engine.apply_masking_strategy(
            12345, MaskingStrategy.HASH, "numeric_id"
        )
        assert isinstance(hashed, str)
        assert len(hashed) == 64

    def test_hash_float_value(self) -> None:
        """Test hashing float value."""
        engine = MaskingEngine()
        hashed = engine.apply_masking_strategy(
            123.45, MaskingStrategy.HASH, "amount"
        )
        assert isinstance(hashed, str)
        assert len(hashed) == 64

    def test_hash_boolean_value(self) -> None:
        """Test hashing boolean value."""
        engine = MaskingEngine()
        hashed = engine.apply_masking_strategy(
            True, MaskingStrategy.HASH, "flag"
        )
        assert isinstance(hashed, str)
        assert len(hashed) == 64

    def test_hash_without_field_name(self) -> None:
        """Test hashing without field name."""
        engine = MaskingEngine()
        hashed = engine.apply_masking_strategy(
            "value", MaskingStrategy.HASH
        )
        assert isinstance(hashed, str)
        assert len(hashed) == 64

    def test_hash_matches_expected_sha256(self) -> None:
        """Test that hash matches expected SHA256."""
        engine = MaskingEngine()
        value = "test123"
        hashed = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "test_field"
        )
        expected = hashlib.sha256("test_field:test123".encode()).hexdigest()
        assert hashed == expected

    def test_hash_complex_dict_value(self) -> None:
        """Test hashing complex dict value."""
        engine = MaskingEngine()
        value = {"key": "value", "nested": {"inner": "data"}}
        hashed = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "complex"
        )
        assert isinstance(hashed, str)
        assert len(hashed) == 64

    def test_hash_complex_list_value(self) -> None:
        """Test hashing complex list value."""
        engine = MaskingEngine()
        value = [1, 2, 3, "four", {"five": 5}]
        hashed = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "list_field"
        )
        assert isinstance(hashed, str)
        assert len(hashed) == 64

    def test_hash_complex_tuple_value(self) -> None:
        """Test hashing complex tuple value."""
        engine = MaskingEngine()
        value = (1, 2, 3)
        hashed = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, "tuple_field"
        )
        assert isinstance(hashed, str)
        assert len(hashed) == 64


class TestApplyTokenizeStrategy:
    """Tests for TOKENIZE masking strategy."""

    def test_tokenize_string_value(self) -> None:
        """Test tokenizing string value."""
        engine = MaskingEngine()
        token = engine.apply_masking_strategy(
            "sensitive_data", MaskingStrategy.TOKENIZE, "field"
        )
        assert isinstance(token, str)
        assert token.startswith("token_")
        assert len(token) == 22  # "token_" (6) + 16 hex chars

    def test_tokenize_creates_unique_tokens(self) -> None:
        """Test that different values get different tokens."""
        engine = MaskingEngine()
        token1 = engine.apply_masking_strategy(
            "data1", MaskingStrategy.TOKENIZE, "field"
        )
        token2 = engine.apply_masking_strategy(
            "data2", MaskingStrategy.TOKENIZE, "field"
        )
        assert token1 != token2

    def test_tokenize_same_value_returns_same_token(self) -> None:
        """Test that same value returns cached token."""
        engine = MaskingEngine()
        value = "credit_card_number"
        token1 = engine.apply_masking_strategy(
            value, MaskingStrategy.TOKENIZE, "credit_card"
        )
        token2 = engine.apply_masking_strategy(
            value, MaskingStrategy.TOKENIZE, "credit_card"
        )
        assert token1 == token2
        assert engine.get_token_count() == 1

    def test_tokenize_integer_value(self) -> None:
        """Test tokenizing integer value."""
        engine = MaskingEngine()
        token = engine.apply_masking_strategy(
            9876543210, MaskingStrategy.TOKENIZE, "ssn"
        )
        assert token.startswith("token_")
        assert len(token) == 22

    def test_tokenize_caches_tokens(self) -> None:
        """Test that tokens are cached for later retrieval."""
        engine = MaskingEngine()
        value = "test_data"
        engine.apply_masking_strategy(
            value, MaskingStrategy.TOKENIZE, "field"
        )
        engine.apply_masking_strategy(
            value, MaskingStrategy.TOKENIZE, "field"
        )
        assert engine.get_token_count() == 1

    def test_tokenize_without_field_name(self) -> None:
        """Test tokenizing without field name."""
        engine = MaskingEngine()
        token = engine.apply_masking_strategy(
            "data", MaskingStrategy.TOKENIZE
        )
        assert token.startswith("token_")

    def test_clear_token_cache(self) -> None:
        """Test clearing token cache."""
        engine = MaskingEngine()
        engine.apply_masking_strategy(
            "data1", MaskingStrategy.TOKENIZE, "field"
        )
        engine.apply_masking_strategy(
            "data2", MaskingStrategy.TOKENIZE, "field"
        )
        assert engine.get_token_count() == 2
        engine.clear_token_cache()
        assert engine.get_token_count() == 0

    def test_tokenize_after_cache_clear(self) -> None:
        """Test that same value gets new token after cache clear."""
        engine = MaskingEngine()
        value = "persistent_data"
        token1 = engine.apply_masking_strategy(
            value, MaskingStrategy.TOKENIZE, "field"
        )
        engine.clear_token_cache()
        token2 = engine.apply_masking_strategy(
            value, MaskingStrategy.TOKENIZE, "field"
        )
        assert token1 != token2


class TestApplyRedactStrategy:
    """Tests for REDACT masking strategy."""

    def test_redact_string_value(self) -> None:
        """Test redacting string value."""
        engine = MaskingEngine()
        redacted = engine.apply_masking_strategy(
            "sensitive_data", MaskingStrategy.REDACT, "field"
        )
        assert redacted == "***REDACTED***"

    def test_redact_integer_value(self) -> None:
        """Test redacting integer value."""
        engine = MaskingEngine()
        redacted = engine.apply_masking_strategy(
            12345, MaskingStrategy.REDACT, "numeric_field"
        )
        assert redacted == "***REDACTED***"

    def test_redact_ignores_input_value(self) -> None:
        """Test that redact ignores the actual value."""
        engine = MaskingEngine()
        redact1 = engine.apply_masking_strategy(
            "value1", MaskingStrategy.REDACT
        )
        redact2 = engine.apply_masking_strategy(
            "value2", MaskingStrategy.REDACT
        )
        assert redact1 == redact2 == "***REDACTED***"

    def test_redact_without_field_name(self) -> None:
        """Test redacting without field name."""
        engine = MaskingEngine()
        redacted = engine.apply_masking_strategy(
            "data", MaskingStrategy.REDACT
        )
        assert redacted == "***REDACTED***"


class TestNullValueHandling:
    """Tests for handling None and null values."""

    def test_hash_none_value(self) -> None:
        """Test that None value is returned as-is for HASH."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            None, MaskingStrategy.HASH, "field"
        )
        assert result is None

    def test_tokenize_none_value(self) -> None:
        """Test that None value is returned as-is for TOKENIZE."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            None, MaskingStrategy.TOKENIZE, "field"
        )
        assert result is None

    def test_redact_none_value(self) -> None:
        """Test that None value is returned as-is for REDACT."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            None, MaskingStrategy.REDACT, "field"
        )
        assert result is None

    def test_hash_null_string(self) -> None:
        """Test that 'null' string is returned as-is for HASH."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            "null", MaskingStrategy.HASH, "field"
        )
        assert result == "null"

    def test_tokenize_null_string(self) -> None:
        """Test that 'null' string is returned as-is for TOKENIZE."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            "null", MaskingStrategy.TOKENIZE, "field"
        )
        assert result == "null"

    def test_redact_null_string(self) -> None:
        """Test that 'null' string is returned as-is for REDACT."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            "null", MaskingStrategy.REDACT, "field"
        )
        assert result == "null"

    def test_hash_empty_string(self) -> None:
        """Test that empty string is returned as-is for HASH."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            "", MaskingStrategy.HASH, "field"
        )
        assert result == ""

    def test_tokenize_empty_string(self) -> None:
        """Test that empty string is returned as-is for TOKENIZE."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            "", MaskingStrategy.TOKENIZE, "field"
        )
        assert result == ""

    def test_redact_empty_string(self) -> None:
        """Test that empty string is returned as-is for REDACT."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            "", MaskingStrategy.REDACT, "field"
        )
        assert result == ""

    def test_hash_null_uppercase_string(self) -> None:
        """Test that 'NULL' (uppercase) is treated as null."""
        engine = MaskingEngine()
        result = engine.apply_masking_strategy(
            "NULL", MaskingStrategy.HASH, "field"
        )
        assert result == "NULL"

    def test_mask_record_with_null_sensitive_field(self) -> None:
        """Test masking record with null sensitive field."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "email": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"id": "123", "email": None}
        masked = engine.mask_record(record, schema)
        assert masked["email"] is None
        assert masked["id"] == "123"


class TestMaskRecord:
    """Tests for mask_record method."""

    def test_mask_record_hash_strategy(self) -> None:
        """Test masking record with HASH strategy."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "email": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"id": "user_123", "email": "user@example.com"}
        masked = engine.mask_record(record, schema)
        assert masked["id"] == "user_123"
        assert masked["email"] != "user@example.com"
        assert len(masked["email"]) == 64

    def test_mask_record_tokenize_strategy(self) -> None:
        """Test masking record with TOKENIZE strategy."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "credit_card": {
                    "type": "string",
                    "sensitive": True,
                    "masking_strategy": "tokenize",
                },
            },
        )
        record = {"id": "user_123", "credit_card": "4532-1234-5678-9010"}
        masked = engine.mask_record(record, schema)
        assert masked["id"] == "user_123"
        assert masked["credit_card"].startswith("token_")

    def test_mask_record_redact_strategy(self) -> None:
        """Test masking record with REDACT strategy."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "ssn": {"type": "string", "sensitive": True, "masking_strategy": "redact"},
            },
        )
        record = {"id": "user_123", "ssn": "123-45-6789"}
        masked = engine.mask_record(record, schema)
        assert masked["id"] == "user_123"
        assert masked["ssn"] == "***REDACTED***"

    def test_mask_record_mixed_strategies(self) -> None:
        """Test masking record with mixed strategies."""
        engine = MaskingEngine()
        schema = Schema(
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
        )
        record = {
            "customer_id": "cust_001",
            "email": "john@example.com",
            "ssn": "123-45-6789",
            "credit_card": "4532-1234-5678-9010",
        }
        masked = engine.mask_record(record, schema)
        assert masked["customer_id"] == "cust_001"
        assert len(masked["email"]) == 64
        assert masked["ssn"] == "***REDACTED***"
        assert masked["credit_card"].startswith("token_")

    def test_mask_record_no_sensitive_fields(self) -> None:
        """Test masking record with no sensitive fields."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="public_v1",
            name="Public",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "name": {"type": "string", "sensitive": False},
            },
        )
        record = {"id": "123", "name": "John"}
        masked = engine.mask_record(record, schema)
        assert masked == record

    def test_mask_record_field_not_in_schema(self) -> None:
        """Test masking record with field not in schema."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="partial_v1",
            name="Partial",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
            },
        )
        record = {"id": "123", "extra_field": "value"}
        masked = engine.mask_record(record, schema)
        assert masked["id"] == "123"
        assert masked["extra_field"] == "value"

    def test_mask_record_invalid_strategy_defaults_to_redact(self) -> None:
        """Test that invalid strategy defaults to REDACT."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="invalid_v1",
            name="Invalid",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "secret": {
                    "type": "string",
                    "sensitive": True,
                    "masking_strategy": "invalid_strategy",
                },
            },
        )
        record = {"id": "123", "secret": "value"}
        masked = engine.mask_record(record, schema)
        assert masked["secret"] == "***REDACTED***"

    def test_mask_record_immutable(self) -> None:
        """Test that masking doesn't modify original record."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "email": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"email": "user@example.com"}
        original_value = record["email"]
        masked = engine.mask_record(record, schema)
        assert record["email"] == original_value
        assert masked["email"] != original_value

    def test_mask_record_returns_new_dict(self) -> None:
        """Test that mask_record returns new dictionary."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "data": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"data": "value"}
        masked = engine.mask_record(record, schema)
        assert masked is not record

    def test_mask_record_invalid_record_type(self) -> None:
        """Test that non-dict record raises TypeError."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={"id": {"type": "string"}},
        )
        with pytest.raises(TypeError, match="record must be a dict"):
            engine.mask_record("not_a_dict", schema)  # type: ignore

    def test_mask_record_invalid_schema_type(self) -> None:
        """Test that non-Schema schema raises TypeError."""
        engine = MaskingEngine()
        record = {"id": "123"}
        with pytest.raises(TypeError, match="schema must be Schema instance"):
            engine.mask_record(record, {"id": {"type": "string"}})  # type: ignore

    def test_mask_record_empty_record(self) -> None:
        """Test masking empty record."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={"id": {"type": "string", "sensitive": False}},
        )
        record: Dict[str, Any] = {}
        masked = engine.mask_record(record, schema)
        assert masked == {}

    def test_mask_record_with_complex_types(self) -> None:
        """Test masking record with complex data types."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="complex_v1",
            name="Complex",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "metadata": {"type": "dict", "sensitive": True, "masking_strategy": "redact"},
            },
        )
        record = {"id": "123", "metadata": {"key": "value"}}
        masked = engine.mask_record(record, schema)
        assert masked["metadata"] == "***REDACTED***"

    def test_mask_record_preserves_order(self) -> None:
        """Test that masking preserves field order."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="order_v1",
            name="Order",
            version="1.0",
            fields={
                "a": {"type": "string", "sensitive": False},
                "b": {"type": "string", "sensitive": False},
                "c": {"type": "string", "sensitive": False},
            },
        )
        record = {"a": "1", "b": "2", "c": "3"}
        masked = engine.mask_record(record, schema)
        assert list(masked.keys()) == ["a", "b", "c"]


class TestApplyMaskingStrategyErrors:
    """Tests for error handling in apply_masking_strategy."""

    def test_apply_invalid_strategy_type(self) -> None:
        """Test that invalid strategy type raises ValueError."""
        engine = MaskingEngine()
        with pytest.raises(ValueError, match="Unknown masking strategy"):
            engine.apply_masking_strategy("value", "invalid")  # type: ignore

    def test_apply_masking_with_all_strategy_types(self) -> None:
        """Test apply_masking_strategy with all enum values."""
        engine = MaskingEngine()
        value = "test_data"

        # Test each strategy can be applied
        result_hash = engine.apply_masking_strategy(value, MaskingStrategy.HASH)
        result_tokenize = engine.apply_masking_strategy(value, MaskingStrategy.TOKENIZE)
        result_redact = engine.apply_masking_strategy(value, MaskingStrategy.REDACT)

        assert isinstance(result_hash, str)
        assert isinstance(result_tokenize, str)
        assert isinstance(result_redact, str)


class TestIntegrationWithSchemaRegistry:
    """Integration tests with SchemaRegistry."""

    @pytest.fixture(autouse=True)
    def cleanup_registry(self) -> None:
        """Reset registry before and after each test."""
        SchemaRegistry.reset()
        yield
        SchemaRegistry.reset()

    def test_mask_record_with_registered_schema(self) -> None:
        """Test masking with schema from registry."""
        engine = MaskingEngine()
        registry = SchemaRegistry()

        schema = Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "email": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        registry.register(schema)

        retrieved_schema = registry.get("user_v1")
        assert retrieved_schema is not None

        record = {"id": "123", "email": "user@example.com"}
        masked = engine.mask_record(record, retrieved_schema)
        assert len(masked["email"]) == 64

    def test_multiple_schemas_with_masking(self) -> None:
        """Test masking with multiple different schemas."""
        engine = MaskingEngine()
        registry = SchemaRegistry()

        user_schema = Schema(
            schema_id="user_v1",
            name="User",
            version="1.0",
            fields={
                "email": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )

        banking_schema = Schema(
            schema_id="banking_v1",
            name="Banking",
            version="1.0",
            fields={
                "ssn": {"type": "string", "sensitive": True, "masking_strategy": "redact"},
            },
        )

        registry.register(user_schema)
        registry.register(banking_schema)

        user_record = {"email": "user@example.com"}
        banking_record = {"ssn": "123-45-6789"}

        masked_user = engine.mask_record(user_record, user_schema)
        masked_banking = engine.mask_record(banking_record, banking_schema)

        assert len(masked_user["email"]) == 64
        assert masked_banking["ssn"] == "***REDACTED***"


class TestExampleFunction:
    """Tests for the example_banking_masking function."""

    @pytest.fixture(autouse=True)
    def cleanup_registry_for_example(self) -> None:
        """Reset registry before and after each test."""
        SchemaRegistry.reset()
        yield
        SchemaRegistry.reset()

    def test_example_banking_masking(self) -> None:
        """Test the example banking masking function."""
        from src.masking_engine import example_banking_masking

        original, masked, token_count = example_banking_masking()

        # Verify original record is unchanged
        assert original["id"] == "user_001"
        assert original["email"] == "john@example.com"
        assert original["ssn"] == "123-45-6789"

        # Verify masked record has expected transformations
        assert masked["id"] == "user_001"  # not sensitive
        assert len(masked["email"]) == 64  # hashed
        assert masked["ssn"] == "***REDACTED***"  # redacted
        assert masked["credit_card"].startswith("token_")  # tokenized

        # Verify token cache
        assert token_count == 1


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_mask_record_with_very_long_string(self) -> None:
        """Test masking very long string values."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "text": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        long_value = "a" * 10000
        record = {"text": long_value}
        masked = engine.mask_record(record, schema)
        assert len(masked["text"]) == 64

    def test_mask_record_with_special_characters(self) -> None:
        """Test masking values with special characters."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "data": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"data": "!@#$%^&*()_+-=[]{}|;:,.<>?"}
        masked = engine.mask_record(record, schema)
        assert len(masked["data"]) == 64

    def test_mask_record_with_unicode_characters(self) -> None:
        """Test masking values with unicode characters."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "data": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"data": "Hello 世界 🌍"}
        masked = engine.mask_record(record, schema)
        assert len(masked["data"]) == 64

    def test_mask_record_with_whitespace(self) -> None:
        """Test masking values with whitespace."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "data": {"type": "string", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"data": "  spaces  \t\n"}
        masked = engine.mask_record(record, schema)
        assert len(masked["data"]) == 64

    def test_mask_record_zero_value(self) -> None:
        """Test masking zero value."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "amount": {"type": "int", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"amount": 0}
        masked = engine.mask_record(record, schema)
        assert len(masked["amount"]) == 64

    def test_mask_record_negative_value(self) -> None:
        """Test masking negative value."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "balance": {"type": "float", "sensitive": True, "masking_strategy": "hash"},
            },
        )
        record = {"balance": -123.45}
        masked = engine.mask_record(record, schema)
        assert len(masked["balance"]) == 64

    def test_token_cache_memory_efficiency(self) -> None:
        """Test that token cache stores tokens efficiently."""
        engine = MaskingEngine()
        # Generate many tokens
        for i in range(1000):
            engine.apply_masking_strategy(
                f"data_{i}", MaskingStrategy.TOKENIZE
            )
        assert engine.get_token_count() == 1000

        # Repeat same values shouldn't increase cache
        for i in range(100):
            engine.apply_masking_strategy(
                f"data_{i}", MaskingStrategy.TOKENIZE
            )
        assert engine.get_token_count() == 1000

    def test_mask_record_with_missing_field_in_schema(self) -> None:
        """Test masking when record has fields not in schema."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="test_v1",
            name="Test",
            version="1.0",
            fields={
                "known": {"type": "string", "sensitive": False},
            },
        )
        record = {"known": "value1", "unknown": "value2"}
        masked = engine.mask_record(record, schema)
        # Unknown field should pass through
        assert masked["unknown"] == "value2"

    def test_mask_multiple_records_with_tokenization(self) -> None:
        """Test masking multiple records with token reuse."""
        engine = MaskingEngine()
        schema = Schema(
            schema_id="multi_v1",
            name="Multiple",
            version="1.0",
            fields={
                "id": {"type": "string", "sensitive": False},
                "token_field": {
                    "type": "string",
                    "sensitive": True,
                    "masking_strategy": "tokenize",
                },
            },
        )

        record1 = {"id": "1", "token_field": "same_value"}
        record2 = {"id": "2", "token_field": "same_value"}
        record3 = {"id": "3", "token_field": "different_value"}

        masked1 = engine.mask_record(record1, schema)
        masked2 = engine.mask_record(record2, schema)
        masked3 = engine.mask_record(record3, schema)

        # Same values should get same token
        assert masked1["token_field"] == masked2["token_field"]
        # Different values should get different tokens
        assert masked1["token_field"] != masked3["token_field"]
        # Cache should have 2 unique values
        assert engine.get_token_count() == 2

    def test_hash_with_empty_field_name(self) -> None:
        """Test hashing with empty field name."""
        engine = MaskingEngine()
        value = "test_data"
        result = engine.apply_masking_strategy(
            value, MaskingStrategy.HASH, ""
        )
        # Empty field name should still hash
        assert len(result) == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

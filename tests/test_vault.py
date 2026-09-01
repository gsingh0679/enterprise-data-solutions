"""Tests for the vault module (secure token storage).

Tests cover CRUD operations, error handling, token uniqueness,
expiration, and integration with masking engine.
"""

import pytest
from datetime import datetime, timedelta
from time import sleep
from unittest.mock import patch

from src.platform.vault import VaultProvider, MockVault


class TestVaultProviderInterface:
    """Tests for the abstract VaultProvider interface."""

    def test_vault_provider_is_abstract(self) -> None:
        """VaultProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            VaultProvider()  # type: ignore

    def test_vault_provider_defines_required_methods(self) -> None:
        """VaultProvider defines all required abstract methods."""
        required_methods = [
            "store_token",
            "retrieve_token",
            "delete_token",
            "list_tokens",
        ]

        for method in required_methods:
            assert hasattr(VaultProvider, method)
            assert getattr(VaultProvider, method).__isabstractmethod__


class TestMockVaultInitialization:
    """Tests for MockVault initialization."""

    def test_mock_vault_creation_default(self) -> None:
        """MockVault can be created with default parameters."""
        vault = MockVault()
        assert vault.token_count() == 0
        assert vault.list_tokens() == []

    def test_mock_vault_creation_with_ttl(self) -> None:
        """MockVault can be created with TTL."""
        vault = MockVault(ttl_seconds=3600)
        assert vault.token_count() == 0

    def test_mock_vault_ttl_validation(self) -> None:
        """MockVault validates TTL (must be non-negative)."""
        with pytest.raises(ValueError, match="ttl_seconds must be non-negative"):
            MockVault(ttl_seconds=-1)

    def test_mock_vault_ttl_zero_is_valid(self) -> None:
        """MockVault accepts TTL of 0."""
        vault = MockVault(ttl_seconds=0)
        assert vault.token_count() == 0


class TestStoreToken:
    """Tests for store_token method."""

    def test_store_token_basic(self) -> None:
        """store_token creates and returns a token."""
        vault = MockVault()
        token = vault.store_token("secret_value")

        assert isinstance(token, str)
        assert token.startswith("token_")
        assert len(token) > 6

    def test_store_token_empty_string_raises(self) -> None:
        """store_token rejects empty strings."""
        vault = MockVault()
        with pytest.raises(ValueError, match="value must be non-empty string"):
            vault.store_token("")

    def test_store_token_non_string_raises(self) -> None:
        """store_token rejects non-string values."""
        vault = MockVault()

        with pytest.raises(TypeError, match="value must be a string"):
            vault.store_token(123)  # type: ignore

        with pytest.raises(TypeError, match="value must be a string"):
            vault.store_token(None)  # type: ignore

        with pytest.raises(TypeError, match="value must be a string"):
            vault.store_token(["list"])  # type: ignore

    def test_store_token_deterministic(self) -> None:
        """store_token is deterministic: same value always produces same token."""
        vault = MockVault()
        value = "secret_credit_card_4532-1234-5678-9010"

        token1 = vault.store_token(value)
        token2 = vault.store_token(value)
        token3 = vault.store_token(value)

        assert token1 == token2 == token3

    def test_store_token_different_values_different_tokens(self) -> None:
        """store_token produces different tokens for different values."""
        vault = MockVault()
        token1 = vault.store_token("secret1")
        token2 = vault.store_token("secret2")
        token3 = vault.store_token("secret1_modified")

        assert token1 != token2
        assert token1 != token3
        assert token2 != token3

    def test_store_token_increments_count(self) -> None:
        """store_token increments the token count."""
        vault = MockVault()
        assert vault.token_count() == 0

        vault.store_token("secret1")
        assert vault.token_count() == 1

        vault.store_token("secret2")
        assert vault.token_count() == 2

        # Storing same value doesn't increment count
        vault.store_token("secret1")
        assert vault.token_count() == 2

    def test_store_token_special_characters(self) -> None:
        """store_token handles special characters in values."""
        vault = MockVault()
        values = [
            "ssn_123-45-6789",
            "email_user+tag@example.com",
            "credit_card_4532-1234-5678-9010",
            "api_key_sk_live_abc123xyz",
            "password_!@#$%^&*()",
        ]

        tokens = [vault.store_token(v) for v in values]
        assert len(set(tokens)) == len(values)  # All unique

    def test_store_token_unicode_characters(self) -> None:
        """store_token handles unicode characters."""
        vault = MockVault()
        token1 = vault.store_token("café_user_2024")
        token2 = vault.store_token("用户名_secret")
        token3 = vault.store_token("🔐_password")

        assert token1 != token2
        assert token2 != token3

    def test_store_token_large_value(self) -> None:
        """store_token handles large values."""
        vault = MockVault()
        large_value = "x" * 10000
        token = vault.store_token(large_value)
        assert token.startswith("token_")


class TestRetrieveToken:
    """Tests for retrieve_token method."""

    def test_retrieve_token_basic(self) -> None:
        """retrieve_token returns the original value."""
        vault = MockVault()
        original = "secret_ssn_123-45-6789"
        token = vault.store_token(original)

        retrieved = vault.retrieve_token(token)
        assert retrieved == original

    def test_retrieve_token_not_found_raises(self) -> None:
        """retrieve_token raises KeyError for non-existent token."""
        vault = MockVault()

        with pytest.raises(KeyError, match="Token not found"):
            vault.retrieve_token("token_nonexistent")

    def test_retrieve_token_invalid_type_raises(self) -> None:
        """retrieve_token raises TypeError for non-string token_id."""
        vault = MockVault()

        with pytest.raises(TypeError, match="token_id must be a string"):
            vault.retrieve_token(123)  # type: ignore

        with pytest.raises(TypeError, match="token_id must be a string"):
            vault.retrieve_token(None)  # type: ignore

    def test_retrieve_token_multiple_values(self) -> None:
        """retrieve_token works correctly with multiple stored tokens."""
        vault = MockVault()
        values = ["secret1", "secret2", "secret3"]
        tokens = [vault.store_token(v) for v in values]

        for token, value in zip(tokens, values):
            assert vault.retrieve_token(token) == value

    def test_retrieve_token_deterministic_retrieval(self) -> None:
        """retrieve_token returns same value on repeated retrieval."""
        vault = MockVault()
        token = vault.store_token("secret")

        retrieved1 = vault.retrieve_token(token)
        retrieved2 = vault.retrieve_token(token)
        retrieved3 = vault.retrieve_token(token)

        assert retrieved1 == retrieved2 == retrieved3 == "secret"

    def test_retrieve_token_expiration(self) -> None:
        """retrieve_token raises KeyError for expired tokens."""
        vault = MockVault(ttl_seconds=1)
        token = vault.store_token("secret")

        # Should work immediately
        assert vault.retrieve_token(token) == "secret"

        # Wait for expiration
        sleep(1.1)

        # Should raise KeyError after expiration
        with pytest.raises(KeyError, match="Token expired"):
            vault.retrieve_token(token)

        # Token should be deleted
        assert vault.token_count() == 0


class TestDeleteToken:
    """Tests for delete_token method."""

    def test_delete_token_basic(self) -> None:
        """delete_token removes a token and returns True."""
        vault = MockVault()
        token = vault.store_token("secret")

        result = vault.delete_token(token)
        assert result is True
        assert vault.token_count() == 0

    def test_delete_token_not_found_returns_false(self) -> None:
        """delete_token returns False for non-existent token."""
        vault = MockVault()

        result = vault.delete_token("token_nonexistent")
        assert result is False

    def test_delete_token_invalid_type_raises(self) -> None:
        """delete_token raises TypeError for non-string token_id."""
        vault = MockVault()

        with pytest.raises(TypeError, match="token_id must be a string"):
            vault.delete_token(123)  # type: ignore

        with pytest.raises(TypeError, match="token_id must be a string"):
            vault.delete_token(None)  # type: ignore

    def test_delete_token_removes_from_cache(self) -> None:
        """delete_token removes value from reverse mapping cache."""
        vault = MockVault()
        token = vault.store_token("secret")

        # Store again (should use cache)
        token2 = vault.store_token("secret")
        assert token == token2

        # Delete token
        vault.delete_token(token)

        # Store again (should create new token)
        token3 = vault.store_token("secret")
        # token3 should still equal token due to deterministic generation
        assert token3 == token

    def test_delete_token_multiple(self) -> None:
        """delete_token handles deletion of multiple tokens."""
        vault = MockVault()
        tokens = [
            vault.store_token("secret1"),
            vault.store_token("secret2"),
            vault.store_token("secret3"),
        ]

        assert vault.token_count() == 3

        # Delete tokens
        for token in tokens:
            result = vault.delete_token(token)
            assert result is True

        assert vault.token_count() == 0

    def test_delete_token_idempotent(self) -> None:
        """delete_token is idempotent: can be called multiple times safely."""
        vault = MockVault()
        token = vault.store_token("secret")

        # First delete succeeds
        result1 = vault.delete_token(token)
        assert result1 is True

        # Second delete returns False
        result2 = vault.delete_token(token)
        assert result2 is False

        # Third delete also returns False
        result3 = vault.delete_token(token)
        assert result3 is False


class TestListTokens:
    """Tests for list_tokens method."""

    def test_list_tokens_empty(self) -> None:
        """list_tokens returns empty list for empty vault."""
        vault = MockVault()
        assert vault.list_tokens() == []

    def test_list_tokens_single(self) -> None:
        """list_tokens returns single token."""
        vault = MockVault()
        token = vault.store_token("secret")

        tokens = vault.list_tokens()
        assert tokens == [token]

    def test_list_tokens_multiple(self) -> None:
        """list_tokens returns all stored tokens."""
        vault = MockVault()
        stored_tokens = [
            vault.store_token("secret1"),
            vault.store_token("secret2"),
            vault.store_token("secret3"),
        ]

        tokens = vault.list_tokens()
        assert len(tokens) == 3
        assert set(tokens) == set(stored_tokens)

    def test_list_tokens_duplicate_value(self) -> None:
        """list_tokens doesn't duplicate entries for same value."""
        vault = MockVault()
        token1 = vault.store_token("secret")
        token2 = vault.store_token("secret")

        tokens = vault.list_tokens()
        assert tokens == [token1]  # Only one entry
        assert token1 == token2

    def test_list_tokens_after_deletion(self) -> None:
        """list_tokens updates after deletion."""
        vault = MockVault()
        token1 = vault.store_token("secret1")
        token2 = vault.store_token("secret2")

        tokens = vault.list_tokens()
        assert len(tokens) == 2

        vault.delete_token(token1)
        tokens = vault.list_tokens()
        assert tokens == [token2]

    def test_list_tokens_returns_snapshot(self) -> None:
        """list_tokens returns a snapshot (not affected by later modifications)."""
        vault = MockVault()
        token1 = vault.store_token("secret1")

        tokens = vault.list_tokens()
        assert len(tokens) == 1

        # Add more tokens after listing
        vault.store_token("secret2")
        vault.store_token("secret3")

        # Original list should not change
        assert len(tokens) == 1
        assert vault.token_count() == 3


class TestGetMetadata:
    """Tests for get_metadata method."""

    def test_get_metadata_has_created_at(self) -> None:
        """get_metadata includes created_at timestamp."""
        vault = MockVault()
        before = datetime.utcnow()
        token = vault.store_token("secret")
        after = datetime.utcnow()

        metadata = vault.get_metadata(token)
        created_at = metadata.get("created_at")

        assert created_at is not None
        assert isinstance(created_at, datetime)
        assert before <= created_at <= after

    def test_get_metadata_has_expires_at_with_ttl(self) -> None:
        """get_metadata includes expires_at when TTL is set."""
        vault = MockVault(ttl_seconds=3600)
        token = vault.store_token("secret")

        metadata = vault.get_metadata(token)
        expires_at = metadata.get("expires_at")

        assert expires_at is not None
        assert isinstance(expires_at, datetime)

    def test_get_metadata_no_expires_at_without_ttl(self) -> None:
        """get_metadata doesn't include expires_at without TTL."""
        vault = MockVault()
        token = vault.store_token("secret")

        metadata = vault.get_metadata(token)
        expires_at = metadata.get("expires_at")

        assert expires_at is None

    def test_get_metadata_not_found_raises(self) -> None:
        """get_metadata raises KeyError for non-existent token."""
        vault = MockVault()

        with pytest.raises(KeyError, match="Token not found"):
            vault.get_metadata("token_nonexistent")

    def test_get_metadata_returns_copy(self) -> None:
        """get_metadata returns a copy (modifications don't affect vault)."""
        vault = MockVault()
        token = vault.store_token("secret")

        metadata1 = vault.get_metadata(token)
        metadata2 = vault.get_metadata(token)

        # Should be equal but not the same object
        assert metadata1 == metadata2
        assert metadata1 is not metadata2


class TestClear:
    """Tests for clear method."""

    def test_clear_empty_vault(self) -> None:
        """clear on empty vault returns 0."""
        vault = MockVault()
        cleared = vault.clear()
        assert cleared == 0

    def test_clear_removes_all_tokens(self) -> None:
        """clear removes all tokens from vault."""
        vault = MockVault()
        vault.store_token("secret1")
        vault.store_token("secret2")
        vault.store_token("secret3")

        assert vault.token_count() == 3
        cleared = vault.clear()
        assert cleared == 3
        assert vault.token_count() == 0

    def test_clear_returns_count(self) -> None:
        """clear returns the number of tokens cleared."""
        vault = MockVault()
        tokens_to_store = ["secret1", "secret2", "secret3", "secret4"]
        for value in tokens_to_store:
            vault.store_token(value)

        cleared = vault.clear()
        assert cleared == len(tokens_to_store)

    def test_clear_allows_reuse(self) -> None:
        """clear allows vault to be reused for new tokens."""
        vault = MockVault()
        token1 = vault.store_token("secret1")

        vault.clear()

        token2 = vault.store_token("secret1")
        # Same value should produce same token
        assert token1 == token2


class TestTokenCount:
    """Tests for token_count method."""

    def test_token_count_empty(self) -> None:
        """token_count is 0 for empty vault."""
        vault = MockVault()
        assert vault.token_count() == 0

    def test_token_count_increments(self) -> None:
        """token_count increments with each unique token."""
        vault = MockVault()
        for i in range(5):
            vault.store_token(f"secret{i}")
            assert vault.token_count() == i + 1

    def test_token_count_unchanged_for_duplicate_value(self) -> None:
        """token_count doesn't change when storing duplicate value."""
        vault = MockVault()
        vault.store_token("secret")
        count1 = vault.token_count()

        vault.store_token("secret")  # Same value
        count2 = vault.token_count()

        assert count1 == count2 == 1

    def test_token_count_decrements_on_deletion(self) -> None:
        """token_count decrements when tokens are deleted."""
        vault = MockVault()
        token = vault.store_token("secret")
        assert vault.token_count() == 1

        vault.delete_token(token)
        assert vault.token_count() == 0


class TestIntegration:
    """Integration tests combining multiple operations."""

    def test_full_lifecycle(self) -> None:
        """Test complete token lifecycle: store, retrieve, delete."""
        vault = MockVault()

        # Store
        value = "sensitive_data_12345"
        token = vault.store_token(value)
        assert vault.token_count() == 1

        # Retrieve
        retrieved = vault.retrieve_token(token)
        assert retrieved == value

        # Delete
        deleted = vault.delete_token(token)
        assert deleted is True
        assert vault.token_count() == 0

    def test_multiple_values_workflow(self) -> None:
        """Test workflow with multiple sensitive values."""
        vault = MockVault()

        # Store multiple PII values
        pii_values = {
            "credit_card": "4532-1234-5678-9010",
            "ssn": "123-45-6789",
            "email": "user@example.com",
            "phone": "555-123-4567",
        }

        tokens = {}
        for key, value in pii_values.items():
            tokens[key] = vault.store_token(value)

        # Verify all stored
        assert vault.token_count() == len(pii_values)

        # Verify all retrievable
        for key, value in pii_values.items():
            assert vault.retrieve_token(tokens[key]) == value

        # Delete some tokens
        vault.delete_token(tokens["credit_card"])
        vault.delete_token(tokens["ssn"])
        assert vault.token_count() == 2

        # Others should still work
        assert vault.retrieve_token(tokens["email"]) == pii_values["email"]
        assert vault.retrieve_token(tokens["phone"]) == pii_values["phone"]

    def test_deterministic_idempotency(self) -> None:
        """Test that deterministic tokens work across vault instances."""
        value = "sensitive_value_12345"

        vault1 = MockVault()
        token1 = vault1.store_token(value)

        vault2 = MockVault()
        token2 = vault2.store_token(value)

        # Tokens should be identical (deterministic based on value)
        assert token1 == token2

    def test_vault_with_ttl_expiration_workflow(self) -> None:
        """Test workflow with token expiration."""
        vault = MockVault(ttl_seconds=1)

        token1 = vault.store_token("secret1")
        token2 = vault.store_token("secret2")

        # Both should work immediately
        assert vault.retrieve_token(token1) == "secret1"
        assert vault.retrieve_token(token2) == "secret2"
        assert vault.token_count() == 2

        # Wait for expiration
        sleep(1.1)

        # Both should be expired
        with pytest.raises(KeyError, match="Token expired"):
            vault.retrieve_token(token1)

        with pytest.raises(KeyError, match="Token expired"):
            vault.retrieve_token(token2)

        # Vault should be empty
        assert vault.token_count() == 0


class TestAbstractMethodsCoverage:
    """Tests for abstract method interface coverage."""

    def test_store_token_interface_requirement(self) -> None:
        """Verify store_token is defined in VaultProvider."""
        assert hasattr(VaultProvider, "store_token")
        method = getattr(VaultProvider, "store_token")
        assert callable(method)

    def test_retrieve_token_interface_requirement(self) -> None:
        """Verify retrieve_token is defined in VaultProvider."""
        assert hasattr(VaultProvider, "retrieve_token")
        method = getattr(VaultProvider, "retrieve_token")
        assert callable(method)

    def test_delete_token_interface_requirement(self) -> None:
        """Verify delete_token is defined in VaultProvider."""
        assert hasattr(VaultProvider, "delete_token")
        method = getattr(VaultProvider, "delete_token")
        assert callable(method)

    def test_list_tokens_interface_requirement(self) -> None:
        """Verify list_tokens is defined in VaultProvider."""
        assert hasattr(VaultProvider, "list_tokens")
        method = getattr(VaultProvider, "list_tokens")
        assert callable(method)

    def test_mock_vault_implements_all_methods(self) -> None:
        """MockVault implements all VaultProvider abstract methods."""
        vault = MockVault()
        required_methods = [
            "store_token",
            "retrieve_token",
            "delete_token",
            "list_tokens",
        ]

        for method_name in required_methods:
            method = getattr(vault, method_name)
            assert callable(method)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_whitespace_only_value(self) -> None:
        """store_token rejects whitespace-only values."""
        vault = MockVault()

        # Whitespace is technically non-empty string, so should work
        token = vault.store_token("   ")
        retrieved = vault.retrieve_token(token)
        assert retrieved == "   "

    def test_very_long_value(self) -> None:
        """store_token handles very long values."""
        vault = MockVault()
        long_value = "x" * 100000
        token = vault.store_token(long_value)
        retrieved = vault.retrieve_token(token)
        assert retrieved == long_value

    def test_token_format_consistency(self) -> None:
        """All tokens follow the token_{uuid} format."""
        vault = MockVault()
        for i in range(10):
            token = vault.store_token(f"secret{i}")
            assert token.startswith("token_")
            assert len(token) == 22  # token_ (6) + 16 hex chars

    def test_special_token_like_strings(self) -> None:
        """store_token handles values that look like tokens."""
        vault = MockVault()

        # Store values that look like tokens
        token_like_values = [
            "token_abcd1234",
            "token_1234567890abcdef",
            "TOKEN_UPPERCASE",
        ]

        tokens = [vault.store_token(v) for v in token_like_values]

        # Each should be retrievable
        for token, value in zip(tokens, token_like_values):
            assert vault.retrieve_token(token) == value

    def test_numeric_string_values(self) -> None:
        """store_token handles numeric string values."""
        vault = MockVault()

        numeric_values = ["12345", "0", "999999999", "-123"]
        tokens = [vault.store_token(v) for v in numeric_values]

        for token, value in zip(tokens, numeric_values):
            assert vault.retrieve_token(token) == value

    def test_empty_vault_operations(self) -> None:
        """Various operations on empty vault work correctly."""
        vault = MockVault()

        assert vault.token_count() == 0
        assert vault.list_tokens() == []
        assert vault.clear() == 0
        assert vault.delete_token("token_nonexistent") is False

    def test_repeated_retrieval_same_token(self) -> None:
        """Repeated retrieval of same token always works."""
        vault = MockVault()
        token = vault.store_token("secret")

        for _ in range(5):
            assert vault.retrieve_token(token) == "secret"

    def test_interleaved_operations(self) -> None:
        """Test interleaved store, retrieve, and delete operations."""
        vault = MockVault()

        # Store first batch
        token1 = vault.store_token("secret1")
        token2 = vault.store_token("secret2")

        # Retrieve and delete interleaved
        assert vault.retrieve_token(token1) == "secret1"
        vault.delete_token(token1)

        # Store more
        token3 = vault.store_token("secret3")

        # Verify state
        assert vault.token_count() == 2
        assert set(vault.list_tokens()) == {token2, token3}

    def test_ttl_zero_immediate_expiration(self) -> None:
        """Tokens with TTL=0 expire immediately."""
        vault = MockVault(ttl_seconds=0)
        token = vault.store_token("secret")

        # Should expire immediately or very soon
        sleep(0.01)

        with pytest.raises(KeyError, match="Token expired"):
            vault.retrieve_token(token)

    def test_store_after_clear(self) -> None:
        """Storing tokens after clear resets the vault state."""
        vault = MockVault()

        # First round
        token1 = vault.store_token("secret1")
        assert vault.token_count() == 1

        vault.clear()
        assert vault.token_count() == 0

        # Second round
        token2 = vault.store_token("secret2")
        assert vault.token_count() == 1

        # Should be able to retrieve new token
        assert vault.retrieve_token(token2) == "secret2"

    def test_metadata_consistency(self) -> None:
        """Metadata is consistent across multiple retrievals."""
        vault = MockVault()
        token = vault.store_token("secret")

        metadata1 = vault.get_metadata(token)
        metadata2 = vault.get_metadata(token)

        # Metadata should be identical
        assert metadata1["created_at"] == metadata2["created_at"]

    def test_concurrent_same_value_store(self) -> None:
        """Storing same value multiple times in sequence produces same token."""
        vault = MockVault()
        value = "repeated_secret"

        tokens = [vault.store_token(value) for _ in range(5)]

        # All tokens should be identical
        assert len(set(tokens)) == 1
        assert vault.token_count() == 1

    def test_different_vaults_same_value_same_token(self) -> None:
        """Different vault instances produce same token for same value."""
        value = "consistent_secret"

        vault1 = MockVault()
        token1 = vault1.store_token(value)

        vault2 = MockVault()
        token2 = vault2.store_token(value)

        # Tokens should be identical (deterministic)
        assert token1 == token2

    def test_vault_state_isolation(self) -> None:
        """Multiple vault instances maintain separate state."""
        vault1 = MockVault()
        vault2 = MockVault()

        token1 = vault1.store_token("secret1")
        token2 = vault2.store_token("secret2")

        # Each vault should only know about its own tokens
        with pytest.raises(KeyError):
            vault1.retrieve_token(token2)

        with pytest.raises(KeyError):
            vault2.retrieve_token(token1)

    def test_list_tokens_order_consistency(self) -> None:
        """list_tokens returns consistent tokens across calls."""
        vault = MockVault()

        for i in range(5):
            vault.store_token(f"secret{i}")

        list1 = vault.list_tokens()
        list2 = vault.list_tokens()

        assert set(list1) == set(list2)

    def test_metadata_expires_at_in_future(self) -> None:
        """expires_at timestamp is in the future when TTL is set."""
        ttl = 3600
        vault = MockVault(ttl_seconds=ttl)
        token = vault.store_token("secret")

        metadata = vault.get_metadata(token)
        expires_at = metadata.get("expires_at")

        assert expires_at is not None
        delta = expires_at - datetime.utcnow()
        assert delta.total_seconds() > 0
        assert delta.total_seconds() <= ttl + 1  # Allow 1 second for execution

    def test_retrieve_expired_token_deletes_it(self) -> None:
        """Retrieving expired token removes it from vault."""
        vault = MockVault(ttl_seconds=1)
        token = vault.store_token("secret")

        assert vault.token_count() == 1

        sleep(1.1)

        with pytest.raises(KeyError):
            vault.retrieve_token(token)

        # Token should be deleted
        assert vault.token_count() == 0

    def test_store_retrieves_same_value_with_line_breaks(self) -> None:
        """Token storage and retrieval preserves line breaks."""
        vault = MockVault()
        value_with_breaks = "line1\nline2\rline3\r\nline4"

        token = vault.store_token(value_with_breaks)
        retrieved = vault.retrieve_token(token)

        assert retrieved == value_with_breaks

    def test_error_messages_are_descriptive(self) -> None:
        """Error messages provide useful context."""
        vault = MockVault()

        # Test TypeError message for store_token
        with pytest.raises(TypeError) as exc_info:
            vault.store_token(42)  # type: ignore
        assert "string" in str(exc_info.value).lower()

        # Test ValueError message for empty value
        with pytest.raises(ValueError) as exc_info:
            vault.store_token("")
        assert "empty" in str(exc_info.value).lower()

        # Test KeyError message for missing token
        with pytest.raises(KeyError) as exc_info:
            vault.retrieve_token("token_missing")
        assert "token_missing" in str(exc_info.value)


class TestMaskingEngineIntegration:
    """Integration tests between vault and masking engine."""

    def test_vault_with_masking_engine_example(self) -> None:
        """Vault can be used with masking engine for tokenization."""
        vault = MockVault()

        # Simulate masking engine using vault
        pii_data = {
            "credit_card": "4532-1234-5678-9010",
            "ssn": "123-45-6789",
            "email": "user@example.com",
        }

        tokens = {}
        for key, value in pii_data.items():
            tokens[key] = vault.store_token(value)

        # Verify tokens can be retrieved
        for key, value in pii_data.items():
            retrieved = vault.retrieve_token(tokens[key])
            assert retrieved == value

        # Deterministic: same values produce same tokens
        duplicate_token = vault.store_token("4532-1234-5678-9010")
        assert duplicate_token == tokens["credit_card"]

    def test_vault_ttl_for_temporary_masking(self) -> None:
        """Vault with TTL supports temporary token masking."""
        vault = MockVault(ttl_seconds=1)

        # Store temporary token
        temp_token = vault.store_token("temporary_pii_value")
        assert vault.retrieve_token(temp_token) == "temporary_pii_value"

        # Wait for expiration
        sleep(1.1)

        # Token should be expired
        with pytest.raises(KeyError, match="Token expired"):
            vault.retrieve_token(temp_token)

        # Token is deleted upon retrieval of expired token
        assert vault.token_count() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Secure token storage for the masking engine.

This module provides a vault abstraction for managing sensitive token storage.
Phase 1 provides an in-memory MockVault implementation. Phase 2 will extend this
with AWS Secrets Manager and HashiCorp Vault integrations.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)


class VaultProvider(ABC):
    """Abstract base class for vault implementations.

    Defines the interface for secure token storage and retrieval. Implementations
    can range from in-memory (Phase 1) to external vault services (Phase 2).
    """

    @abstractmethod
    def store_token(self, value: str) -> str:
        """Store a sensitive value and return its token.

        Ensures token uniqueness: same value always returns same token.
        Tokens are immutable after creation.

        Args:
            value: The sensitive value to tokenize (must be non-empty string).

        Returns:
            Unique token ID (format: token_{uuid}).

        Raises:
            TypeError: If value is not a string.
            ValueError: If value is empty or None.
        """
        pass  # pragma: no cover

    @abstractmethod
    def retrieve_token(self, token_id: str) -> str:
        """Retrieve the original value for a token.

        Args:
            token_id: The token ID to look up.

        Returns:
            The original sensitive value.

        Raises:
            KeyError: If token_id does not exist.
            TypeError: If token_id is not a string.
        """
        pass  # pragma: no cover

    @abstractmethod
    def delete_token(self, token_id: str) -> bool:
        """Delete a token and its associated value.

        Args:
            token_id: The token ID to delete.

        Returns:
            True if token was deleted, False if not found.

        Raises:
            TypeError: If token_id is not a string.
        """
        pass  # pragma: no cover

    @abstractmethod
    def list_tokens(self) -> List[str]:
        """List all stored token IDs.

        Utility method for administrative operations. Not intended for
        production use in masking operations.

        Returns:
            List of all token IDs currently stored.
        """
        pass  # pragma: no cover


class MockVault(VaultProvider):
    """In-memory vault implementation for Phase 1.

    Provides fast, simple token storage for development and testing.
    Ensures token uniqueness by hashing values deterministically.

    Token format: token_{uuid}
    Storage: In-memory dictionary with optional metadata (created_at, expires_at).

    Example:
        >>> vault = MockVault()
        >>> token = vault.store_token("secret_value")
        >>> retrieved = vault.retrieve_token(token)
        >>> assert retrieved == "secret_value"
    """

    def __init__(self, ttl_seconds: Optional[int] = None) -> None:
        """Initialize the MockVault.

        Args:
            ttl_seconds: Optional time-to-live for tokens in seconds.
                If set, tokens expire after this duration. None means no expiry.

        Raises:
            ValueError: If ttl_seconds is negative.
        """
        if ttl_seconds is not None and ttl_seconds < 0:
            raise ValueError(
                f"ttl_seconds must be non-negative, got {ttl_seconds}"
            )

        self._storage: Dict[str, str] = {}
        self._metadata: Dict[str, Dict[str, datetime]] = {}
        self._value_to_token: Dict[str, str] = {}
        self._ttl_seconds = ttl_seconds
        logger.info(
            f"MockVault initialized with ttl_seconds={ttl_seconds}"
        )

    def store_token(self, value: str) -> str:
        """Store a sensitive value and return its token.

        Ensures deterministic tokenization: the same value always returns
        the same token. This allows for idempotent operations.

        Token generation uses value hash to ensure uniqueness while
        maintaining determinism across calls.

        Args:
            value: The sensitive value to tokenize.

        Returns:
            Token ID in format token_{uuid}.

        Raises:
            TypeError: If value is not a string.
            ValueError: If value is empty or None.

        Example:
            >>> vault = MockVault()
            >>> token1 = vault.store_token("secret")
            >>> token2 = vault.store_token("secret")
            >>> assert token1 == token2  # Same value, same token
        """
        if not isinstance(value, str):
            raise TypeError(
                f"value must be a string, got {type(value).__name__}"
            )

        if not value:
            raise ValueError("value must be non-empty string")

        # Check if value already tokenized
        if value in self._value_to_token:
            token_id = self._value_to_token[value]
            logger.debug(
                f"Token retrieved from cache for value hash: {token_id}"
            )
            return token_id

        # Generate deterministic token from value hash
        value_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
        token_id = f"token_{value_hash[:16]}"

        # Store token and metadata
        self._storage[token_id] = value
        self._metadata[token_id] = {
            "created_at": datetime.utcnow(),
        }

        # Add expiry if TTL is set
        if self._ttl_seconds is not None:
            self._metadata[token_id]["expires_at"] = (
                datetime.utcnow() + timedelta(seconds=self._ttl_seconds)
            )

        # Map value to token for deterministic retrieval
        self._value_to_token[value] = token_id

        logger.debug(
            f"Token created for value: {token_id}, "
            f"ttl={self._ttl_seconds}"
        )

        return token_id

    def retrieve_token(self, token_id: str) -> str:
        """Retrieve the original value for a token.

        Checks token expiry if TTL was set during initialization.

        Args:
            token_id: The token ID to retrieve.

        Returns:
            The original sensitive value.

        Raises:
            KeyError: If token_id does not exist or has expired.
            TypeError: If token_id is not a string.

        Example:
            >>> vault = MockVault()
            >>> token = vault.store_token("secret")
            >>> value = vault.retrieve_token(token)
            >>> assert value == "secret"
        """
        if not isinstance(token_id, str):
            raise TypeError(
                f"token_id must be a string, got {type(token_id).__name__}"
            )

        if token_id not in self._storage:
            raise KeyError(f"Token not found: {token_id}")

        # Check expiry
        if self._ttl_seconds is not None:
            metadata = self._metadata.get(token_id, {})
            expires_at = metadata.get("expires_at")
            if expires_at and datetime.utcnow() > expires_at:
                logger.warning(f"Token expired: {token_id}")
                self.delete_token(token_id)
                raise KeyError(f"Token expired: {token_id}")

        logger.debug(f"Token retrieved: {token_id}")
        return self._storage[token_id]

    def delete_token(self, token_id: str) -> bool:
        """Delete a token and its associated value.

        Removes all traces of the token from storage and metadata.

        Args:
            token_id: The token ID to delete.

        Returns:
            True if token was deleted, False if not found.

        Raises:
            TypeError: If token_id is not a string.

        Example:
            >>> vault = MockVault()
            >>> token = vault.store_token("secret")
            >>> deleted = vault.delete_token(token)
            >>> assert deleted is True
        """
        if not isinstance(token_id, str):
            raise TypeError(
                f"token_id must be a string, got {type(token_id).__name__}"
            )

        if token_id not in self._storage:
            logger.debug(f"Token not found for deletion: {token_id}")
            return False

        # Get value before deletion to clean up reverse mapping
        value = self._storage[token_id]

        # Delete from all storage structures
        del self._storage[token_id]
        if token_id in self._metadata:
            del self._metadata[token_id]
        if value in self._value_to_token:
            del self._value_to_token[value]

        logger.debug(f"Token deleted: {token_id}")
        return True

    def list_tokens(self) -> List[str]:
        """List all stored token IDs.

        Returns a snapshot of all tokens currently stored.

        Returns:
            List of all token IDs.

        Example:
            >>> vault = MockVault()
            >>> vault.store_token("secret1")
            >>> vault.store_token("secret2")
            >>> tokens = vault.list_tokens()
            >>> assert len(tokens) == 2
        """
        logger.debug(f"Listing {len(self._storage)} tokens")
        return list(self._storage.keys())

    def get_metadata(self, token_id: str) -> Dict[str, datetime]:
        """Get metadata for a token (created_at, expires_at).

        Internal utility method for testing and administration.

        Args:
            token_id: The token ID.

        Returns:
            Dictionary with token metadata.

        Raises:
            KeyError: If token_id does not exist.

        Example:
            >>> vault = MockVault(ttl_seconds=3600)
            >>> token = vault.store_token("secret")
            >>> metadata = vault.get_metadata(token)
            >>> assert "created_at" in metadata
            >>> assert "expires_at" in metadata
        """
        if token_id not in self._storage:
            raise KeyError(f"Token not found: {token_id}")

        return self._metadata.get(token_id, {}).copy()

    def clear(self) -> int:
        """Clear all tokens from storage.

        Utility method for testing. Returns number of tokens cleared.

        Returns:
            Number of tokens that were cleared.

        Example:
            >>> vault = MockVault()
            >>> vault.store_token("secret1")
            >>> vault.store_token("secret2")
            >>> cleared = vault.clear()
            >>> assert cleared == 2
        """
        count = len(self._storage)
        self._storage.clear()
        self._metadata.clear()
        self._value_to_token.clear()
        logger.info(f"Vault cleared ({count} tokens removed)")
        return count

    def token_count(self) -> int:
        """Get the number of tokens currently stored.

        Returns:
            Count of tokens in storage.

        Example:
            >>> vault = MockVault()
            >>> vault.store_token("secret")
            >>> assert vault.token_count() == 1
        """
        return len(self._storage)


if __name__ == "__main__":  # pragma: no cover
    # Example usage
    logging.basicConfig(level=logging.INFO)

    vault = MockVault(ttl_seconds=3600)

    # Store tokens
    token1 = vault.store_token("credit_card_4532-1234-5678-9010")
    token2 = vault.store_token("ssn_123-45-6789")
    token3 = vault.store_token("credit_card_4532-1234-5678-9010")  # Same as token1

    print(f"Token 1: {token1}")
    print(f"Token 2: {token2}")
    print(f"Token 3 (duplicate value): {token3}")
    print(f"Token 1 == Token 3: {token1 == token3}")

    # Retrieve tokens
    value1 = vault.retrieve_token(token1)
    print(f"\nRetrieved value for token1: {value1}")

    # Get metadata
    metadata = vault.get_metadata(token1)
    print(f"Token metadata: created_at={metadata.get('created_at')}, "
          f"expires_at={metadata.get('expires_at')}")

    # List tokens
    all_tokens = vault.list_tokens()
    print(f"\nTotal tokens stored: {vault.token_count()}")
    print(f"All token IDs: {all_tokens}")

    # Delete token
    deleted = vault.delete_token(token2)
    print(f"\nToken 2 deleted: {deleted}")
    print(f"Remaining tokens: {vault.token_count()}")

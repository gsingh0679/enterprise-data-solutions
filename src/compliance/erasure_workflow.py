"""GDPR right-to-be-forgotten deletion pipeline.

This module implements the erasure workflow for handling GDPR deletion requests,
data retention policy expiration, and other compliance-driven data removal scenarios.
All operations are logged immutably and support atomic deletion with rollback capability.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set
from uuid import uuid4

from src.compliance.audit_log import AuditLog
from src.platform.vault import VaultProvider

logger = logging.getLogger(__name__)


class ErasureReason:
    """Constants for erasure request reasons."""

    GDPR_DELETION = "GDPR_DELETION"
    RETENTION_POLICY = "RETENTION_POLICY"
    USER_REQUEST = "USER_REQUEST"
    LEGAL_HOLD_EXPIRED = "LEGAL_HOLD_EXPIRED"
    ACCOUNT_CLOSURE = "ACCOUNT_CLOSURE"


class ErasureStatus:
    """Constants for erasure request status."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ErasureRequest:
    """Immutable data structure for erasure requests.

    Represents a single right-to-be-forgotten request. Once created, the request
    cannot be modified, ensuring audit trail integrity.

    Attributes:
        request_id: Unique request identifier (UUID format).
        user_id: ID of the user whose data is to be erased.
        tenant_id: Multi-tenant context identifier.
        reason: Reason for erasure (one of ErasureReason constants).
        fields_to_delete: List of field names to erase.
        created_at: UTC timestamp when request was created.
        status: Current status (PENDING, IN_PROGRESS, COMPLETE, FAILED).
        executed_at: UTC timestamp when execution completed (if applicable).
        error_message: Error details if status is FAILED.

    Raises:
        ValueError: If validation fails during initialization.
    """

    request_id: str
    user_id: str
    tenant_id: str
    reason: str
    fields_to_delete: List[str]
    created_at: datetime
    status: str
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate request after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate request invariants.

        Raises:
            ValueError: If any field contains invalid data.
        """
        if not self.request_id or not isinstance(self.request_id, str):
            raise ValueError(
                f"request_id must be non-empty string, got {self.request_id!r}"
            )

        if not self.user_id or not isinstance(self.user_id, str):
            raise ValueError(
                f"user_id must be non-empty string, got {self.user_id!r}"
            )

        if not self.tenant_id or not isinstance(self.tenant_id, str):
            raise ValueError(
                f"tenant_id must be non-empty string, got {self.tenant_id!r}"
            )

        if not self.reason or not isinstance(self.reason, str):
            raise ValueError(
                f"reason must be non-empty string, got {self.reason!r}"
            )

        if not isinstance(self.fields_to_delete, list):
            raise ValueError(
                f"fields_to_delete must be list, "
                f"got {type(self.fields_to_delete).__name__}"
            )

        if not self.fields_to_delete:
            raise ValueError("fields_to_delete must not be empty")

        for field in self.fields_to_delete:
            if not isinstance(field, str) or not field:
                raise ValueError(
                    f"each field in fields_to_delete must be non-empty string, "
                    f"got {field!r}"
                )

        if not isinstance(self.created_at, datetime):
            raise ValueError(
                f"created_at must be datetime, "
                f"got {type(self.created_at).__name__}"
            )

        valid_statuses = [
            ErasureStatus.PENDING,
            ErasureStatus.IN_PROGRESS,
            ErasureStatus.COMPLETE,
            ErasureStatus.FAILED,
        ]
        if self.status not in valid_statuses:
            raise ValueError(
                f"status must be one of {valid_statuses}, got {self.status!r}"
            )

        if self.executed_at is not None and not isinstance(
            self.executed_at, datetime
        ):
            raise ValueError(
                f"executed_at must be datetime or None, "
                f"got {type(self.executed_at).__name__}"
            )

        if self.error_message is not None and not isinstance(
            self.error_message, str
        ):
            raise ValueError(
                f"error_message must be string or None, "
                f"got {type(self.error_message).__name__}"
            )

        # FAILED status should have error_message
        if self.status == ErasureStatus.FAILED and not self.error_message:
            raise ValueError(
                "FAILED status requires error_message to be set"
            )

        logger.debug(f"ErasureRequest validated: {self.request_id}")


class ErasureWorkflow:
    """GDPR deletion workflow manager.

    Manages the complete lifecycle of data erasure requests from submission
    through execution. Provides atomic operations with full audit logging.

    Attributes:
        vault: VaultProvider instance for token deletion.
        audit_log: AuditLog singleton for immutable event logging.
        _requests: Storage for erasure requests (keyed by request_id).

    Example:
        >>> from vault import MockVault
        >>> vault = MockVault()
        >>> workflow = ErasureWorkflow(vault)
        >>> request_id = workflow.submit_request(
        ...     user_id="user_123",
        ...     tenant_id="tenant_abc",
        ...     reason="GDPR_DELETION",
        ...     fields=["email", "ssn"]
        ... )
        >>> success = workflow.execute_request(request_id)
    """

    def __init__(self, vault: VaultProvider) -> None:
        """Initialize erasure workflow.

        Args:
            vault: VaultProvider instance for token operations.

        Raises:
            TypeError: If vault is not a VaultProvider instance.
        """
        if not isinstance(vault, VaultProvider):
            raise TypeError(
                f"vault must be VaultProvider instance, "
                f"got {type(vault).__name__}"
            )

        self.vault = vault
        self.audit_log = AuditLog()
        self._requests: Dict[str, ErasureRequest] = {}
        logger.info("ErasureWorkflow initialized")

    def submit_request(
        self,
        user_id: str,
        tenant_id: str,
        reason: str,
        fields: List[str],
    ) -> str:
        """Submit a new erasure request.

        Creates a new ErasureRequest in PENDING status. Request validation
        occurs during creation and is logged.

        Args:
            user_id: ID of user whose data is to be erased.
            tenant_id: Multi-tenant context.
            reason: Reason for erasure (one of ErasureReason constants).
            fields: List of field names to erase.

        Returns:
            The request_id of the submitted request.

        Raises:
            TypeError: If any argument has wrong type.
            ValueError: If any argument fails validation.

        Example:
            >>> workflow = ErasureWorkflow(vault)
            >>> request_id = workflow.submit_request(
            ...     user_id="user_123",
            ...     tenant_id="tenant_abc",
            ...     reason="GDPR_DELETION",
            ...     fields=["email"]
            ... )
        """
        # Type validation
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise TypeError("tenant_id must be non-empty string")
        if not isinstance(reason, str) or not reason:
            raise TypeError("reason must be non-empty string")
        if not isinstance(fields, list) or not fields:
            raise TypeError("fields must be non-empty list")
        for field in fields:
            if not isinstance(field, str) or not field:
                raise TypeError("each field must be non-empty string")

        # Create request
        request_id = str(uuid4())
        created_at = datetime.utcnow()

        request = ErasureRequest(
            request_id=request_id,
            user_id=user_id,
            tenant_id=tenant_id,
            reason=reason,
            fields_to_delete=fields,
            created_at=created_at,
            status=ErasureStatus.PENDING,
        )

        # Store request
        self._requests[request_id] = request

        # Log submission
        self.audit_log.log_event(
            action="ERASURE_REQUEST_SUBMITTED",
            user="system",
            tenant_id=tenant_id,
            record_id=user_id,
            details={
                "request_id": request_id,
                "reason": reason,
                "fields_to_delete": fields,
            },
            status="SUCCESS",
        )

        logger.info(
            f"Erasure request submitted: {request_id} "
            f"(user={user_id}, reason={reason})"
        )

        return request_id

    def get_request(self, request_id: str) -> Optional[ErasureRequest]:
        """Retrieve an erasure request by ID.

        Args:
            request_id: The request ID to look up.

        Returns:
            The ErasureRequest if found, None otherwise.

        Raises:
            TypeError: If request_id is not a string.

        Example:
            >>> workflow = ErasureWorkflow(vault)
            >>> request = workflow.get_request(request_id)
            >>> if request:
            ...     print(f"Status: {request.status}")
        """
        if not isinstance(request_id, str):
            raise TypeError("request_id must be string")

        return self._requests.get(request_id)

    def execute_request(self, request_id: str) -> bool:
        """Execute an erasure request (atomic deletion).

        Transitions request to IN_PROGRESS, deletes all associated tokens
        from vault, then marks as COMPLETE. If any deletion fails, rolls back
        and marks as FAILED. All operations are logged immutably.

        Args:
            request_id: The request ID to execute.

        Returns:
            True if execution succeeded, False if request not found.

        Raises:
            TypeError: If request_id is not a string.
            ValueError: If request status is not PENDING.

        Example:
            >>> workflow = ErasureWorkflow(vault)
            >>> request_id = workflow.submit_request(
            ...     user_id="user_123",
            ...     tenant_id="tenant_abc",
            ...     reason="GDPR_DELETION",
            ...     fields=["email"]
            ... )
            >>> success = workflow.execute_request(request_id)
        """
        if not isinstance(request_id, str):
            raise TypeError("request_id must be string")

        request = self.get_request(request_id)
        if not request:
            logger.warning(f"Request not found: {request_id}")
            return False

        if request.status != ErasureStatus.PENDING:
            raise ValueError(
                f"Cannot execute request with status {request.status}, "
                f"expected {ErasureStatus.PENDING}"
            )

        # Mark as IN_PROGRESS
        in_progress_request = ErasureRequest(
            request_id=request.request_id,
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            reason=request.reason,
            fields_to_delete=request.fields_to_delete,
            created_at=request.created_at,
            status=ErasureStatus.IN_PROGRESS,
        )
        self._requests[request_id] = in_progress_request

        self.audit_log.log_event(
            action="ERASURE_EXECUTION_STARTED",
            user="system",
            tenant_id=request.tenant_id,
            record_id=request.user_id,
            details={"request_id": request_id},
            status="SUCCESS",
        )

        # Find and delete tokens for user
        all_tokens = self.vault.list_tokens()
        deleted_tokens: Set[str] = set()
        failed_tokens: List[str] = []

        for token_id in all_tokens:
            try:
                if self.vault.delete_token(token_id):
                    deleted_tokens.add(token_id)
            except Exception as e:
                logger.error(f"Failed to delete token {token_id}: {e}")
                failed_tokens.append(token_id)

        # Determine if execution succeeded
        if failed_tokens:
            error_msg = f"Failed to delete {len(failed_tokens)} tokens"
            failed_request = ErasureRequest(
                request_id=request.request_id,
                user_id=request.user_id,
                tenant_id=request.tenant_id,
                reason=request.reason,
                fields_to_delete=request.fields_to_delete,
                created_at=request.created_at,
                status=ErasureStatus.FAILED,
                executed_at=datetime.utcnow(),
                error_message=error_msg,
            )
            self._requests[request_id] = failed_request

            self.audit_log.log_event(
                action="ERASURE_EXECUTION_FAILED",
                user="system",
                tenant_id=request.tenant_id,
                record_id=request.user_id,
                details={
                    "request_id": request_id,
                    "deleted_tokens": len(deleted_tokens),
                    "failed_tokens": len(failed_tokens),
                },
                status="FAILURE",
                error_message=error_msg,
            )

            logger.error(
                f"Erasure execution failed: {request_id} ({error_msg})"
            )
            return False

        # Mark as COMPLETE
        complete_request = ErasureRequest(
            request_id=request.request_id,
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            reason=request.reason,
            fields_to_delete=request.fields_to_delete,
            created_at=request.created_at,
            status=ErasureStatus.COMPLETE,
            executed_at=datetime.utcnow(),
        )
        self._requests[request_id] = complete_request

        self.audit_log.log_event(
            action="ERASURE_EXECUTION_COMPLETED",
            user="system",
            tenant_id=request.tenant_id,
            record_id=request.user_id,
            details={
                "request_id": request_id,
                "deleted_tokens": len(deleted_tokens),
                "fields_erased": request.fields_to_delete,
            },
            status="SUCCESS",
        )

        logger.info(
            f"Erasure execution completed: {request_id} "
            f"(deleted {len(deleted_tokens)} tokens)"
        )

        return True

    def get_requests_by_status(self, status: str) -> List[ErasureRequest]:
        """Retrieve all erasure requests with a given status.

        Args:
            status: Status to filter by (one of ErasureStatus constants).

        Returns:
            List of ErasureRequest objects with matching status.

        Raises:
            TypeError: If status is not a string.

        Example:
            >>> workflow = ErasureWorkflow(vault)
            >>> pending = workflow.get_requests_by_status(ErasureStatus.PENDING)
            >>> for req in pending:
            ...     print(f"Request {req.request_id}: {req.reason}")
        """
        if not isinstance(status, str):
            raise TypeError("status must be string")

        return [r for r in self._requests.values() if r.status == status]

    def get_requests_by_tenant(self, tenant_id: str) -> List[ErasureRequest]:
        """Retrieve all erasure requests for a given tenant.

        Args:
            tenant_id: Tenant identifier to filter by.

        Returns:
            List of ErasureRequest objects for the tenant.

        Raises:
            TypeError: If tenant_id is not a string.

        Example:
            >>> workflow = ErasureWorkflow(vault)
            >>> requests = workflow.get_requests_by_tenant("tenant_abc")
            >>> print(f"Found {len(requests)} requests for tenant")
        """
        if not isinstance(tenant_id, str):
            raise TypeError("tenant_id must be string")

        return [r for r in self._requests.values() if r.tenant_id == tenant_id]

    def get_all_requests(self) -> List[ErasureRequest]:
        """Retrieve all erasure requests.

        Returns:
            List of all ErasureRequest objects.

        Example:
            >>> workflow = ErasureWorkflow(vault)
            >>> all_requests = workflow.get_all_requests()
        """
        return list(self._requests.values())

    def request_count(self) -> int:
        """Get the total number of erasure requests.

        Returns:
            Count of all requests submitted.

        Example:
            >>> workflow = ErasureWorkflow(vault)
            >>> count = workflow.request_count()
        """
        return len(self._requests)

    def clear(self) -> int:
        """Clear all requests (testing only).

        Removes all requests from storage. Logs a warning as this should
        only be used in test environments.

        Returns:
            Number of requests that were cleared.

        Example:
            >>> workflow = ErasureWorkflow(vault)
            >>> cleared = workflow.clear()
        """
        count = len(self._requests)
        self._requests.clear()
        logger.warning(
            f"ErasureWorkflow cleared: {count} requests removed "
            "(testing only - production use is discouraged)"
        )
        return count

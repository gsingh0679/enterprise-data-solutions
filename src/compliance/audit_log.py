"""Immutable append-only audit trail for compliance (GDPR, PCI-DSS, SOX).

This module provides an audit logging system that creates an immutable,
append-only record of all sensitive operations (masking, tokenization, etc.)
for compliance tracking and forensic analysis.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditEvent:
    """Immutable audit event representing a single logged action.

    This frozen dataclass ensures that once created, audit events cannot be
    modified, providing integrity guarantees for compliance requirements.

    Attributes:
        event_id: Unique event identifier (UUID format).
        timestamp: When the event occurred (UTC datetime).
        action: Type of action (e.g., "MASK_RECORD", "STORE_TOKEN", "DELETE_TOKEN").
        user: User who performed the action.
        tenant_id: Multi-tenant context identifier.
        record_id: Optional identifier of affected record/resource.
        details: Action-specific metadata (e.g., field names, strategies used).
        status: Outcome of action ("SUCCESS" or "FAILURE").
        error_message: Optional error details if status is "FAILURE".

    Raises:
        ValueError: If validation fails during initialization.
    """

    event_id: str
    timestamp: datetime
    action: str
    user: str
    tenant_id: str
    record_id: Optional[str]
    details: Dict[str, Any]
    status: str
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate event after initialization.

        Raises:
            ValueError: If any field fails validation.
        """
        self.validate()

    def validate(self) -> None:
        """Validate event invariants.

        Raises:
            ValueError: If any field contains invalid data.
        """
        # Validate event_id
        if not self.event_id or not isinstance(self.event_id, str):
            raise ValueError(
                f"event_id must be non-empty string, got {self.event_id!r}"
            )

        # Validate timestamp
        if not isinstance(self.timestamp, datetime):
            raise ValueError(
                f"timestamp must be datetime, got {type(self.timestamp).__name__}"
            )

        # Validate action
        if not self.action or not isinstance(self.action, str):
            raise ValueError(
                f"action must be non-empty string, got {self.action!r}"
            )

        # Validate user
        if not self.user or not isinstance(self.user, str):
            raise ValueError(f"user must be non-empty string, got {self.user!r}")

        # Validate tenant_id
        if not self.tenant_id or not isinstance(self.tenant_id, str):
            raise ValueError(
                f"tenant_id must be non-empty string, got {self.tenant_id!r}"
            )

        # Validate record_id (optional)
        if self.record_id is not None and not isinstance(self.record_id, str):
            raise ValueError(
                f"record_id must be string or None, "
                f"got {type(self.record_id).__name__}"
            )

        # Validate details
        if not isinstance(self.details, dict):
            raise ValueError(
                f"details must be dict, got {type(self.details).__name__}"
            )

        # Validate status
        valid_statuses = ["SUCCESS", "FAILURE"]
        if self.status not in valid_statuses:
            raise ValueError(
                f"status must be one of {valid_statuses}, got {self.status!r}"
            )

        # Validate error_message
        if self.error_message is not None and not isinstance(
            self.error_message, str
        ):
            raise ValueError(
                f"error_message must be string or None, "
                f"got {type(self.error_message).__name__}"
            )

        # FAILURE status should have error_message
        if self.status == "FAILURE" and not self.error_message:
            raise ValueError("FAILURE status requires error_message to be set")

        logger.debug(f"AuditEvent validated: {self.event_id} ({self.action})")


class AuditLog:
    """Singleton-like append-only audit log for immutable event storage.

    Maintains an ordered, immutable collection of audit events. Supports
    querying by action, tenant, and timestamp range. Implements singleton
    pattern for consistent instance across the application.

    Attributes:
        _instance: Singleton instance cache.
        _events: Immutable list of audit events (append-only).

    Example:
        >>> audit = AuditLog()
        >>> audit.log_event(
        ...     action="MASK_RECORD",
        ...     user="admin@example.com",
        ...     tenant_id="tenant_123",
        ...     details={"field": "ssn", "strategy": "HASH"},
        ...     status="SUCCESS"
        ... )
        >>> events = audit.get_events_by_action("MASK_RECORD")
        >>> len(events)
        1
    """

    _instance: Optional["AuditLog"] = None

    def __new__(cls) -> "AuditLog":
        """Create or return singleton instance.

        Ensures only one AuditLog instance exists across the application.

        Returns:
            The singleton AuditLog instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._events: List[AuditEvent] = []
            logger.info("AuditLog singleton instance created")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (testing only).

        Clears the cached singleton instance and all events. This method is
        intended for testing purposes only and should not be used in
        production code.

        Example:
            >>> AuditLog.reset()  # In tests only
        """
        if cls._instance is not None:
            cls._instance._events = []
        cls._instance = None
        logger.debug("AuditLog singleton instance reset (testing)")

    def log_event(
        self,
        action: str,
        user: str,
        tenant_id: str,
        details: Dict[str, Any],
        status: str,
        record_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """Log an audit event (append-only operation).

        Creates and appends an immutable audit event to the log. The event
        is assigned a unique ID and current UTC timestamp automatically.

        Args:
            action: Action type (e.g., "MASK_RECORD", "STORE_TOKEN").
            user: User who performed the action.
            tenant_id: Multi-tenant context identifier.
            details: Action-specific metadata dict.
            status: Outcome ("SUCCESS" or "FAILURE").
            record_id: Optional identifier of affected record.
            error_message: Optional error details (required if status="FAILURE").

        Returns:
            The event_id of the logged event.

        Raises:
            TypeError: If any argument has wrong type.
            ValueError: If any argument fails validation.

        Example:
            >>> audit = AuditLog()
            >>> event_id = audit.log_event(
            ...     action="MASK_RECORD",
            ...     user="admin@example.com",
            ...     tenant_id="tenant_123",
            ...     details={"field": "email", "strategy": "REDACT"},
            ...     status="SUCCESS"
            ... )
        """
        # Type validation
        if not isinstance(action, str) or not action:
            raise TypeError("action must be non-empty string")
        if not isinstance(user, str) or not user:
            raise TypeError("user must be non-empty string")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise TypeError("tenant_id must be non-empty string")
        if not isinstance(details, dict):
            raise TypeError("details must be dict")
        if not isinstance(status, str) or status not in ["SUCCESS", "FAILURE"]:
            raise TypeError("status must be 'SUCCESS' or 'FAILURE'")
        if record_id is not None and not isinstance(record_id, str):
            raise TypeError("record_id must be string or None")
        if error_message is not None and not isinstance(error_message, str):
            raise TypeError("error_message must be string or None")

        # Create event
        event_id = str(uuid4())
        timestamp = datetime.utcnow()

        event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            action=action,
            user=user,
            tenant_id=tenant_id,
            record_id=record_id,
            details=details,
            status=status,
            error_message=error_message,
        )

        # Append to log
        self._events.append(event)

        log_level = logging.INFO if status == "SUCCESS" else logging.WARNING
        logger.log(
            log_level,
            f"Audit event logged: {action} (status={status}, "
            f"user={user}, tenant={tenant_id}, event_id={event_id})",
        )

        return event_id

    def get_events(self) -> List[AuditEvent]:
        """Get all audit events.

        Returns:
            List of all audit events in chronological order.

        Example:
            >>> audit = AuditLog()
            >>> events = audit.get_events()
            >>> len(events)
            0
        """
        return list(self._events)

    def get_events_by_action(self, action: str) -> List[AuditEvent]:
        """Get events filtered by action type.

        Args:
            action: Action type to filter by (e.g., "MASK_RECORD").

        Returns:
            List of events with matching action in chronological order.

        Raises:
            TypeError: If action is not a string.

        Example:
            >>> audit = AuditLog()
            >>> events = audit.get_events_by_action("STORE_TOKEN")
        """
        if not isinstance(action, str):
            raise TypeError("action must be string")

        return [e for e in self._events if e.action == action]

    def get_events_by_tenant(self, tenant_id: str) -> List[AuditEvent]:
        """Get events filtered by tenant.

        Args:
            tenant_id: Tenant identifier to filter by.

        Returns:
            List of events for the tenant in chronological order.

        Raises:
            TypeError: If tenant_id is not a string.

        Example:
            >>> audit = AuditLog()
            >>> events = audit.get_events_by_tenant("tenant_abc")
        """
        if not isinstance(tenant_id, str):
            raise TypeError("tenant_id must be string")

        return [e for e in self._events if e.tenant_id == tenant_id]

    def get_events_by_timestamp(
        self, start: datetime, end: datetime
    ) -> List[AuditEvent]:
        """Get events within a timestamp range (inclusive).

        Args:
            start: Start of time range (UTC datetime).
            end: End of time range (UTC datetime).

        Returns:
            List of events within range in chronological order.

        Raises:
            TypeError: If start or end is not a datetime.
            ValueError: If start is after end.

        Example:
            >>> from datetime import datetime, timedelta
            >>> audit = AuditLog()
            >>> now = datetime.utcnow()
            >>> yesterday = now - timedelta(days=1)
            >>> events = audit.get_events_by_timestamp(yesterday, now)
        """
        if not isinstance(start, datetime):
            raise TypeError("start must be datetime")
        if not isinstance(end, datetime):
            raise TypeError("end must be datetime")
        if start > end:
            raise ValueError("start must be <= end")

        return [e for e in self._events if start <= e.timestamp <= end]

    def event_count(self) -> int:
        """Get the total number of events logged.

        Returns:
            Count of all audit events.

        Example:
            >>> audit = AuditLog()
            >>> count = audit.event_count()
            >>> count >= 0
            True
        """
        return len(self._events)

    def clear(self) -> int:
        """Clear all events (testing only).

        Removes all events from the audit log. Logs a warning in production
        environments as audit trails should be immutable.

        Returns:
            Number of events that were cleared.

        Example:
            >>> audit = AuditLog()
            >>> audit.log_event("TEST", "user", "tenant", {}, "SUCCESS")
            >>> count = audit.clear()
            >>> count
            1
        """
        count = len(self._events)
        self._events = []
        logger.warning(
            f"Audit log cleared: {count} events removed "
            "(testing only - production use is discouraged)"
        )
        return count

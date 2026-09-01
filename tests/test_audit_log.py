"""Tests for the audit_log module (immutable audit trail).

Tests cover CRUD operations, filtering, immutability, type validation,
singleton behavior, and compliance scenarios.
"""

import pytest
from datetime import datetime, timedelta

from src.compliance.audit_log import AuditEvent, AuditLog


class TestAuditEventInitialization:
    """Tests for AuditEvent initialization and validation."""

    def test_audit_event_creation_success(self) -> None:
        """AuditEvent can be created with valid parameters."""
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime.utcnow(),
            action="MASK_RECORD",
            user="admin@example.com",
            tenant_id="tenant_abc",
            record_id="rec_456",
            details={"field": "ssn", "strategy": "HASH"},
            status="SUCCESS",
        )

        assert event.event_id == "evt-123"
        assert event.action == "MASK_RECORD"
        assert event.user == "admin@example.com"
        assert event.tenant_id == "tenant_abc"
        assert event.record_id == "rec_456"
        assert event.status == "SUCCESS"
        assert event.details["field"] == "ssn"

    def test_audit_event_creation_failure_with_error(self) -> None:
        """AuditEvent can represent a failed action with error message."""
        event = AuditEvent(
            event_id="evt-456",
            timestamp=datetime.utcnow(),
            action="STORE_TOKEN",
            user="system",
            tenant_id="tenant_xyz",
            record_id=None,
            details={"value": "secret"},
            status="FAILURE",
            error_message="Storage unavailable",
        )

        assert event.status == "FAILURE"
        assert event.error_message == "Storage unavailable"
        assert event.record_id is None

    def test_audit_event_frozen_immutable(self) -> None:
        """AuditEvent is frozen and immutable after creation."""
        event = AuditEvent(
            event_id="evt-789",
            timestamp=datetime.utcnow(),
            action="DELETE_TOKEN",
            user="admin",
            tenant_id="tenant_123",
            record_id="rec_789",
            details={},
            status="SUCCESS",
        )

        with pytest.raises(AttributeError):
            event.action = "DIFFERENT_ACTION"  # type: ignore

        with pytest.raises(AttributeError):
            event.user = "different_user"  # type: ignore

    def test_audit_event_invalid_event_id(self) -> None:
        """AuditEvent rejects invalid event_id."""
        with pytest.raises(ValueError, match="event_id must be non-empty string"):
            AuditEvent(
                event_id="",
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                record_id=None,
                details={},
                status="SUCCESS",
            )

        with pytest.raises(ValueError, match="event_id must be non-empty string"):
            AuditEvent(
                event_id=None,  # type: ignore
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                record_id=None,
                details={},
                status="SUCCESS",
            )

    def test_audit_event_invalid_timestamp(self) -> None:
        """AuditEvent rejects invalid timestamp."""
        with pytest.raises(ValueError, match="timestamp must be datetime"):
            AuditEvent(
                event_id="evt-123",
                timestamp="2024-01-01",  # type: ignore
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                record_id=None,
                details={},
                status="SUCCESS",
            )

    def test_audit_event_invalid_action(self) -> None:
        """AuditEvent rejects invalid action."""
        with pytest.raises(ValueError, match="action must be non-empty string"):
            AuditEvent(
                event_id="evt-123",
                timestamp=datetime.utcnow(),
                action="",
                user="admin",
                tenant_id="tenant",
                record_id=None,
                details={},
                status="SUCCESS",
            )

    def test_audit_event_invalid_user(self) -> None:
        """AuditEvent rejects invalid user."""
        with pytest.raises(ValueError, match="user must be non-empty string"):
            AuditEvent(
                event_id="evt-123",
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="",
                tenant_id="tenant",
                record_id=None,
                details={},
                status="SUCCESS",
            )

    def test_audit_event_invalid_tenant_id(self) -> None:
        """AuditEvent rejects invalid tenant_id."""
        with pytest.raises(ValueError, match="tenant_id must be non-empty string"):
            AuditEvent(
                event_id="evt-123",
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="admin",
                tenant_id="",
                record_id=None,
                details={},
                status="SUCCESS",
            )

    def test_audit_event_invalid_record_id_type(self) -> None:
        """AuditEvent rejects non-string record_id."""
        with pytest.raises(ValueError, match="record_id must be string or None"):
            AuditEvent(
                event_id="evt-123",
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                record_id=123,  # type: ignore
                details={},
                status="SUCCESS",
            )

    def test_audit_event_invalid_details_type(self) -> None:
        """AuditEvent rejects non-dict details."""
        with pytest.raises(ValueError, match="details must be dict"):
            AuditEvent(
                event_id="evt-123",
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                record_id=None,
                details="not a dict",  # type: ignore
                status="SUCCESS",
            )

    def test_audit_event_invalid_status(self) -> None:
        """AuditEvent rejects invalid status."""
        with pytest.raises(ValueError, match="status must be one of"):
            AuditEvent(
                event_id="evt-123",
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                record_id=None,
                details={},
                status="PENDING",
            )

    def test_audit_event_failure_requires_error_message(self) -> None:
        """AuditEvent with FAILURE status requires error_message."""
        with pytest.raises(
            ValueError, match="FAILURE status requires error_message"
        ):
            AuditEvent(
                event_id="evt-123",
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                record_id=None,
                details={},
                status="FAILURE",
                error_message=None,
            )

    def test_audit_event_invalid_error_message_type(self) -> None:
        """AuditEvent rejects non-string error_message."""
        with pytest.raises(ValueError, match="error_message must be string or None"):
            AuditEvent(
                event_id="evt-123",
                timestamp=datetime.utcnow(),
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                record_id=None,
                details={},
                status="FAILURE",
                error_message=123,  # type: ignore
            )


class TestAuditLogSingleton:
    """Tests for AuditLog singleton pattern."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_audit_log_singleton_instance(self) -> None:
        """AuditLog returns same instance on multiple calls."""
        log1 = AuditLog()
        log2 = AuditLog()

        assert log1 is log2

    def test_audit_log_reset_clears_events(self) -> None:
        """Resetting AuditLog clears all events."""
        log = AuditLog()
        log.log_event("TEST", "user", "tenant", {}, "SUCCESS")

        assert log.event_count() == 1

        AuditLog.reset()
        log = AuditLog()

        assert log.event_count() == 0

    def test_audit_log_reset_creates_new_instance(self) -> None:
        """Resetting creates new singleton instance."""
        log1 = AuditLog()
        log1.log_event("TEST", "user", "tenant", {}, "SUCCESS")

        AuditLog.reset()
        log2 = AuditLog()

        assert log1 is not log2
        assert log2.event_count() == 0


class TestLogEvent:
    """Tests for log_event method."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_log_event_success(self) -> None:
        """log_event successfully records an event."""
        audit = AuditLog()
        event_id = audit.log_event(
            action="MASK_RECORD",
            user="admin@example.com",
            tenant_id="tenant_123",
            details={"field": "email", "strategy": "REDACT"},
            status="SUCCESS",
        )

        assert isinstance(event_id, str)
        assert len(event_id) > 0
        assert audit.event_count() == 1

    def test_log_event_failure(self) -> None:
        """log_event records failed operations with error message."""
        audit = AuditLog()
        event_id = audit.log_event(
            action="STORE_TOKEN",
            user="system",
            tenant_id="tenant_456",
            details={"value": "secret"},
            status="FAILURE",
            error_message="Storage unavailable",
        )

        assert audit.event_count() == 1
        events = audit.get_events()
        assert events[0].status == "FAILURE"
        assert events[0].error_message == "Storage unavailable"

    def test_log_event_with_record_id(self) -> None:
        """log_event includes record_id when provided."""
        audit = AuditLog()
        audit.log_event(
            action="MASK_RECORD",
            user="admin",
            tenant_id="tenant",
            details={},
            status="SUCCESS",
            record_id="rec_abc_123",
        )

        events = audit.get_events()
        assert events[0].record_id == "rec_abc_123"

    def test_log_event_without_record_id(self) -> None:
        """log_event works without record_id."""
        audit = AuditLog()
        audit.log_event(
            action="STORE_TOKEN",
            user="system",
            tenant_id="tenant",
            details={},
            status="SUCCESS",
        )

        events = audit.get_events()
        assert events[0].record_id is None

    def test_log_event_preserves_details(self) -> None:
        """log_event preserves complex details dict."""
        audit = AuditLog()
        details = {
            "field": "ssn",
            "strategy": "HASH",
            "original_length": 11,
            "masked_value": "abc123...",
            "nested": {"key": "value"},
        }

        audit.log_event(
            action="MASK_RECORD",
            user="admin",
            tenant_id="tenant",
            details=details,
            status="SUCCESS",
        )

        events = audit.get_events()
        assert events[0].details == details

    def test_log_event_invalid_action_type(self) -> None:
        """log_event rejects non-string action."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="action must be non-empty string"):
            audit.log_event(
                action=123,  # type: ignore
                user="admin",
                tenant_id="tenant",
                details={},
                status="SUCCESS",
            )

    def test_log_event_invalid_user_type(self) -> None:
        """log_event rejects non-string user."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="user must be non-empty string"):
            audit.log_event(
                action="MASK_RECORD",
                user=None,  # type: ignore
                tenant_id="tenant",
                details={},
                status="SUCCESS",
            )

    def test_log_event_invalid_tenant_type(self) -> None:
        """log_event rejects non-string tenant_id."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="tenant_id must be non-empty string"):
            audit.log_event(
                action="MASK_RECORD",
                user="admin",
                tenant_id="",
                details={},
                status="SUCCESS",
            )

    def test_log_event_invalid_details_type(self) -> None:
        """log_event rejects non-dict details."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="details must be dict"):
            audit.log_event(
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                details="not a dict",  # type: ignore
                status="SUCCESS",
            )

    def test_log_event_invalid_status(self) -> None:
        """log_event rejects invalid status."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="status must be 'SUCCESS' or 'FAILURE'"):
            audit.log_event(
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                details={},
                status="PENDING",  # type: ignore
            )

    def test_log_event_invalid_record_id_type(self) -> None:
        """log_event rejects non-string record_id."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="record_id must be string or None"):
            audit.log_event(
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                details={},
                status="SUCCESS",
                record_id=123,  # type: ignore
            )

    def test_log_event_invalid_error_message_type(self) -> None:
        """log_event rejects non-string error_message."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="error_message must be string or None"):
            audit.log_event(
                action="MASK_RECORD",
                user="admin",
                tenant_id="tenant",
                details={},
                status="FAILURE",
                error_message=123,  # type: ignore
            )

    def test_log_event_multiple_events(self) -> None:
        """log_event maintains append-only order."""
        audit = AuditLog()

        id1 = audit.log_event("ACTION_1", "user1", "tenant", {}, "SUCCESS")
        id2 = audit.log_event("ACTION_2", "user2", "tenant", {}, "SUCCESS")
        id3 = audit.log_event("ACTION_3", "user3", "tenant", {}, "SUCCESS")

        events = audit.get_events()
        assert len(events) == 3
        assert events[0].action == "ACTION_1"
        assert events[1].action == "ACTION_2"
        assert events[2].action == "ACTION_3"

    def test_log_event_timestamp_auto_assigned(self) -> None:
        """log_event automatically assigns current UTC timestamp."""
        audit = AuditLog()
        before = datetime.utcnow()

        audit.log_event("ACTION", "user", "tenant", {}, "SUCCESS")

        after = datetime.utcnow()
        event = audit.get_events()[0]

        assert before <= event.timestamp <= after


class TestGetEvents:
    """Tests for get_events method."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_get_events_empty(self) -> None:
        """get_events returns empty list when no events logged."""
        audit = AuditLog()
        assert audit.get_events() == []

    def test_get_events_returns_all(self) -> None:
        """get_events returns all logged events."""
        audit = AuditLog()
        audit.log_event("ACTION_1", "user", "tenant", {}, "SUCCESS")
        audit.log_event("ACTION_2", "user", "tenant", {}, "SUCCESS")
        audit.log_event("ACTION_3", "user", "tenant", {}, "SUCCESS")

        events = audit.get_events()
        assert len(events) == 3

    def test_get_events_returns_copy(self) -> None:
        """get_events returns a copy, not the internal list."""
        audit = AuditLog()
        audit.log_event("ACTION_1", "user", "tenant", {}, "SUCCESS")

        events = audit.get_events()
        events.clear()

        # Clearing returned list doesn't affect internal state
        assert audit.event_count() == 1


class TestGetEventsByAction:
    """Tests for get_events_by_action filtering method."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_get_events_by_action_matches(self) -> None:
        """get_events_by_action returns events with matching action."""
        audit = AuditLog()
        audit.log_event("MASK_RECORD", "user", "tenant", {}, "SUCCESS")
        audit.log_event("MASK_RECORD", "user", "tenant", {}, "SUCCESS")
        audit.log_event("STORE_TOKEN", "user", "tenant", {}, "SUCCESS")

        mask_events = audit.get_events_by_action("MASK_RECORD")
        assert len(mask_events) == 2
        assert all(e.action == "MASK_RECORD" for e in mask_events)

    def test_get_events_by_action_no_matches(self) -> None:
        """get_events_by_action returns empty list for non-matching action."""
        audit = AuditLog()
        audit.log_event("MASK_RECORD", "user", "tenant", {}, "SUCCESS")

        events = audit.get_events_by_action("DELETE_TOKEN")
        assert events == []

    def test_get_events_by_action_invalid_type(self) -> None:
        """get_events_by_action rejects non-string action."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="action must be string"):
            audit.get_events_by_action(123)  # type: ignore


class TestGetEventsByTenant:
    """Tests for get_events_by_tenant filtering method."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_get_events_by_tenant_matches(self) -> None:
        """get_events_by_tenant returns events for specified tenant."""
        audit = AuditLog()
        audit.log_event("ACTION", "user", "tenant_a", {}, "SUCCESS")
        audit.log_event("ACTION", "user", "tenant_b", {}, "SUCCESS")
        audit.log_event("ACTION", "user", "tenant_a", {}, "SUCCESS")

        tenant_a_events = audit.get_events_by_tenant("tenant_a")
        assert len(tenant_a_events) == 2
        assert all(e.tenant_id == "tenant_a" for e in tenant_a_events)

    def test_get_events_by_tenant_no_matches(self) -> None:
        """get_events_by_tenant returns empty list for non-existent tenant."""
        audit = AuditLog()
        audit.log_event("ACTION", "user", "tenant_a", {}, "SUCCESS")

        events = audit.get_events_by_tenant("tenant_nonexistent")
        assert events == []

    def test_get_events_by_tenant_invalid_type(self) -> None:
        """get_events_by_tenant rejects non-string tenant_id."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="tenant_id must be string"):
            audit.get_events_by_tenant(123)  # type: ignore


class TestGetEventsByTimestamp:
    """Tests for get_events_by_timestamp filtering method."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_get_events_by_timestamp_range(self) -> None:
        """get_events_by_timestamp filters by time range (inclusive)."""
        audit = AuditLog()
        now = datetime.utcnow()
        earlier = now - timedelta(hours=2)
        later = now + timedelta(hours=2)

        # We can't easily control event timestamps, so we log and check
        audit.log_event("ACTION", "user", "tenant", {}, "SUCCESS")

        # With a wide range, should capture the event
        events = audit.get_events_by_timestamp(earlier, later)
        assert len(events) == 1

    def test_get_events_by_timestamp_excludes_outside_range(self) -> None:
        """get_events_by_timestamp excludes events outside range."""
        audit = AuditLog()
        now = datetime.utcnow()
        future = now + timedelta(hours=1)
        far_future = now + timedelta(hours=2)

        audit.log_event("ACTION", "user", "tenant", {}, "SUCCESS")

        # Range is in the future, should not capture the event
        events = audit.get_events_by_timestamp(future, far_future)
        assert len(events) == 0

    def test_get_events_by_timestamp_invalid_start_type(self) -> None:
        """get_events_by_timestamp rejects non-datetime start."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="start must be datetime"):
            audit.get_events_by_timestamp("2024-01-01", datetime.utcnow())  # type: ignore

    def test_get_events_by_timestamp_invalid_end_type(self) -> None:
        """get_events_by_timestamp rejects non-datetime end."""
        audit = AuditLog()

        with pytest.raises(TypeError, match="end must be datetime"):
            audit.get_events_by_timestamp(datetime.utcnow(), "2024-01-01")  # type: ignore

    def test_get_events_by_timestamp_start_after_end(self) -> None:
        """get_events_by_timestamp rejects start after end."""
        audit = AuditLog()
        now = datetime.utcnow()
        past = now - timedelta(hours=1)

        with pytest.raises(ValueError, match="start must be <= end"):
            audit.get_events_by_timestamp(now, past)


class TestEventCount:
    """Tests for event_count method."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_event_count_empty(self) -> None:
        """event_count returns 0 when no events logged."""
        audit = AuditLog()
        assert audit.event_count() == 0

    def test_event_count_increments(self) -> None:
        """event_count increments with each log_event call."""
        audit = AuditLog()

        for i in range(1, 6):
            audit.log_event("ACTION", "user", "tenant", {}, "SUCCESS")
            assert audit.event_count() == i


class TestClear:
    """Tests for clear method (testing only)."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_clear_removes_all_events(self) -> None:
        """clear() removes all events."""
        audit = AuditLog()
        audit.log_event("ACTION_1", "user", "tenant", {}, "SUCCESS")
        audit.log_event("ACTION_2", "user", "tenant", {}, "SUCCESS")
        audit.log_event("ACTION_3", "user", "tenant", {}, "SUCCESS")

        count = audit.clear()

        assert count == 3
        assert audit.event_count() == 0
        assert audit.get_events() == []

    def test_clear_empty_log(self) -> None:
        """clear() on empty log returns 0."""
        audit = AuditLog()
        count = audit.clear()

        assert count == 0


class TestComplianceScenarios:
    """Tests for compliance and audit trail scenarios."""

    def setup_method(self) -> None:
        """Reset AuditLog before each test."""
        AuditLog.reset()

    def test_audit_trail_gdpr_masking_operations(self) -> None:
        """Audit trail captures GDPR-relevant masking operations."""
        audit = AuditLog()

        # Log masking operations for GDPR compliance
        audit.log_event(
            action="MASK_RECORD",
            user="data_processor@company.com",
            tenant_id="gdpr_tenant",
            record_id="customer_123",
            details={"field": "email", "strategy": "REDACT", "reason": "GDPR_REQUEST"},
            status="SUCCESS",
        )

        audit.log_event(
            action="MASK_RECORD",
            user="data_processor@company.com",
            tenant_id="gdpr_tenant",
            record_id="customer_123",
            details={"field": "phone", "strategy": "REDACT", "reason": "GDPR_REQUEST"},
            status="SUCCESS",
        )

        # Query for GDPR operations
        events = audit.get_events_by_tenant("gdpr_tenant")
        mask_events = audit.get_events_by_action("MASK_RECORD")

        assert len(events) == 2
        assert len(mask_events) == 2
        assert all(
            "GDPR_REQUEST" in e.details.get("reason", "")
            for e in mask_events
        )

    def test_audit_trail_pci_dss_tokenization(self) -> None:
        """Audit trail captures PCI-DSS relevant tokenization operations."""
        audit = AuditLog()

        # Log successful tokenization
        audit.log_event(
            action="STORE_TOKEN",
            user="payment_processor",
            tenant_id="pci_tenant",
            details={"value_type": "credit_card", "length": 16},
            status="SUCCESS",
        )

        # Log failed tokenization
        audit.log_event(
            action="STORE_TOKEN",
            user="payment_processor",
            tenant_id="pci_tenant",
            details={"value_type": "credit_card"},
            status="FAILURE",
            error_message="Vault unavailable",
        )

        events = audit.get_events_by_action("STORE_TOKEN")
        assert len(events) == 2
        assert events[0].status == "SUCCESS"
        assert events[1].status == "FAILURE"
        assert events[1].error_message == "Vault unavailable"

    def test_audit_trail_sox_immutability(self) -> None:
        """Audit trail is immutable (SOX compliance)."""
        audit = AuditLog()

        # Log SOX-relevant operation
        audit.log_event(
            action="DELETE_TOKEN",
            user="compliance_officer",
            tenant_id="sox_tenant",
            record_id="token_123",
            details={"reason": "RETENTION_POLICY", "days_old": 730},
            status="SUCCESS",
        )

        events = audit.get_events()
        original_event = events[0]

        # Verify event is immutable
        with pytest.raises(AttributeError):
            original_event.action = "MODIFIED"  # type: ignore

        # Verify log cannot be modified externally
        events.clear()
        assert audit.event_count() == 1

    def test_audit_trail_multi_tenant_isolation(self) -> None:
        """Audit trail maintains multi-tenant isolation."""
        audit = AuditLog()

        # Operations for tenant A
        audit.log_event("ACTION_1", "user_a", "tenant_a", {}, "SUCCESS")
        audit.log_event("ACTION_2", "user_a", "tenant_a", {}, "SUCCESS")

        # Operations for tenant B
        audit.log_event("ACTION_1", "user_b", "tenant_b", {}, "SUCCESS")
        audit.log_event("ACTION_3", "user_b", "tenant_b", {}, "SUCCESS")

        # Verify isolation
        tenant_a_events = audit.get_events_by_tenant("tenant_a")
        tenant_b_events = audit.get_events_by_tenant("tenant_b")

        assert len(tenant_a_events) == 2
        assert len(tenant_b_events) == 2
        assert all(e.tenant_id == "tenant_a" for e in tenant_a_events)
        assert all(e.tenant_id == "tenant_b" for e in tenant_b_events)

    def test_audit_trail_append_only_compliance(self) -> None:
        """Audit trail enforces append-only semantics for compliance."""
        audit = AuditLog()

        # Log initial events
        audit.log_event("OP_1", "user", "tenant", {}, "SUCCESS")
        audit.log_event("OP_2", "user", "tenant", {}, "SUCCESS")

        # Verify append-only behavior
        assert audit.event_count() == 2
        events_before = audit.get_events()

        # Log more events
        audit.log_event("OP_3", "user", "tenant", {}, "SUCCESS")

        events_after = audit.get_events()
        assert len(events_after) == 3

        # Original events are still in order
        assert events_after[0].action == "OP_1"
        assert events_after[1].action == "OP_2"
        assert events_after[2].action == "OP_3"

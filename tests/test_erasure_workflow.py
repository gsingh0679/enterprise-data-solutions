"""Tests for the erasure_workflow module (GDPR right-to-be-forgotten).

Coverage targets:
- ErasureRequest dataclass validation
- ErasureWorkflow lifecycle (submit, execute, query)
- Atomic deletion with rollback
- Audit logging integration
- Compliance scenarios
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from src.erasure_workflow import (
    ErasureRequest,
    ErasureWorkflow,
    ErasureReason,
    ErasureStatus,
)
from src.vault import MockVault
from src.audit_log import AuditLog


class TestErasureRequest:
    """Tests for ErasureRequest dataclass."""

    def test_valid_erasure_request(self):
        """Test creating a valid erasure request."""
        request_id = str(uuid4())
        created_at = datetime.utcnow()

        request = ErasureRequest(
            request_id=request_id,
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields_to_delete=["email", "ssn"],
            created_at=created_at,
            status=ErasureStatus.PENDING,
        )

        assert request.request_id == request_id
        assert request.user_id == "user_123"
        assert request.tenant_id == "tenant_abc"
        assert request.reason == ErasureReason.GDPR_DELETION
        assert request.fields_to_delete == ["email", "ssn"]
        assert request.status == ErasureStatus.PENDING
        assert request.executed_at is None
        assert request.error_message is None

    def test_erasure_request_with_execution(self):
        """Test erasure request with execution details."""
        request_id = str(uuid4())
        created_at = datetime.utcnow()
        executed_at = datetime.utcnow()

        request = ErasureRequest(
            request_id=request_id,
            user_id="user_456",
            tenant_id="tenant_xyz",
            reason=ErasureReason.RETENTION_POLICY,
            fields_to_delete=["phone"],
            created_at=created_at,
            status=ErasureStatus.COMPLETE,
            executed_at=executed_at,
        )

        assert request.status == ErasureStatus.COMPLETE
        assert request.executed_at == executed_at

    def test_erasure_request_with_failure(self):
        """Test erasure request with failure status."""
        request_id = str(uuid4())
        created_at = datetime.utcnow()
        executed_at = datetime.utcnow()

        request = ErasureRequest(
            request_id=request_id,
            user_id="user_789",
            tenant_id="tenant_pqr",
            reason=ErasureReason.USER_REQUEST,
            fields_to_delete=["dob"],
            created_at=created_at,
            status=ErasureStatus.FAILED,
            executed_at=executed_at,
            error_message="Token deletion failed",
        )

        assert request.status == ErasureStatus.FAILED
        assert request.error_message == "Token deletion failed"

    def test_erasure_request_immutable(self):
        """Test that erasure request is frozen (immutable)."""
        request_id = str(uuid4())
        request = ErasureRequest(
            request_id=request_id,
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields_to_delete=["email"],
            created_at=datetime.utcnow(),
            status=ErasureStatus.PENDING,
        )

        with pytest.raises(AttributeError):
            request.user_id = "user_456"

    def test_erasure_request_invalid_request_id(self):
        """Test validation of invalid request_id."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id="",
                user_id="user_123",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=["email"],
                created_at=datetime.utcnow(),
                status=ErasureStatus.PENDING,
            )

    def test_erasure_request_invalid_user_id(self):
        """Test validation of invalid user_id."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=["email"],
                created_at=datetime.utcnow(),
                status=ErasureStatus.PENDING,
            )

    def test_erasure_request_invalid_tenant_id(self):
        """Test validation of invalid tenant_id."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="user_123",
                tenant_id="",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=["email"],
                created_at=datetime.utcnow(),
                status=ErasureStatus.PENDING,
            )

    def test_erasure_request_invalid_reason(self):
        """Test validation of invalid reason."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="user_123",
                tenant_id="tenant_abc",
                reason="",
                fields_to_delete=["email"],
                created_at=datetime.utcnow(),
                status=ErasureStatus.PENDING,
            )

    def test_erasure_request_empty_fields_to_delete(self):
        """Test validation of empty fields_to_delete."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="user_123",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=[],
                created_at=datetime.utcnow(),
                status=ErasureStatus.PENDING,
            )

    def test_erasure_request_invalid_field_type(self):
        """Test validation of invalid field type in fields_to_delete."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="user_123",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=["email", 123],
                created_at=datetime.utcnow(),
                status=ErasureStatus.PENDING,
            )

    def test_erasure_request_invalid_status(self):
        """Test validation of invalid status."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="user_123",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=["email"],
                created_at=datetime.utcnow(),
                status="INVALID_STATUS",
            )

    def test_erasure_request_failed_without_error_message(self):
        """Test that FAILED status requires error_message."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="user_123",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=["email"],
                created_at=datetime.utcnow(),
                status=ErasureStatus.FAILED,
            )

    def test_erasure_request_invalid_created_at(self):
        """Test validation of invalid created_at."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="user_123",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=["email"],
                created_at="not a datetime",
                status=ErasureStatus.PENDING,
            )

    def test_erasure_request_invalid_executed_at(self):
        """Test validation of invalid executed_at."""
        with pytest.raises(ValueError):
            ErasureRequest(
                request_id=str(uuid4()),
                user_id="user_123",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields_to_delete=["email"],
                created_at=datetime.utcnow(),
                status=ErasureStatus.COMPLETE,
                executed_at="not a datetime",
            )


class TestErasureWorkflow:
    """Tests for ErasureWorkflow class."""

    @pytest.fixture
    def vault(self):
        """Create a fresh vault for each test."""
        return MockVault()

    @pytest.fixture
    def workflow(self, vault):
        """Create a fresh workflow for each test."""
        AuditLog.reset()
        return ErasureWorkflow(vault)

    def test_workflow_initialization(self, vault):
        """Test workflow initialization."""
        workflow = ErasureWorkflow(vault)
        assert workflow.vault == vault
        assert workflow.audit_log is not None
        assert workflow.request_count() == 0

    def test_workflow_invalid_vault_type(self):
        """Test that workflow rejects invalid vault type."""
        with pytest.raises(TypeError):
            ErasureWorkflow("not a vault")

    def test_submit_request(self, workflow):
        """Test submitting an erasure request."""
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email", "ssn"],
        )

        assert request_id is not None
        assert workflow.request_count() == 1

        request = workflow.get_request(request_id)
        assert request is not None
        assert request.user_id == "user_123"
        assert request.tenant_id == "tenant_abc"
        assert request.reason == ErasureReason.GDPR_DELETION
        assert request.fields_to_delete == ["email", "ssn"]
        assert request.status == ErasureStatus.PENDING

    def test_submit_request_audit_logging(self, workflow):
        """Test that request submission is logged."""
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )

        audit = AuditLog()
        events = audit.get_events_by_action("ERASURE_REQUEST_SUBMITTED")
        assert len(events) == 1
        assert events[0].details["request_id"] == request_id
        assert events[0].details["reason"] == ErasureReason.GDPR_DELETION

    def test_submit_request_invalid_user_id(self, workflow):
        """Test submit_request with invalid user_id."""
        with pytest.raises(TypeError):
            workflow.submit_request(
                user_id="",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields=["email"],
            )

    def test_submit_request_invalid_tenant_id(self, workflow):
        """Test submit_request with invalid tenant_id."""
        with pytest.raises(TypeError):
            workflow.submit_request(
                user_id="user_123",
                tenant_id="",
                reason=ErasureReason.GDPR_DELETION,
                fields=["email"],
            )

    def test_submit_request_invalid_reason(self, workflow):
        """Test submit_request with invalid reason."""
        with pytest.raises(TypeError):
            workflow.submit_request(
                user_id="user_123",
                tenant_id="tenant_abc",
                reason="",
                fields=["email"],
            )

    def test_submit_request_invalid_fields(self, workflow):
        """Test submit_request with invalid fields."""
        with pytest.raises(TypeError):
            workflow.submit_request(
                user_id="user_123",
                tenant_id="tenant_abc",
                reason=ErasureReason.GDPR_DELETION,
                fields=[],
            )

    def test_get_request_found(self, workflow):
        """Test retrieving an existing request."""
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )

        request = workflow.get_request(request_id)
        assert request is not None
        assert request.request_id == request_id

    def test_get_request_not_found(self, workflow):
        """Test retrieving a non-existent request."""
        request = workflow.get_request(str(uuid4()))
        assert request is None

    def test_get_request_invalid_request_id(self, workflow):
        """Test get_request with invalid request_id."""
        with pytest.raises(TypeError):
            workflow.get_request(123)

    def test_execute_request_success(self, vault, workflow):
        """Test successful request execution."""
        # Store some tokens first
        token1 = vault.store_token("credit_card_4532")
        token2 = vault.store_token("ssn_123-45-6789")
        assert vault.token_count() == 2

        # Submit and execute request
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email", "ssn"],
        )

        success = workflow.execute_request(request_id)
        assert success is True
        assert vault.token_count() == 0

        # Verify request status
        request = workflow.get_request(request_id)
        assert request.status == ErasureStatus.COMPLETE
        assert request.executed_at is not None

    def test_execute_request_not_found(self, workflow):
        """Test execution of non-existent request."""
        success = workflow.execute_request(str(uuid4()))
        assert success is False

    def test_execute_request_invalid_status(self, workflow):
        """Test execution when request is not PENDING."""
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )

        # First execution should succeed
        workflow.execute_request(request_id)

        # Second execution should fail (status is now COMPLETE)
        with pytest.raises(ValueError):
            workflow.execute_request(request_id)

    def test_execute_request_audit_logging(self, vault, workflow):
        """Test that execution is logged."""
        vault.store_token("credit_card")
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )

        workflow.execute_request(request_id)

        audit = AuditLog()
        started = audit.get_events_by_action("ERASURE_EXECUTION_STARTED")
        completed = audit.get_events_by_action("ERASURE_EXECUTION_COMPLETED")

        assert len(started) == 1
        assert len(completed) == 1
        assert completed[0].details["request_id"] == request_id

    def test_execute_request_invalid_request_id_type(self, workflow):
        """Test execute_request with invalid request_id type."""
        with pytest.raises(TypeError):
            workflow.execute_request(123)

    def test_get_requests_by_status_pending(self, workflow):
        """Test filtering requests by PENDING status."""
        req1 = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )
        req2 = workflow.submit_request(
            user_id="user_456",
            tenant_id="tenant_abc",
            reason=ErasureReason.USER_REQUEST,
            fields=["phone"],
        )

        pending = workflow.get_requests_by_status(ErasureStatus.PENDING)
        assert len(pending) == 2

    def test_get_requests_by_status_complete(self, vault, workflow):
        """Test filtering requests by COMPLETE status."""
        vault.store_token("token")
        req1 = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )
        req2 = workflow.submit_request(
            user_id="user_456",
            tenant_id="tenant_abc",
            reason=ErasureReason.USER_REQUEST,
            fields=["phone"],
        )

        workflow.execute_request(req1)

        pending = workflow.get_requests_by_status(ErasureStatus.PENDING)
        complete = workflow.get_requests_by_status(ErasureStatus.COMPLETE)

        assert len(pending) == 1
        assert len(complete) == 1

    def test_get_requests_by_status_invalid_type(self, workflow):
        """Test get_requests_by_status with invalid status type."""
        with pytest.raises(TypeError):
            workflow.get_requests_by_status(123)

    def test_get_requests_by_tenant(self, workflow):
        """Test filtering requests by tenant."""
        req1 = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )
        req2 = workflow.submit_request(
            user_id="user_456",
            tenant_id="tenant_abc",
            reason=ErasureReason.USER_REQUEST,
            fields=["phone"],
        )
        req3 = workflow.submit_request(
            user_id="user_789",
            tenant_id="tenant_xyz",
            reason=ErasureReason.RETENTION_POLICY,
            fields=["dob"],
        )

        abc_requests = workflow.get_requests_by_tenant("tenant_abc")
        xyz_requests = workflow.get_requests_by_tenant("tenant_xyz")

        assert len(abc_requests) == 2
        assert len(xyz_requests) == 1

    def test_get_requests_by_tenant_invalid_type(self, workflow):
        """Test get_requests_by_tenant with invalid tenant_id type."""
        with pytest.raises(TypeError):
            workflow.get_requests_by_tenant(123)

    def test_get_all_requests(self, workflow):
        """Test retrieving all requests."""
        req1 = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )
        req2 = workflow.submit_request(
            user_id="user_456",
            tenant_id="tenant_abc",
            reason=ErasureReason.USER_REQUEST,
            fields=["phone"],
        )

        all_requests = workflow.get_all_requests()
        assert len(all_requests) == 2

    def test_request_count(self, workflow):
        """Test request counting."""
        assert workflow.request_count() == 0

        workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )
        assert workflow.request_count() == 1

        workflow.submit_request(
            user_id="user_456",
            tenant_id="tenant_abc",
            reason=ErasureReason.USER_REQUEST,
            fields=["phone"],
        )
        assert workflow.request_count() == 2

    def test_clear_requests(self, workflow):
        """Test clearing all requests."""
        workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )
        assert workflow.request_count() == 1

        cleared = workflow.clear()
        assert cleared == 1
        assert workflow.request_count() == 0


class TestErasureScenarios:
    """Integration tests for compliance scenarios."""

    @pytest.fixture
    def vault(self):
        """Create a fresh vault for each test."""
        return MockVault()

    @pytest.fixture
    def workflow(self, vault):
        """Create a fresh workflow for each test."""
        AuditLog.reset()
        return ErasureWorkflow(vault)

    def test_gdpr_deletion_scenario(self, vault, workflow):
        """Test GDPR right-to-be-forgotten scenario."""
        # User data is stored as tokens
        email_token = vault.store_token("user@example.com")
        ssn_token = vault.store_token("123-45-6789")
        phone_token = vault.store_token("555-1234")

        assert vault.token_count() == 3

        # User submits deletion request
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email", "ssn", "phone"],
        )

        # Request is pending
        request = workflow.get_request(request_id)
        assert request.status == ErasureStatus.PENDING

        # Execute deletion
        success = workflow.execute_request(request_id)
        assert success is True

        # All tokens are deleted
        assert vault.token_count() == 0

        # Request is complete
        request = workflow.get_request(request_id)
        assert request.status == ErasureStatus.COMPLETE

    def test_retention_policy_scenario(self, vault, workflow):
        """Test data deletion due to retention policy expiration."""
        # Store old data
        old_token = vault.store_token("old_data")
        assert vault.token_count() == 1

        # Create retention policy deletion request
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.RETENTION_POLICY,
            fields=["archived_record"],
        )

        # Execute deletion
        success = workflow.execute_request(request_id)
        assert success is True
        assert vault.token_count() == 0

    def test_account_closure_scenario(self, vault, workflow):
        """Test account closure deletion scenario."""
        # User has multiple data points
        token1 = vault.store_token("email@example.com")
        token2 = vault.store_token("profile_data")
        token3 = vault.store_token("payment_info")
        assert vault.token_count() == 3

        # Account closure request
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.ACCOUNT_CLOSURE,
            fields=["email", "profile", "payment"],
        )

        # Execute deletion
        success = workflow.execute_request(request_id)
        assert success is True
        assert vault.token_count() == 0

    def test_audit_trail_immutability(self, vault, workflow):
        """Test that audit trail is immutable even after erasure."""
        vault.store_token("data")
        request_id = workflow.submit_request(
            user_id="user_123",
            tenant_id="tenant_abc",
            reason=ErasureReason.GDPR_DELETION,
            fields=["data"],
        )

        workflow.execute_request(request_id)

        # Audit trail should still have all events
        audit = AuditLog()
        all_events = audit.get_events()
        assert len(all_events) > 0

        # No events should be deleted
        for event in all_events:
            assert event.action in [
                "ERASURE_REQUEST_SUBMITTED",
                "ERASURE_EXECUTION_STARTED",
                "ERASURE_EXECUTION_COMPLETED",
            ]

    def test_multi_tenant_isolation(self, workflow):
        """Test that requests are properly isolated by tenant."""
        req_a1 = workflow.submit_request(
            user_id="user_a1",
            tenant_id="tenant_a",
            reason=ErasureReason.GDPR_DELETION,
            fields=["email"],
        )
        req_a2 = workflow.submit_request(
            user_id="user_a2",
            tenant_id="tenant_a",
            reason=ErasureReason.USER_REQUEST,
            fields=["phone"],
        )
        req_b1 = workflow.submit_request(
            user_id="user_b1",
            tenant_id="tenant_b",
            reason=ErasureReason.RETENTION_POLICY,
            fields=["dob"],
        )

        tenant_a = workflow.get_requests_by_tenant("tenant_a")
        tenant_b = workflow.get_requests_by_tenant("tenant_b")

        assert len(tenant_a) == 2
        assert len(tenant_b) == 1

        # Verify isolation
        assert all(r.tenant_id == "tenant_a" for r in tenant_a)
        assert all(r.tenant_id == "tenant_b" for r in tenant_b)

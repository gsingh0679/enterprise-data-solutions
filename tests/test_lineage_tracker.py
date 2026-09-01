"""Tests for the lineage_tracker module (data provenance tracking).

Coverage targets:
- LineageEvent dataclass validation
- LineageTracker lifecycle (track, query, graph building)
- Bidirectional lineage queries (upstream, downstream)
- Graph visualization support
- Audit logging integration
- Compliance scenarios (data flow visibility)
"""

import pytest
from datetime import datetime
from uuid import uuid4

from src.lineage_tracker import (
    LineageEvent,
    LineageTracker,
    TransformationType,
)
from src.audit_log import AuditLog


class TestLineageEvent:
    """Tests for LineageEvent dataclass."""

    def test_valid_lineage_event(self):
        """Test creating a valid lineage event."""
        event_id = str(uuid4())
        timestamp = datetime.utcnow()

        event = LineageEvent(
            event_id=event_id,
            timestamp=timestamp,
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin@example.com",
            tenant_id="tenant_abc",
            metadata={"fields": ["email", "ssn"], "strategy": "hash"},
        )

        assert event.event_id == event_id
        assert event.source_dataset == "raw_users"
        assert event.destination_dataset == "masked_users"
        assert event.transformation == TransformationType.MASK
        assert event.user == "admin@example.com"
        assert event.tenant_id == "tenant_abc"
        assert event.metadata["fields"] == ["email", "ssn"]

    def test_lineage_event_minimal_metadata(self):
        """Test lineage event with empty metadata."""
        event = LineageEvent(
            event_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            source_dataset="dataset_a",
            destination_dataset="dataset_b",
            transformation=TransformationType.COPY,
            user="user_123",
            tenant_id="tenant_xyz",
            metadata={},
        )

        assert event.metadata == {}

    def test_lineage_event_immutable(self):
        """Test that lineage event is frozen (immutable)."""
        event = LineageEvent(
            event_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            source_dataset="raw_data",
            destination_dataset="processed_data",
            transformation=TransformationType.FILTER,
            user="analyst",
            tenant_id="tenant_123",
            metadata={},
        )

        with pytest.raises(AttributeError):
            event.source_dataset = "new_source"

    def test_lineage_event_invalid_event_id(self):
        """Test validation of invalid event_id."""
        with pytest.raises(ValueError):
            LineageEvent(
                event_id="",
                timestamp=datetime.utcnow(),
                source_dataset="raw_users",
                destination_dataset="masked_users",
                transformation=TransformationType.MASK,
                user="admin",
                tenant_id="tenant_abc",
                metadata={},
            )

    def test_lineage_event_invalid_timestamp(self):
        """Test validation of invalid timestamp."""
        with pytest.raises(ValueError):
            LineageEvent(
                event_id=str(uuid4()),
                timestamp="not a datetime",
                source_dataset="raw_users",
                destination_dataset="masked_users",
                transformation=TransformationType.MASK,
                user="admin",
                tenant_id="tenant_abc",
                metadata={},
            )

    def test_lineage_event_invalid_source_dataset(self):
        """Test validation of invalid source_dataset."""
        with pytest.raises(ValueError):
            LineageEvent(
                event_id=str(uuid4()),
                timestamp=datetime.utcnow(),
                source_dataset="",
                destination_dataset="masked_users",
                transformation=TransformationType.MASK,
                user="admin",
                tenant_id="tenant_abc",
                metadata={},
            )

    def test_lineage_event_invalid_destination_dataset(self):
        """Test validation of invalid destination_dataset."""
        with pytest.raises(ValueError):
            LineageEvent(
                event_id=str(uuid4()),
                timestamp=datetime.utcnow(),
                source_dataset="raw_users",
                destination_dataset="",
                transformation=TransformationType.MASK,
                user="admin",
                tenant_id="tenant_abc",
                metadata={},
            )

    def test_lineage_event_invalid_transformation(self):
        """Test validation of invalid transformation."""
        with pytest.raises(ValueError):
            LineageEvent(
                event_id=str(uuid4()),
                timestamp=datetime.utcnow(),
                source_dataset="raw_users",
                destination_dataset="masked_users",
                transformation="",
                user="admin",
                tenant_id="tenant_abc",
                metadata={},
            )

    def test_lineage_event_invalid_user(self):
        """Test validation of invalid user."""
        with pytest.raises(ValueError):
            LineageEvent(
                event_id=str(uuid4()),
                timestamp=datetime.utcnow(),
                source_dataset="raw_users",
                destination_dataset="masked_users",
                transformation=TransformationType.MASK,
                user="",
                tenant_id="tenant_abc",
                metadata={},
            )

    def test_lineage_event_invalid_tenant_id(self):
        """Test validation of invalid tenant_id."""
        with pytest.raises(ValueError):
            LineageEvent(
                event_id=str(uuid4()),
                timestamp=datetime.utcnow(),
                source_dataset="raw_users",
                destination_dataset="masked_users",
                transformation=TransformationType.MASK,
                user="admin",
                tenant_id="",
                metadata={},
            )

    def test_lineage_event_invalid_metadata(self):
        """Test validation of invalid metadata."""
        with pytest.raises(ValueError):
            LineageEvent(
                event_id=str(uuid4()),
                timestamp=datetime.utcnow(),
                source_dataset="raw_users",
                destination_dataset="masked_users",
                transformation=TransformationType.MASK,
                user="admin",
                tenant_id="tenant_abc",
                metadata="not a dict",
            )


class TestLineageTracker:
    """Tests for LineageTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh tracker for each test."""
        AuditLog.reset()
        return LineageTracker()

    def test_tracker_initialization(self):
        """Test tracker initialization."""
        tracker = LineageTracker()
        assert tracker.audit_log is not None
        assert tracker.event_count() == 0
        assert tracker.dataset_count() == 0

    def test_track_transformation(self, tracker):
        """Test tracking a transformation."""
        event_id = tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin@example.com",
            tenant_id="tenant_abc",
            metadata={"fields": ["email", "ssn"]},
        )

        assert event_id is not None
        assert tracker.event_count() == 1

        event = tracker.get_event(event_id)
        assert event is not None
        assert event.source_dataset == "raw_users"
        assert event.destination_dataset == "masked_users"
        assert event.transformation == TransformationType.MASK

    def test_track_transformation_minimal_metadata(self, tracker):
        """Test tracking transformation without metadata."""
        event_id = tracker.track_transformation(
            source_dataset="dataset_a",
            destination_dataset="dataset_b",
            transformation=TransformationType.COPY,
            user="user_123",
            tenant_id="tenant_xyz",
        )

        event = tracker.get_event(event_id)
        assert event.metadata == {}

    def test_track_transformation_audit_logging(self, tracker):
        """Test that transformation tracking is logged."""
        event_id = tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin@example.com",
            tenant_id="tenant_abc",
        )

        audit = AuditLog()
        events = audit.get_events_by_action("LINEAGE_TRANSFORMATION_TRACKED")
        assert len(events) == 1
        assert events[0].details["event_id"] == event_id

    def test_track_transformation_invalid_source(self, tracker):
        """Test track_transformation with invalid source_dataset."""
        with pytest.raises(TypeError):
            tracker.track_transformation(
                source_dataset="",
                destination_dataset="dataset_b",
                transformation=TransformationType.COPY,
                user="user_123",
                tenant_id="tenant_abc",
            )

    def test_track_transformation_invalid_destination(self, tracker):
        """Test track_transformation with invalid destination_dataset."""
        with pytest.raises(TypeError):
            tracker.track_transformation(
                source_dataset="dataset_a",
                destination_dataset="",
                transformation=TransformationType.COPY,
                user="user_123",
                tenant_id="tenant_abc",
            )

    def test_track_transformation_invalid_user(self, tracker):
        """Test track_transformation with invalid user."""
        with pytest.raises(TypeError):
            tracker.track_transformation(
                source_dataset="dataset_a",
                destination_dataset="dataset_b",
                transformation=TransformationType.COPY,
                user="",
                tenant_id="tenant_abc",
            )

    def test_track_transformation_invalid_tenant(self, tracker):
        """Test track_transformation with invalid tenant_id."""
        with pytest.raises(TypeError):
            tracker.track_transformation(
                source_dataset="dataset_a",
                destination_dataset="dataset_b",
                transformation=TransformationType.COPY,
                user="user_123",
                tenant_id="",
            )

    def test_get_event_found(self, tracker):
        """Test retrieving an existing event."""
        event_id = tracker.track_transformation(
            source_dataset="dataset_a",
            destination_dataset="dataset_b",
            transformation=TransformationType.COPY,
            user="user_123",
            tenant_id="tenant_abc",
        )

        event = tracker.get_event(event_id)
        assert event is not None
        assert event.event_id == event_id

    def test_get_event_not_found(self, tracker):
        """Test retrieving a non-existent event."""
        event = tracker.get_event(str(uuid4()))
        assert event is None

    def test_get_event_invalid_event_id(self, tracker):
        """Test get_event with invalid event_id type."""
        with pytest.raises(TypeError):
            tracker.get_event(123)

    def test_get_lineage_single_event(self, tracker):
        """Test getting lineage for a dataset with single event."""
        event_id = tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )

        # Query both source and destination
        source_lineage = tracker.get_lineage("raw_users")
        dest_lineage = tracker.get_lineage("masked_users")

        assert len(source_lineage) == 1
        assert len(dest_lineage) == 1
        assert source_lineage[0].event_id == event_id

    def test_get_lineage_multiple_events(self, tracker):
        """Test getting complete lineage with multiple transformations."""
        # Chain: raw -> masked -> aggregated
        event1 = tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )
        event2 = tracker.track_transformation(
            source_dataset="masked_users",
            destination_dataset="aggregated_users",
            transformation=TransformationType.AGGREGATE,
            user="admin",
            tenant_id="tenant_abc",
        )

        # masked_users should have 2 events (one as source, one as dest)
        lineage = tracker.get_lineage("masked_users")
        assert len(lineage) == 2

    def test_get_lineage_invalid_dataset(self, tracker):
        """Test get_lineage with invalid dataset type."""
        with pytest.raises(TypeError):
            tracker.get_lineage(123)

    def test_get_lineage_no_events(self, tracker):
        """Test getting lineage for dataset with no events."""
        lineage = tracker.get_lineage("nonexistent_dataset")
        assert lineage == []

    def test_get_upstream_lineage(self, tracker):
        """Test getting upstream lineage (sources only)."""
        # Chain: raw -> masked -> aggregated
        tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )
        tracker.track_transformation(
            source_dataset="masked_users",
            destination_dataset="aggregated_users",
            transformation=TransformationType.AGGREGATE,
            user="admin",
            tenant_id="tenant_abc",
        )

        # Upstream of aggregated should only show masked->aggregated
        upstream = tracker.get_upstream_lineage("aggregated_users")
        assert len(upstream) == 1
        assert upstream[0].source_dataset == "masked_users"
        assert upstream[0].destination_dataset == "aggregated_users"

    def test_get_upstream_lineage_invalid_dataset(self, tracker):
        """Test get_upstream_lineage with invalid dataset type."""
        with pytest.raises(TypeError):
            tracker.get_upstream_lineage(123)

    def test_get_downstream_lineage(self, tracker):
        """Test getting downstream lineage (consumers only)."""
        # Chain: raw -> masked -> aggregated
        tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )
        tracker.track_transformation(
            source_dataset="masked_users",
            destination_dataset="aggregated_users",
            transformation=TransformationType.AGGREGATE,
            user="admin",
            tenant_id="tenant_abc",
        )

        # Downstream of raw should only show raw->masked
        downstream = tracker.get_downstream_lineage("raw_users")
        assert len(downstream) == 1
        assert downstream[0].source_dataset == "raw_users"
        assert downstream[0].destination_dataset == "masked_users"

    def test_get_downstream_lineage_invalid_dataset(self, tracker):
        """Test get_downstream_lineage with invalid dataset type."""
        with pytest.raises(TypeError):
            tracker.get_downstream_lineage(123)

    def test_get_lineage_graph_simple(self, tracker):
        """Test getting lineage graph for visualization."""
        tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )
        tracker.track_transformation(
            source_dataset="masked_users",
            destination_dataset="aggregated_users",
            transformation=TransformationType.AGGREGATE,
            user="admin",
            tenant_id="tenant_abc",
        )

        # Get graph for masked_users
        graph = tracker.get_lineage_graph("masked_users")

        assert graph["root"] == "masked_users"
        assert "raw_users" in graph["upstream"]
        assert "aggregated_users" in graph["downstream"]
        assert len(graph["events"]) == 2

    def test_get_lineage_graph_structure(self, tracker):
        """Test lineage graph structure."""
        tracker.track_transformation(
            source_dataset="a",
            destination_dataset="b",
            transformation=TransformationType.COPY,
            user="user",
            tenant_id="tenant",
        )

        graph = tracker.get_lineage_graph("a")

        assert "root" in graph
        assert "upstream" in graph
        assert "downstream" in graph
        assert "events" in graph
        assert "graph" in graph
        assert isinstance(graph["upstream"], list)
        assert isinstance(graph["downstream"], list)
        assert isinstance(graph["graph"], dict)

    def test_get_lineage_graph_invalid_dataset(self, tracker):
        """Test get_lineage_graph with invalid dataset type."""
        with pytest.raises(TypeError):
            tracker.get_lineage_graph(123)

    def test_get_events_by_transformation(self, tracker):
        """Test filtering events by transformation type."""
        tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )
        tracker.track_transformation(
            source_dataset="dataset_a",
            destination_dataset="dataset_b",
            transformation=TransformationType.COPY,
            user="user",
            tenant_id="tenant_abc",
        )
        tracker.track_transformation(
            source_dataset="masked_users",
            destination_dataset="aggregated_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )

        mask_events = tracker.get_events_by_transformation(
            TransformationType.MASK
        )
        copy_events = tracker.get_events_by_transformation(
            TransformationType.COPY
        )

        assert len(mask_events) == 2
        assert len(copy_events) == 1

    def test_get_events_by_transformation_invalid_type(self, tracker):
        """Test get_events_by_transformation with invalid type."""
        with pytest.raises(TypeError):
            tracker.get_events_by_transformation(123)

    def test_get_events_by_tenant(self, tracker):
        """Test filtering events by tenant."""
        tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )
        tracker.track_transformation(
            source_dataset="dataset_a",
            destination_dataset="dataset_b",
            transformation=TransformationType.COPY,
            user="user",
            tenant_id="tenant_xyz",
        )

        tenant_abc = tracker.get_events_by_tenant("tenant_abc")
        tenant_xyz = tracker.get_events_by_tenant("tenant_xyz")

        assert len(tenant_abc) == 1
        assert len(tenant_xyz) == 1
        assert all(e.tenant_id == "tenant_abc" for e in tenant_abc)
        assert all(e.tenant_id == "tenant_xyz" for e in tenant_xyz)

    def test_get_events_by_tenant_invalid_type(self, tracker):
        """Test get_events_by_tenant with invalid type."""
        with pytest.raises(TypeError):
            tracker.get_events_by_tenant(123)

    def test_get_all_events(self, tracker):
        """Test retrieving all events."""
        tracker.track_transformation(
            source_dataset="a",
            destination_dataset="b",
            transformation=TransformationType.COPY,
            user="user",
            tenant_id="tenant",
        )
        tracker.track_transformation(
            source_dataset="c",
            destination_dataset="d",
            transformation=TransformationType.MASK,
            user="user",
            tenant_id="tenant",
        )

        all_events = tracker.get_all_events()
        assert len(all_events) == 2

    def test_get_all_datasets(self, tracker):
        """Test retrieving all datasets."""
        tracker.track_transformation(
            source_dataset="raw_users",
            destination_dataset="masked_users",
            transformation=TransformationType.MASK,
            user="admin",
            tenant_id="tenant_abc",
        )
        tracker.track_transformation(
            source_dataset="masked_users",
            destination_dataset="aggregated_users",
            transformation=TransformationType.AGGREGATE,
            user="admin",
            tenant_id="tenant_abc",
        )

        datasets = tracker.get_all_datasets()
        assert len(datasets) == 3
        assert "raw_users" in datasets
        assert "masked_users" in datasets
        assert "aggregated_users" in datasets

    def test_event_count(self, tracker):
        """Test event counting."""
        assert tracker.event_count() == 0

        tracker.track_transformation(
            source_dataset="a",
            destination_dataset="b",
            transformation=TransformationType.COPY,
            user="user",
            tenant_id="tenant",
        )
        assert tracker.event_count() == 1

        tracker.track_transformation(
            source_dataset="c",
            destination_dataset="d",
            transformation=TransformationType.MASK,
            user="user",
            tenant_id="tenant",
        )
        assert tracker.event_count() == 2

    def test_dataset_count(self, tracker):
        """Test dataset counting."""
        assert tracker.dataset_count() == 0

        tracker.track_transformation(
            source_dataset="a",
            destination_dataset="b",
            transformation=TransformationType.COPY,
            user="user",
            tenant_id="tenant",
        )
        assert tracker.dataset_count() == 2

        tracker.track_transformation(
            source_dataset="b",
            destination_dataset="c",
            transformation=TransformationType.MASK,
            user="user",
            tenant_id="tenant",
        )
        assert tracker.dataset_count() == 3

    def test_clear_events(self, tracker):
        """Test clearing all events."""
        tracker.track_transformation(
            source_dataset="a",
            destination_dataset="b",
            transformation=TransformationType.COPY,
            user="user",
            tenant_id="tenant",
        )
        assert tracker.event_count() == 1

        cleared = tracker.clear()
        assert cleared == 1
        assert tracker.event_count() == 0
        assert tracker.dataset_count() == 0


class TestLineageScenarios:
    """Integration tests for data flow scenarios."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh tracker for each test."""
        AuditLog.reset()
        return LineageTracker()

    def test_data_masking_pipeline(self, tracker):
        """Test complete data masking pipeline lineage."""
        # Raw data -> masked -> aggregated -> exported
        event1 = tracker.track_transformation(
            source_dataset="db.users.raw",
            destination_dataset="db.users.masked",
            transformation=TransformationType.MASK,
            user="etl_admin",
            tenant_id="tenant_prod",
            metadata={"fields": ["email", "phone", "ssn"]},
        )
        event2 = tracker.track_transformation(
            source_dataset="db.users.masked",
            destination_dataset="warehouse.users_daily",
            transformation=TransformationType.AGGREGATE,
            user="etl_admin",
            tenant_id="tenant_prod",
            metadata={"groupby": ["country", "segment"]},
        )
        event3 = tracker.track_transformation(
            source_dataset="warehouse.users_daily",
            destination_dataset="reports.export_users",
            transformation=TransformationType.COPY,
            user="analyst",
            tenant_id="tenant_prod",
        )

        # Trace complete lineage
        complete = tracker.get_lineage("db.users.masked")
        assert len(complete) == 2

        # Check upstream sources
        upstream = tracker.get_upstream_lineage("warehouse.users_daily")
        assert upstream[0].source_dataset == "db.users.masked"

        # Check downstream consumers
        downstream = tracker.get_downstream_lineage("db.users.masked")
        assert downstream[0].destination_dataset == "warehouse.users_daily"

    def test_multi_source_join(self, tracker):
        """Test data lineage for multi-source join."""
        # Two sources joining into one destination
        tracker.track_transformation(
            source_dataset="users_table",
            destination_dataset="user_order_join",
            transformation=TransformationType.JOIN,
            user="analyst",
            tenant_id="tenant_abc",
            metadata={"join_key": "user_id"},
        )
        tracker.track_transformation(
            source_dataset="orders_table",
            destination_dataset="user_order_join",
            transformation=TransformationType.JOIN,
            user="analyst",
            tenant_id="tenant_abc",
            metadata={"join_key": "user_id"},
        )

        # Both sources should appear in lineage
        lineage = tracker.get_lineage("user_order_join")
        assert len(lineage) == 2

        upstream = tracker.get_upstream_lineage("user_order_join")
        assert len(upstream) == 2

    def test_multi_tenant_isolation(self, tracker):
        """Test that lineage is properly isolated by tenant."""
        tracker.track_transformation(
            source_dataset="raw_a",
            destination_dataset="masked_a",
            transformation=TransformationType.MASK,
            user="admin_a",
            tenant_id="tenant_a",
        )
        tracker.track_transformation(
            source_dataset="raw_b",
            destination_dataset="masked_b",
            transformation=TransformationType.MASK,
            user="admin_b",
            tenant_id="tenant_b",
        )

        tenant_a_events = tracker.get_events_by_tenant("tenant_a")
        tenant_b_events = tracker.get_events_by_tenant("tenant_b")

        assert len(tenant_a_events) == 1
        assert len(tenant_b_events) == 1
        assert all(e.tenant_id == "tenant_a" for e in tenant_a_events)
        assert all(e.tenant_id == "tenant_b" for e in tenant_b_events)

    def test_lineage_audit_trail(self, tracker):
        """Test that all lineage operations are audited."""
        tracker.track_transformation(
            source_dataset="raw_data",
            destination_dataset="processed_data",
            transformation=TransformationType.FILTER,
            user="analyst",
            tenant_id="tenant_abc",
        )

        audit = AuditLog()
        events = audit.get_events_by_action("LINEAGE_TRANSFORMATION_TRACKED")
        assert len(events) == 1
        assert events[0].status == "SUCCESS"

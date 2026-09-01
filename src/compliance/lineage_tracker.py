"""Data provenance tracking and lineage management.

This module provides comprehensive data lineage tracking for compliance and
operational visibility. Tracks data flow from source through transformations
to destination, including temporal provenance information and metadata.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from src.compliance.audit_log import AuditLog

logger = logging.getLogger(__name__)


class TransformationType:
    """Constants for transformation types."""

    MASK = "MASK"
    TOKENIZE = "TOKENIZE"
    HASH = "HASH"
    REDACT = "REDACT"
    COPY = "COPY"
    AGGREGATE = "AGGREGATE"
    JOIN = "JOIN"
    FILTER = "FILTER"
    ENRICH = "ENRICH"


@dataclass(frozen=True)
class LineageEvent:
    """Immutable representation of a data transformation event.

    Records a single transformation from source dataset to destination dataset,
    capturing the transformation type, who performed it, and detailed metadata.

    Attributes:
        event_id: Unique event identifier (UUID format).
        timestamp: UTC timestamp when transformation occurred.
        source_dataset: Name or identifier of source dataset.
        destination_dataset: Name or identifier of destination dataset.
        transformation: Type of transformation applied.
        user: User who initiated the transformation.
        tenant_id: Multi-tenant context identifier.
        metadata: Additional metadata (field mappings, record counts, etc.).

    Raises:
        ValueError: If validation fails during initialization.
    """

    event_id: str
    timestamp: datetime
    source_dataset: str
    destination_dataset: str
    transformation: str
    user: str
    tenant_id: str
    metadata: Dict[str, Any]

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate event invariants.

        Raises:
            ValueError: If any field contains invalid data.
        """
        if not self.event_id or not isinstance(self.event_id, str):
            raise ValueError(
                f"event_id must be non-empty string, got {self.event_id!r}"
            )

        if not isinstance(self.timestamp, datetime):
            raise ValueError(
                f"timestamp must be datetime, "
                f"got {type(self.timestamp).__name__}"
            )

        if not self.source_dataset or not isinstance(
            self.source_dataset, str
        ):
            raise ValueError(
                f"source_dataset must be non-empty string, "
                f"got {self.source_dataset!r}"
            )

        if not self.destination_dataset or not isinstance(
            self.destination_dataset, str
        ):
            raise ValueError(
                f"destination_dataset must be non-empty string, "
                f"got {self.destination_dataset!r}"
            )

        if not self.transformation or not isinstance(
            self.transformation, str
        ):
            raise ValueError(
                f"transformation must be non-empty string, "
                f"got {self.transformation!r}"
            )

        if not self.user or not isinstance(self.user, str):
            raise ValueError(
                f"user must be non-empty string, got {self.user!r}"
            )

        if not self.tenant_id or not isinstance(self.tenant_id, str):
            raise ValueError(
                f"tenant_id must be non-empty string, "
                f"got {self.tenant_id!r}"
            )

        if not isinstance(self.metadata, dict):
            raise ValueError(
                f"metadata must be dict, "
                f"got {type(self.metadata).__name__}"
            )

        logger.debug(f"LineageEvent validated: {self.event_id}")


class LineageTracker:
    """Data lineage tracking and provenance system.

    Maintains a directed graph of data transformations with temporal metadata.
    Enables tracking data flow from sources through transformations to sinks,
    supporting bidirectional queries (upstream sources, downstream consumers).

    Attributes:
        audit_log: AuditLog singleton for event logging.
        _events: Storage for lineage events (keyed by event_id).
        _dataset_index: Index for fast dataset lookup (dataset_name -> event_ids).

    Example:
        >>> tracker = LineageTracker()
        >>> event_id = tracker.track_transformation(
        ...     source_dataset="raw_users",
        ...     destination_dataset="masked_users",
        ...     transformation="MASK",
        ...     user="admin@example.com",
        ...     tenant_id="tenant_abc",
        ...     metadata={"fields": ["email", "ssn"], "strategy": "hash"}
        ... )
        >>> lineage = tracker.get_lineage("masked_users")
    """

    def __init__(self) -> None:
        """Initialize lineage tracker."""
        self.audit_log = AuditLog()
        self._events: Dict[str, LineageEvent] = {}
        self._dataset_index: Dict[str, List[str]] = {}
        logger.info("LineageTracker initialized")

    def track_transformation(
        self,
        source_dataset: str,
        destination_dataset: str,
        transformation: str,
        user: str,
        tenant_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Track a data transformation event.

        Records a transformation from source to destination dataset with
        full provenance information and metadata.

        Args:
            source_dataset: Name/ID of source dataset.
            destination_dataset: Name/ID of destination dataset.
            transformation: Type of transformation (one of TransformationType).
            user: User who initiated the transformation.
            tenant_id: Multi-tenant context.
            metadata: Optional metadata about the transformation.

        Returns:
            The event_id of the tracked transformation.

        Raises:
            TypeError: If any argument has wrong type.
            ValueError: If any argument fails validation.

        Example:
            >>> tracker = LineageTracker()
            >>> event_id = tracker.track_transformation(
            ...     source_dataset="raw_users",
            ...     destination_dataset="masked_users",
            ...     transformation="MASK",
            ...     user="admin@example.com",
            ...     tenant_id="tenant_abc"
            ... )
        """
        # Type validation
        if not isinstance(source_dataset, str) or not source_dataset:
            raise TypeError("source_dataset must be non-empty string")
        if (
            not isinstance(destination_dataset, str)
            or not destination_dataset
        ):
            raise TypeError("destination_dataset must be non-empty string")
        if not isinstance(transformation, str) or not transformation:
            raise TypeError("transformation must be non-empty string")
        if not isinstance(user, str) or not user:
            raise TypeError("user must be non-empty string")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise TypeError("tenant_id must be non-empty string")
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("metadata must be dict or None")

        metadata = metadata or {}

        # Create event
        event_id = str(uuid4())
        timestamp = datetime.utcnow()

        event = LineageEvent(
            event_id=event_id,
            timestamp=timestamp,
            source_dataset=source_dataset,
            destination_dataset=destination_dataset,
            transformation=transformation,
            user=user,
            tenant_id=tenant_id,
            metadata=metadata,
        )

        # Store event
        self._events[event_id] = event

        # Update dataset index
        if source_dataset not in self._dataset_index:
            self._dataset_index[source_dataset] = []
        if destination_dataset not in self._dataset_index:
            self._dataset_index[destination_dataset] = []

        self._dataset_index[source_dataset].append(event_id)
        self._dataset_index[destination_dataset].append(event_id)

        # Log transformation
        self.audit_log.log_event(
            action="LINEAGE_TRANSFORMATION_TRACKED",
            user=user,
            tenant_id=tenant_id,
            details={
                "event_id": event_id,
                "source_dataset": source_dataset,
                "destination_dataset": destination_dataset,
                "transformation": transformation,
            },
            status="SUCCESS",
        )

        logger.info(
            f"Lineage transformation tracked: {event_id} "
            f"({source_dataset} -> {destination_dataset}, "
            f"type={transformation})"
        )

        return event_id

    def get_event(self, event_id: str) -> Optional[LineageEvent]:
        """Retrieve a lineage event by ID.

        Args:
            event_id: The event ID to look up.

        Returns:
            The LineageEvent if found, None otherwise.

        Raises:
            TypeError: If event_id is not a string.

        Example:
            >>> tracker = LineageTracker()
            >>> event = tracker.get_event(event_id)
        """
        if not isinstance(event_id, str):
            raise TypeError("event_id must be string")

        return self._events.get(event_id)

    def get_lineage(self, dataset: str) -> List[LineageEvent]:
        """Get complete lineage for a dataset (upstream + downstream).

        Returns all events where this dataset is either source or destination,
        enabling full provenance tracking from original sources to final sinks.

        Args:
            dataset: Dataset name/ID to trace.

        Returns:
            List of LineageEvent objects involving this dataset.

        Raises:
            TypeError: If dataset is not a string.

        Example:
            >>> tracker = LineageTracker()
            >>> lineage = tracker.get_lineage("masked_users")
            >>> for event in lineage:
            ...     print(f"{event.source_dataset} -> {event.destination_dataset}")
        """
        if not isinstance(dataset, str):
            raise TypeError("dataset must be string")

        event_ids = self._dataset_index.get(dataset, [])
        return [self._events[eid] for eid in event_ids]

    def get_upstream_lineage(self, dataset: str) -> List[LineageEvent]:
        """Get upstream lineage (sources only) for a dataset.

        Traces all transformations backwards from destination to sources.

        Args:
            dataset: Dataset name/ID to trace.

        Returns:
            List of LineageEvent objects with this dataset as destination.

        Raises:
            TypeError: If dataset is not a string.

        Example:
            >>> tracker = LineageTracker()
            >>> upstream = tracker.get_upstream_lineage("masked_users")
        """
        if not isinstance(dataset, str):
            raise TypeError("dataset must be string")

        event_ids = self._dataset_index.get(dataset, [])
        return [
            self._events[eid]
            for eid in event_ids
            if self._events[eid].destination_dataset == dataset
        ]

    def get_downstream_lineage(self, dataset: str) -> List[LineageEvent]:
        """Get downstream lineage (consumers only) for a dataset.

        Traces all transformations forwards from source to destinations.

        Args:
            dataset: Dataset name/ID to trace.

        Returns:
            List of LineageEvent objects with this dataset as source.

        Raises:
            TypeError: If dataset is not a string.

        Example:
            >>> tracker = LineageTracker()
            >>> downstream = tracker.get_downstream_lineage("raw_users")
        """
        if not isinstance(dataset, str):
            raise TypeError("dataset must be string")

        event_ids = self._dataset_index.get(dataset, [])
        return [
            self._events[eid]
            for eid in event_ids
            if self._events[eid].source_dataset == dataset
        ]

    def get_lineage_graph(self, dataset: str) -> Dict[str, Any]:
        """Get lineage graph for a dataset (for visualization).

        Returns a structured representation of the lineage DAG including
        all upstream sources and downstream consumers.

        Args:
            dataset: Dataset name/ID to trace.

        Returns:
            Dictionary with keys:
            - 'root': The query dataset
            - 'upstream': List of upstream source datasets
            - 'downstream': List of downstream consumer datasets
            - 'events': List of all lineage events
            - 'graph': Dict mapping dataset -> connected datasets

        Raises:
            TypeError: If dataset is not a string.

        Example:
            >>> tracker = LineageTracker()
            >>> graph = tracker.get_lineage_graph("masked_users")
            >>> print(graph['upstream'])  # Source datasets
            >>> print(graph['downstream'])  # Consumer datasets
        """
        if not isinstance(dataset, str):
            raise TypeError("dataset must be string")

        # Get all events for this dataset
        lineage_events = self.get_lineage(dataset)

        # Build upstream and downstream sets
        upstream: Set[str] = set()
        downstream: Set[str] = set()
        graph: Dict[str, List[str]] = {}

        for event in lineage_events:
            if event.destination_dataset == dataset:
                upstream.add(event.source_dataset)
            else:
                downstream.add(event.destination_dataset)

            # Build graph connections
            if event.source_dataset not in graph:
                graph[event.source_dataset] = []
            if event.destination_dataset not in graph[event.source_dataset]:
                graph[event.source_dataset].append(event.destination_dataset)

        return {
            "root": dataset,
            "upstream": sorted(list(upstream)),
            "downstream": sorted(list(downstream)),
            "events": lineage_events,
            "graph": graph,
        }

    def get_events_by_transformation(
        self, transformation: str
    ) -> List[LineageEvent]:
        """Get all events of a specific transformation type.

        Args:
            transformation: Transformation type to filter by.

        Returns:
            List of LineageEvent objects with matching transformation.

        Raises:
            TypeError: If transformation is not a string.

        Example:
            >>> tracker = LineageTracker()
            >>> mask_events = tracker.get_events_by_transformation("MASK")
            >>> for event in mask_events:
            ...     print(f"{event.source_dataset} masked")
        """
        if not isinstance(transformation, str):
            raise TypeError("transformation must be string")

        return [
            e
            for e in self._events.values()
            if e.transformation == transformation
        ]

    def get_events_by_tenant(self, tenant_id: str) -> List[LineageEvent]:
        """Get all lineage events for a tenant.

        Args:
            tenant_id: Tenant identifier to filter by.

        Returns:
            List of LineageEvent objects for the tenant.

        Raises:
            TypeError: If tenant_id is not a string.

        Example:
            >>> tracker = LineageTracker()
            >>> tenant_events = tracker.get_events_by_tenant("tenant_abc")
        """
        if not isinstance(tenant_id, str):
            raise TypeError("tenant_id must be string")

        return [e for e in self._events.values() if e.tenant_id == tenant_id]

    def get_all_events(self) -> List[LineageEvent]:
        """Retrieve all lineage events.

        Returns:
            List of all LineageEvent objects.

        Example:
            >>> tracker = LineageTracker()
            >>> all_events = tracker.get_all_events()
        """
        return list(self._events.values())

    def get_all_datasets(self) -> List[str]:
        """Get all datasets referenced in lineage.

        Returns:
            List of dataset names/IDs.

        Example:
            >>> tracker = LineageTracker()
            >>> datasets = tracker.get_all_datasets()
        """
        return list(self._dataset_index.keys())

    def event_count(self) -> int:
        """Get the total number of lineage events.

        Returns:
            Count of all tracked transformations.

        Example:
            >>> tracker = LineageTracker()
            >>> count = tracker.event_count()
        """
        return len(self._events)

    def dataset_count(self) -> int:
        """Get the total number of datasets in lineage.

        Returns:
            Count of all unique datasets.

        Example:
            >>> tracker = LineageTracker()
            >>> count = tracker.dataset_count()
        """
        return len(self._dataset_index)

    def clear(self) -> int:
        """Clear all events (testing only).

        Removes all lineage events from tracking.

        Returns:
            Number of events that were cleared.

        Example:
            >>> tracker = LineageTracker()
            >>> cleared = tracker.clear()
        """
        count = len(self._events)
        self._events.clear()
        self._dataset_index.clear()
        logger.warning(
            f"LineageTracker cleared: {count} events removed "
            "(testing only - production use is discouraged)"
        )
        return count

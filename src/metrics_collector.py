"""System health metrics collection and reporting.

This module provides comprehensive metrics collection for monitoring system
health, performance, and compliance. Tracks throughput, latency, error rates,
and derives insights from audit logs.
"""

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .audit_log import AuditLog

logger = logging.getLogger(__name__)


class MetricName:
    """Constants for standard metric names."""

    MASK_OPERATIONS_TOTAL = "mask_operations_total"
    MASK_OPERATIONS_SUCCESS = "mask_operations_success"
    MASK_OPERATIONS_FAILED = "mask_operations_failed"
    MASK_LATENCY_MS = "mask_latency_ms"

    VAULT_OPERATIONS_TOTAL = "vault_operations_total"
    VAULT_LATENCY_MS = "vault_latency_ms"

    ERASURE_REQUESTS_TOTAL = "erasure_requests_total"
    ERASURE_REQUESTS_COMPLETED = "erasure_requests_completed"
    ERASURE_REQUESTS_FAILED = "erasure_requests_failed"

    LINEAGE_EVENTS_TOTAL = "lineage_events_total"
    LINEAGE_LATENCY_MS = "lineage_latency_ms"

    AUDIT_EVENTS_TOTAL = "audit_events_total"
    ERROR_RATE_PERCENT = "error_rate_percent"


@dataclass(frozen=True)
class Metric:
    """Immutable metric data point.

    Represents a single metric measurement with timestamp and labels for
    dimensional analysis.

    Attributes:
        metric_id: Unique metric identifier (UUID format).
        name: Metric name (e.g., "mask_operations_total").
        value: Numeric metric value.
        timestamp: UTC timestamp when metric was recorded.
        labels: Dimensional labels (tenant_id, operation_type, status).

    Raises:
        ValueError: If validation fails during initialization.
    """

    metric_id: str
    name: str
    value: float
    timestamp: datetime
    labels: Dict[str, str]

    def __post_init__(self) -> None:
        """Validate metric after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate metric invariants.

        Raises:
            ValueError: If any field contains invalid data.
        """
        if not self.metric_id or not isinstance(self.metric_id, str):
            raise ValueError(
                f"metric_id must be non-empty string, got {self.metric_id!r}"
            )

        if not self.name or not isinstance(self.name, str):
            raise ValueError(
                f"name must be non-empty string, got {self.name!r}"
            )

        if not isinstance(self.value, (int, float)):
            raise ValueError(
                f"value must be numeric, got {type(self.value).__name__}"
            )

        if not isinstance(self.timestamp, datetime):
            raise ValueError(
                f"timestamp must be datetime, "
                f"got {type(self.timestamp).__name__}"
            )

        if not isinstance(self.labels, dict):
            raise ValueError(
                f"labels must be dict, got {type(self.labels).__name__}"
            )

        logger.debug(f"Metric validated: {self.metric_id} ({self.name})")


class MetricsCollector:
    """System health metrics collection and analysis.

    Collects and aggregates metrics from system operations. Supports
    dimensional queries, statistical aggregations, and time-windowed
    analysis for monitoring and alerting.

    Attributes:
        audit_log: AuditLog singleton for event analysis.
        _metrics: Storage for metrics (keyed by metric_id).
        _name_index: Index for fast metric lookup by name.

    Example:
        >>> collector = MetricsCollector()
        >>> collector.record_metric(
        ...     name="mask_operations_total",
        ...     value=1.0,
        ...     labels={"tenant_id": "tenant_abc", "status": "success"}
        ... )
        >>> metrics = collector.get_metrics_by_name("mask_operations_total")
        >>> stats = collector.summary_statistics()
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self.audit_log = AuditLog()
        self._metrics: Dict[str, Metric] = {}
        self._name_index: Dict[str, List[str]] = {}
        logger.info("MetricsCollector initialized")

    def record_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a single metric data point.

        Args:
            name: Metric name (should be from MetricName constants).
            value: Numeric value of the metric.
            labels: Optional dimensional labels for the metric.

        Raises:
            TypeError: If any argument has wrong type.
            ValueError: If any argument fails validation.

        Example:
            >>> collector = MetricsCollector()
            >>> collector.record_metric(
            ...     name="mask_operations_total",
            ...     value=5.0,
            ...     labels={"tenant_id": "tenant_123", "status": "success"}
            ... )
        """
        # Type validation
        if not isinstance(name, str) or not name:
            raise TypeError("name must be non-empty string")
        if not isinstance(value, (int, float)):
            raise TypeError("value must be numeric")
        if labels is not None and not isinstance(labels, dict):
            raise TypeError("labels must be dict or None")

        labels = labels or {}

        # Create metric
        metric_id = str(uuid4())
        timestamp = datetime.utcnow()

        metric = Metric(
            metric_id=metric_id,
            name=name,
            value=float(value),
            timestamp=timestamp,
            labels=labels,
        )

        # Store metric
        self._metrics[metric_id] = metric

        # Update name index
        if name not in self._name_index:
            self._name_index[name] = []
        self._name_index[name].append(metric_id)

        logger.debug(
            f"Metric recorded: {name}={value} "
            f"(labels={labels})"
        )

    def get_metrics(self) -> List[Metric]:
        """Retrieve all recorded metrics.

        Returns:
            List of all Metric objects in chronological order.

        Example:
            >>> collector = MetricsCollector()
            >>> all_metrics = collector.get_metrics()
        """
        return sorted(
            self._metrics.values(), key=lambda m: m.timestamp
        )

    def get_metrics_by_name(self, name: str) -> List[Metric]:
        """Retrieve metrics by name.

        Args:
            name: Metric name to filter by.

        Returns:
            List of metrics with matching name in chronological order.

        Raises:
            TypeError: If name is not a string.

        Example:
            >>> collector = MetricsCollector()
            >>> mask_metrics = collector.get_metrics_by_name(
            ...     "mask_operations_total"
            ... )
        """
        if not isinstance(name, str):
            raise TypeError("name must be string")

        metric_ids = self._name_index.get(name, [])
        return sorted(
            [self._metrics[mid] for mid in metric_ids],
            key=lambda m: m.timestamp,
        )

    def get_metrics_by_label(
        self, label_key: str, label_value: str
    ) -> List[Metric]:
        """Retrieve metrics by label key-value pair.

        Args:
            label_key: Label key to filter by.
            label_value: Label value to match.

        Returns:
            List of metrics with matching label in chronological order.

        Raises:
            TypeError: If label_key or label_value is not a string.

        Example:
            >>> collector = MetricsCollector()
            >>> tenant_metrics = collector.get_metrics_by_label(
            ...     "tenant_id", "tenant_abc"
            ... )
        """
        if not isinstance(label_key, str):
            raise TypeError("label_key must be string")
        if not isinstance(label_value, str):
            raise TypeError("label_value must be string")

        matching = [
            m
            for m in self._metrics.values()
            if m.labels.get(label_key) == label_value
        ]
        return sorted(matching, key=lambda m: m.timestamp)

    def get_metrics_by_time_window(
        self, name: str, hours: int
    ) -> List[Metric]:
        """Retrieve metrics within a time window.

        Args:
            name: Metric name to filter by.
            hours: Number of hours in the past to include.

        Returns:
            List of metrics matching name within time window.

        Raises:
            TypeError: If name is not a string or hours is not int.
            ValueError: If hours is negative.

        Example:
            >>> collector = MetricsCollector()
            >>> recent = collector.get_metrics_by_time_window(
            ...     "mask_operations_total", hours=1
            ... )
        """
        if not isinstance(name, str):
            raise TypeError("name must be string")
        if not isinstance(hours, int):
            raise TypeError("hours must be int")
        if hours < 0:
            raise ValueError("hours must be non-negative")

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        metrics = self.get_metrics_by_name(name)
        return [m for m in metrics if m.timestamp >= cutoff_time]

    def summary_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Calculate summary statistics for all metrics.

        Returns statistics including count, mean, median (p50), and p99
        percentile for each metric name.

        Returns:
            Dictionary mapping metric name to statistics dict with keys:
            - 'count': Number of data points
            - 'mean': Average value
            - 'min': Minimum value
            - 'max': Maximum value
            - 'p50': Median (50th percentile)
            - 'p99': 99th percentile
            - 'stdev': Standard deviation (if count >= 2)

        Example:
            >>> collector = MetricsCollector()
            >>> collector.record_metric("latency_ms", 100.0)
            >>> collector.record_metric("latency_ms", 150.0)
            >>> stats = collector.summary_statistics()
            >>> print(stats["latency_ms"]["mean"])
        """
        stats: Dict[str, Dict[str, Any]] = {}

        for name in self._name_index.keys():
            metrics = self.get_metrics_by_name(name)
            if not metrics:
                continue

            values = [m.value for m in metrics]
            count = len(values)
            mean = statistics.mean(values)
            min_val = min(values)
            max_val = max(values)

            # Calculate percentiles
            sorted_values = sorted(values)
            p50_idx = int(count * 0.50)
            p99_idx = int(count * 0.99)
            # Ensure indices are valid
            p50_idx = min(max(p50_idx, 0), count - 1)
            p99_idx = min(max(p99_idx, 0), count - 1)

            p50 = sorted_values[p50_idx]
            p99 = sorted_values[p99_idx]

            stat_dict: Dict[str, Any] = {
                "count": count,
                "mean": round(mean, 2),
                "min": min_val,
                "max": max_val,
                "p50": p50,
                "p99": p99,
            }

            # Calculate standard deviation if we have enough data points
            if count >= 2:
                stdev = statistics.stdev(values)
                stat_dict["stdev"] = round(stdev, 2)

            stats[name] = stat_dict

        logger.debug(f"Calculated statistics for {len(stats)} metrics")
        return stats

    def derive_throughput(
        self, metric_name: str, hours: int = 1
    ) -> float:
        """Calculate throughput (operations per second).

        Args:
            metric_name: Metric name to calculate throughput for.
            hours: Time window in hours.

        Returns:
            Throughput in operations per second.

        Raises:
            TypeError: If metric_name is not a string or hours is not int.
            ValueError: If hours is negative or no data available.

        Example:
            >>> collector = MetricsCollector()
            >>> for i in range(10):
            ...     collector.record_metric("ops", 1.0)
            >>> throughput = collector.derive_throughput("ops", hours=1)
        """
        if not isinstance(metric_name, str):
            raise TypeError("metric_name must be string")
        if not isinstance(hours, int):
            raise TypeError("hours must be int")
        if hours <= 0:
            raise ValueError("hours must be positive")

        metrics = self.get_metrics_by_time_window(metric_name, hours)
        if not metrics:
            raise ValueError(f"No metrics found for {metric_name}")

        total_count = sum(m.value for m in metrics)
        seconds = hours * 3600
        throughput = total_count / seconds

        logger.debug(
            f"Throughput for {metric_name}: {throughput:.2f} ops/sec"
        )
        return round(throughput, 2)

    def derive_error_rate(self, hours: int = 1) -> float:
        """Calculate error rate from audit log events.

        Queries audit log for FAILURE events and calculates error rate
        as percentage of total events.

        Args:
            hours: Time window in hours.

        Returns:
            Error rate as percentage (0-100).

        Raises:
            ValueError: If hours is negative or no events found.

        Example:
            >>> collector = MetricsCollector()
            >>> error_rate = collector.derive_error_rate(hours=1)
        """
        if not isinstance(hours, int):
            raise TypeError("hours must be int")
        if hours <= 0:
            raise ValueError("hours must be positive")

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        all_events = self.audit_log.get_events_by_timestamp(
            cutoff_time, datetime.utcnow()
        )

        if not all_events:
            raise ValueError("No audit events found in time window")

        failure_count = sum(1 for e in all_events if e.status == "FAILURE")
        total_count = len(all_events)

        error_rate = (failure_count / total_count) * 100 if total_count > 0 else 0

        logger.debug(f"Error rate: {error_rate:.2f}%")
        return round(error_rate, 2)

    def derive_latency_percentile(
        self, metric_name: str, percentile: float, hours: int = 1
    ) -> float:
        """Calculate latency percentile.

        Args:
            metric_name: Latency metric name to analyze.
            percentile: Percentile to calculate (0-100).
            hours: Time window in hours.

        Returns:
            Latency value at specified percentile.

        Raises:
            TypeError: If types are wrong.
            ValueError: If values are out of range or no data found.

        Example:
            >>> collector = MetricsCollector()
            >>> p99_latency = collector.derive_latency_percentile(
            ...     "mask_latency_ms", percentile=99, hours=1
            ... )
        """
        if not isinstance(metric_name, str):
            raise TypeError("metric_name must be string")
        if not isinstance(percentile, (int, float)):
            raise TypeError("percentile must be numeric")
        if not 0 <= percentile <= 100:
            raise ValueError("percentile must be between 0 and 100")
        if not isinstance(hours, int):
            raise TypeError("hours must be int")
        if hours <= 0:
            raise ValueError("hours must be positive")

        metrics = self.get_metrics_by_time_window(metric_name, hours)
        if not metrics:
            raise ValueError(f"No metrics found for {metric_name}")

        values = sorted([m.value for m in metrics])
        idx = int(len(values) * (percentile / 100))
        # Ensure index is valid
        idx = min(max(idx, 0), len(values) - 1)

        result = values[idx]
        logger.debug(
            f"P{percentile} latency for {metric_name}: {result:.2f}ms"
        )
        return round(result, 2)

    def metric_count(self) -> int:
        """Get the total number of recorded metrics.

        Returns:
            Count of all metrics.

        Example:
            >>> collector = MetricsCollector()
            >>> count = collector.metric_count()
        """
        return len(self._metrics)

    def clear(self) -> int:
        """Clear all metrics (testing only).

        Removes all recorded metrics from the collector.

        Returns:
            Number of metrics that were cleared.

        Example:
            >>> collector = MetricsCollector()
            >>> cleared = collector.clear()
        """
        count = len(self._metrics)
        self._metrics.clear()
        self._name_index.clear()
        logger.warning(
            f"MetricsCollector cleared: {count} metrics removed "
            "(testing only - production use is discouraged)"
        )
        return count

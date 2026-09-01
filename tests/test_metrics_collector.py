"""Tests for the metrics_collector module (system health monitoring).

Coverage targets:
- Metric dataclass validation
- MetricsCollector recording and retrieval
- Statistical aggregations (mean, percentiles, stdev)
- Time-windowed analysis
- Derived metrics (throughput, error rate, latency percentiles)
- Audit log integration
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from src.metrics_collector import (
    Metric,
    MetricsCollector,
    MetricName,
)
from src.audit_log import AuditLog


class TestMetric:
    """Tests for Metric dataclass."""

    def test_valid_metric(self):
        """Test creating a valid metric."""
        metric_id = str(uuid4())
        timestamp = datetime.utcnow()

        metric = Metric(
            metric_id=metric_id,
            name="mask_operations_total",
            value=42.0,
            timestamp=timestamp,
            labels={"tenant_id": "tenant_abc", "status": "success"},
        )

        assert metric.metric_id == metric_id
        assert metric.name == "mask_operations_total"
        assert metric.value == 42.0
        assert metric.labels["tenant_id"] == "tenant_abc"

    def test_metric_with_int_value(self):
        """Test metric with integer value."""
        metric = Metric(
            metric_id=str(uuid4()),
            name="count",
            value=100,
            timestamp=datetime.utcnow(),
            labels={},
        )

        assert metric.value == 100
        assert isinstance(metric.value, (int, float))

    def test_metric_with_empty_labels(self):
        """Test metric with empty labels."""
        metric = Metric(
            metric_id=str(uuid4()),
            name="latency_ms",
            value=150.5,
            timestamp=datetime.utcnow(),
            labels={},
        )

        assert metric.labels == {}

    def test_metric_immutable(self):
        """Test that metric is frozen (immutable)."""
        metric = Metric(
            metric_id=str(uuid4()),
            name="test_metric",
            value=10.0,
            timestamp=datetime.utcnow(),
            labels={},
        )

        with pytest.raises(AttributeError):
            metric.value = 20.0

    def test_metric_invalid_metric_id(self):
        """Test validation of invalid metric_id."""
        with pytest.raises(ValueError):
            Metric(
                metric_id="",
                name="test",
                value=10.0,
                timestamp=datetime.utcnow(),
                labels={},
            )

    def test_metric_invalid_name(self):
        """Test validation of invalid name."""
        with pytest.raises(ValueError):
            Metric(
                metric_id=str(uuid4()),
                name="",
                value=10.0,
                timestamp=datetime.utcnow(),
                labels={},
            )

    def test_metric_invalid_value_type(self):
        """Test validation of invalid value type."""
        with pytest.raises(ValueError):
            Metric(
                metric_id=str(uuid4()),
                name="test",
                value="not_a_number",
                timestamp=datetime.utcnow(),
                labels={},
            )

    def test_metric_invalid_timestamp(self):
        """Test validation of invalid timestamp."""
        with pytest.raises(ValueError):
            Metric(
                metric_id=str(uuid4()),
                name="test",
                value=10.0,
                timestamp="not a datetime",
                labels={},
            )

    def test_metric_invalid_labels(self):
        """Test validation of invalid labels."""
        with pytest.raises(ValueError):
            Metric(
                metric_id=str(uuid4()),
                name="test",
                value=10.0,
                timestamp=datetime.utcnow(),
                labels="not a dict",
            )


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    @pytest.fixture
    def collector(self):
        """Create a fresh collector for each test."""
        AuditLog.reset()
        return MetricsCollector()

    def test_collector_initialization(self):
        """Test collector initialization."""
        collector = MetricsCollector()
        assert collector.audit_log is not None
        assert collector.metric_count() == 0

    def test_record_metric_with_labels(self, collector):
        """Test recording a metric with labels."""
        collector.record_metric(
            name="mask_operations_total",
            value=5.0,
            labels={"tenant_id": "tenant_abc", "status": "success"},
        )

        assert collector.metric_count() == 1

        metrics = collector.get_metrics()
        assert len(metrics) == 1
        assert metrics[0].name == "mask_operations_total"
        assert metrics[0].value == 5.0
        assert metrics[0].labels["tenant_id"] == "tenant_abc"

    def test_record_metric_without_labels(self, collector):
        """Test recording a metric without labels."""
        collector.record_metric(
            name="audit_events_total",
            value=100.0,
        )

        metrics = collector.get_metrics()
        assert len(metrics) == 1
        assert metrics[0].labels == {}

    def test_record_metric_int_value(self, collector):
        """Test recording metric with integer value."""
        collector.record_metric(
            name="event_count",
            value=42,
        )

        metrics = collector.get_metrics()
        assert metrics[0].value == 42.0

    def test_record_metric_invalid_name(self, collector):
        """Test record_metric with invalid name."""
        with pytest.raises(TypeError):
            collector.record_metric(
                name="",
                value=10.0,
            )

    def test_record_metric_invalid_value(self, collector):
        """Test record_metric with invalid value."""
        with pytest.raises(TypeError):
            collector.record_metric(
                name="test",
                value="not_a_number",
            )

    def test_record_metric_invalid_labels(self, collector):
        """Test record_metric with invalid labels."""
        with pytest.raises(TypeError):
            collector.record_metric(
                name="test",
                value=10.0,
                labels="not a dict",
            )

    def test_get_metrics(self, collector):
        """Test retrieving all metrics."""
        collector.record_metric("metric1", 10.0)
        collector.record_metric("metric2", 20.0)
        collector.record_metric("metric1", 15.0)

        metrics = collector.get_metrics()
        assert len(metrics) == 3

    def test_get_metrics_by_name(self, collector):
        """Test filtering metrics by name."""
        collector.record_metric("metric1", 10.0)
        collector.record_metric("metric2", 20.0)
        collector.record_metric("metric1", 15.0)

        metric1_values = collector.get_metrics_by_name("metric1")
        metric2_values = collector.get_metrics_by_name("metric2")

        assert len(metric1_values) == 2
        assert len(metric2_values) == 1
        assert all(m.name == "metric1" for m in metric1_values)

    def test_get_metrics_by_name_invalid_type(self, collector):
        """Test get_metrics_by_name with invalid name type."""
        with pytest.raises(TypeError):
            collector.get_metrics_by_name(123)

    def test_get_metrics_by_label(self, collector):
        """Test filtering metrics by label."""
        collector.record_metric(
            "metric1",
            10.0,
            labels={"tenant": "a", "status": "success"},
        )
        collector.record_metric(
            "metric1",
            20.0,
            labels={"tenant": "b", "status": "success"},
        )
        collector.record_metric(
            "metric1",
            15.0,
            labels={"tenant": "a", "status": "failure"},
        )

        tenant_a = collector.get_metrics_by_label("tenant", "a")
        success = collector.get_metrics_by_label("status", "success")

        assert len(tenant_a) == 2
        assert len(success) == 2

    def test_get_metrics_by_label_invalid_key(self, collector):
        """Test get_metrics_by_label with invalid key type."""
        with pytest.raises(TypeError):
            collector.get_metrics_by_label(123, "value")

    def test_get_metrics_by_label_invalid_value(self, collector):
        """Test get_metrics_by_label with invalid value type."""
        with pytest.raises(TypeError):
            collector.get_metrics_by_label("key", 123)

    def test_get_metrics_by_time_window(self, collector):
        """Test filtering metrics by time window."""
        now = datetime.utcnow()
        old_time = now - timedelta(hours=2)

        # Record a metric (uses current time)
        collector.record_metric("metric1", 10.0)

        # Manually add old metric with proper indexing
        metric_old = Metric(
            metric_id=str(uuid4()),
            name="metric1",
            value=5.0,
            timestamp=old_time,
            labels={},
        )
        collector._metrics[metric_old.metric_id] = metric_old
        collector._name_index["metric1"].append(metric_old.metric_id)

        # Query last 1 hour
        recent = collector.get_metrics_by_time_window("metric1", hours=1)
        all_metrics = collector.get_metrics_by_time_window("metric1", hours=3)

        assert len(recent) == 1
        assert len(all_metrics) == 2

    def test_get_metrics_by_time_window_invalid_hours(self, collector):
        """Test get_metrics_by_time_window with invalid hours."""
        with pytest.raises(ValueError):
            collector.get_metrics_by_time_window("metric1", hours=-1)

    def test_summary_statistics_single_metric(self, collector):
        """Test summary statistics for single metric."""
        collector.record_metric("latency_ms", 100.0)
        collector.record_metric("latency_ms", 150.0)
        collector.record_metric("latency_ms", 200.0)

        stats = collector.summary_statistics()

        assert "latency_ms" in stats
        assert stats["latency_ms"]["count"] == 3
        assert stats["latency_ms"]["mean"] == 150.0
        assert stats["latency_ms"]["min"] == 100.0
        assert stats["latency_ms"]["max"] == 200.0
        assert stats["latency_ms"]["p50"] >= 100.0

    def test_summary_statistics_multiple_metrics(self, collector):
        """Test summary statistics for multiple metrics."""
        collector.record_metric("metric1", 10.0)
        collector.record_metric("metric1", 20.0)
        collector.record_metric("metric2", 100.0)
        collector.record_metric("metric2", 200.0)

        stats = collector.summary_statistics()

        assert len(stats) == 2
        assert "metric1" in stats
        assert "metric2" in stats
        assert stats["metric1"]["count"] == 2
        assert stats["metric2"]["count"] == 2

    def test_summary_statistics_percentiles(self, collector):
        """Test percentile calculation in summary statistics."""
        # Add 100 values (0-99)
        for i in range(100):
            collector.record_metric("percentile_test", float(i))

        stats = collector.summary_statistics()

        assert stats["percentile_test"]["p50"] >= 0.0
        assert stats["percentile_test"]["p99"] >= 0.0

    def test_summary_statistics_with_stdev(self, collector):
        """Test standard deviation calculation."""
        collector.record_metric("metric", 10.0)
        collector.record_metric("metric", 20.0)
        collector.record_metric("metric", 30.0)

        stats = collector.summary_statistics()

        assert "stdev" in stats["metric"]
        assert stats["metric"]["stdev"] > 0

    def test_summary_statistics_empty(self, collector):
        """Test summary statistics with no metrics."""
        stats = collector.summary_statistics()
        assert stats == {}

    def test_derive_throughput(self, collector):
        """Test throughput calculation."""
        # Record 3600 operations (should be 1 op/sec over 1 hour)
        for i in range(10):
            collector.record_metric("operations", 360.0)

        throughput = collector.derive_throughput("operations", hours=1)
        assert throughput > 0

    def test_derive_throughput_invalid_metric(self, collector):
        """Test derive_throughput with no data."""
        with pytest.raises(ValueError):
            collector.derive_throughput("nonexistent", hours=1)

    def test_derive_throughput_invalid_hours(self, collector):
        """Test derive_throughput with invalid hours."""
        collector.record_metric("ops", 10.0)

        with pytest.raises(ValueError):
            collector.derive_throughput("ops", hours=0)

    def test_derive_error_rate(self, collector):
        """Test error rate calculation from audit log."""
        audit = AuditLog()

        # Log some success events
        for i in range(8):
            audit.log_event(
                action="TEST_ACTION",
                user="user",
                tenant_id="tenant",
                details={},
                status="SUCCESS",
            )

        # Log some failure events
        for i in range(2):
            audit.log_event(
                action="TEST_ACTION",
                user="user",
                tenant_id="tenant",
                details={},
                status="FAILURE",
                error_message="Test error",
            )

        collector = MetricsCollector()
        error_rate = collector.derive_error_rate(hours=1)

        assert error_rate == 20.0  # 2 out of 10

    def test_derive_error_rate_no_events(self, collector):
        """Test error rate with no audit events."""
        with pytest.raises(ValueError):
            collector.derive_error_rate(hours=1)

    def test_derive_error_rate_all_success(self, collector):
        """Test error rate when all events succeed."""
        audit = AuditLog()
        for i in range(10):
            audit.log_event(
                action="TEST",
                user="user",
                tenant_id="tenant",
                details={},
                status="SUCCESS",
            )

        collector = MetricsCollector()
        error_rate = collector.derive_error_rate(hours=1)
        assert error_rate == 0.0

    def test_derive_latency_percentile(self, collector):
        """Test latency percentile calculation."""
        # Add latencies from 100ms to 999ms
        for i in range(100, 1000):
            collector.record_metric("latency_ms", float(i))

        p50 = collector.derive_latency_percentile("latency_ms", 50)
        p99 = collector.derive_latency_percentile("latency_ms", 99)

        assert p50 > 0
        assert p99 > p50

    def test_derive_latency_percentile_invalid_percentile(self, collector):
        """Test latency percentile with invalid percentile."""
        collector.record_metric("latency_ms", 100.0)

        with pytest.raises(ValueError):
            collector.derive_latency_percentile("latency_ms", 150)

    def test_derive_latency_percentile_no_data(self, collector):
        """Test latency percentile with no data."""
        with pytest.raises(ValueError):
            collector.derive_latency_percentile("latency_ms", 50)

    def test_metric_count(self, collector):
        """Test metric counting."""
        assert collector.metric_count() == 0

        collector.record_metric("metric1", 10.0)
        assert collector.metric_count() == 1

        collector.record_metric("metric2", 20.0)
        assert collector.metric_count() == 2

    def test_clear_metrics(self, collector):
        """Test clearing all metrics."""
        collector.record_metric("metric1", 10.0)
        collector.record_metric("metric2", 20.0)
        assert collector.metric_count() == 2

        cleared = collector.clear()
        assert cleared == 2
        assert collector.metric_count() == 0


class TestMetricsScenarios:
    """Integration tests for monitoring scenarios."""

    @pytest.fixture
    def collector(self):
        """Create a fresh collector for each test."""
        AuditLog.reset()
        return MetricsCollector()

    def test_masking_performance_monitoring(self, collector):
        """Test monitoring masking operation performance."""
        # Simulate masking latencies
        latencies = [50, 75, 100, 125, 150, 200, 250, 300, 400, 500]
        for latency in latencies:
            collector.record_metric(
                "mask_latency_ms",
                float(latency),
                labels={"operation": "mask", "status": "success"},
            )

        stats = collector.summary_statistics()
        assert stats["mask_latency_ms"]["count"] == 10
        assert stats["mask_latency_ms"]["mean"] > 0

        # Calculate percentiles
        p99 = collector.derive_latency_percentile("mask_latency_ms", 99)
        assert p99 >= 50 and p99 <= 500

    def test_system_health_monitoring(self, collector):
        """Test monitoring system health metrics."""
        # Record various metrics
        collector.record_metric("vault_latency_ms", 10.0)
        collector.record_metric("vault_latency_ms", 15.0)
        collector.record_metric("vault_latency_ms", 12.0)

        collector.record_metric("audit_events_total", 1000.0)

        # Get summary
        stats = collector.summary_statistics()
        assert len(stats) >= 2
        assert "vault_latency_ms" in stats
        assert "audit_events_total" in stats

    def test_compliance_metrics_tracking(self, collector):
        """Test tracking compliance-related metrics."""
        # Track erasure requests
        collector.record_metric(
            "erasure_requests_total",
            1.0,
            labels={"reason": "GDPR_DELETION", "status": "completed"},
        )
        collector.record_metric(
            "erasure_requests_total",
            1.0,
            labels={"reason": "RETENTION_POLICY", "status": "completed"},
        )
        collector.record_metric(
            "erasure_requests_total",
            1.0,
            labels={"reason": "GDPR_DELETION", "status": "failed"},
        )

        # Query metrics
        gdpr = collector.get_metrics_by_label("reason", "GDPR_DELETION")
        completed = collector.get_metrics_by_label("status", "completed")

        assert len(gdpr) == 2
        assert len(completed) == 2

    def test_multi_tenant_metrics_isolation(self, collector):
        """Test metrics isolation across tenants."""
        # Record metrics for different tenants
        collector.record_metric(
            "operations",
            10.0,
            labels={"tenant_id": "tenant_a"},
        )
        collector.record_metric(
            "operations",
            20.0,
            labels={"tenant_id": "tenant_b"},
        )

        tenant_a = collector.get_metrics_by_label("tenant_id", "tenant_a")
        tenant_b = collector.get_metrics_by_label("tenant_id", "tenant_b")

        assert len(tenant_a) == 1
        assert len(tenant_b) == 1
        assert tenant_a[0].value == 10.0
        assert tenant_b[0].value == 20.0

    def test_time_windowed_aggregation(self, collector):
        """Test time-windowed metric aggregation."""
        # Record multiple metrics
        for i in range(5):
            collector.record_metric("latency_ms", 100.0 + i)

        # Get metrics in recent time window
        recent = collector.get_metrics_by_time_window("latency_ms", hours=1)
        assert len(recent) == 5

        # All should be within last hour
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        for metric in recent:
            assert metric.timestamp >= cutoff

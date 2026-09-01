"""Platform core functionality package.

This package contains modules for multi-tenant isolation, metrics collection,
and secure token management - forming the foundation of the enterprise
data platform.

Modules:
    tenant_aware_layer: Multi-tenant routing and isolation logic
    metrics_collector: Platform metrics and observability
    vault: Secure token storage and retrieval
"""

from .tenant_aware_layer import TenantAwareRouter
from .metrics_collector import MetricsCollector, Metric, MetricName
from .vault import VaultProvider, MockVault

__all__ = ["TenantAwareRouter", "MetricsCollector", "Metric", "MetricName", "VaultProvider", "MockVault"]

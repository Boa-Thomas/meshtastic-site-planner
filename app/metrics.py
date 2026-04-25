"""
Prometheus metrics for the Meshtastic Site Planner.

Exposes both standard FastAPI HTTP metrics and custom application counters
related to SPLAT! pipeline performance.

Metrics are registered lazily so importing this module never fails when
prometheus_client is unavailable in development environments.
"""

import logging
from contextlib import contextmanager
from time import perf_counter
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram, REGISTRY
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    Counter = Histogram = None
    REGISTRY = None


def _make_metric(metric_cls, name: str, *args, **kwargs):
    """Create a metric, returning the existing one if already registered."""
    if not _AVAILABLE:
        return None
    try:
        return metric_cls(name, *args, **kwargs)
    except ValueError:
        for collector in list(REGISTRY._names_to_collectors.values()):
            if getattr(collector, "_name", None) == name:
                return collector
        return None


simulation_duration_seconds = _make_metric(
    Histogram,
    "simulation_duration_seconds",
    "Wall-clock time of a SPLAT! coverage prediction",
    labelnames=("status", "queue"),
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
)

srtm_cache_events_total = _make_metric(
    Counter,
    "srtm_cache_events_total",
    "SRTM tile cache events (hit/miss/store) by tier",
    labelnames=("tier", "event"),
)

splat_subprocess_duration_seconds = _make_metric(
    Histogram,
    "splat_subprocess_duration_seconds",
    "Wall-clock time of the splat / splat-hd subprocess",
    labelnames=("binary",),
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

result_cache_hits_total = _make_metric(
    Counter,
    "result_cache_hits_total",
    "Result cache hits by lookup strategy (rf_hash or bbox)",
    labelnames=("strategy",),
)


@contextmanager
def measure(metric, **labels) -> Iterator[None]:
    """Context manager to record duration into a Histogram. Safe when metric is None."""
    start = perf_counter()
    try:
        yield
    finally:
        if metric is not None:
            try:
                metric.labels(**labels).observe(perf_counter() - start)
            except Exception as e:
                logger.debug(f"Metric observe failed: {e}")


def inc(metric, amount: float = 1.0, **labels) -> None:
    """Increment a Counter, safe when metric is None or labels mismatch."""
    if metric is None:
        return
    try:
        if labels:
            metric.labels(**labels).inc(amount)
        else:
            metric.inc(amount)
    except Exception as e:
        logger.debug(f"Metric inc failed: {e}")


def setup_instrumentator(app) -> Optional[object]:
    """
    Attach prometheus-fastapi-instrumentator to the FastAPI app.

    Returns the instrumentator instance or None if the dependency is missing.
    Endpoint exposed at /metrics.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        logger.info("prometheus_fastapi_instrumentator not installed; /metrics disabled")
        return None
    instrumentator = Instrumentator(
        excluded_handlers=["/metrics", "/healthz"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus metrics enabled at /metrics")
    return instrumentator

"""Structured logging and in-process metrics for STRATUM backend."""
from __future__ import annotations

import json
import time
from collections import defaultdict
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_counters: dict[str, int] = defaultdict(int)
_histograms: dict[str, list[float]] = defaultdict(list)
_trace_id: ContextVar[str | None] = ContextVar("stratum_trace_id", default=None)


def set_trace_id(trace_id: str | None):
    """Bind a trace ID to log lines emitted in the current async context."""
    return _trace_id.set(trace_id)


def reset_trace_id(token) -> None:
    _trace_id.reset(token)


def log_event(level: str, event: str, **fields: Any) -> None:
    """Emit a structured JSON log line to stdout."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "event": event,
        **fields,
    }
    if _trace_id.get() and "trace_id" not in record:
        record["trace_id"] = _trace_id.get()
    print(json.dumps(record, default=str), flush=True)


def increment_counter(name: str, by: int = 1) -> None:
    _counters[name] += by


def observe_latency(name: str, seconds: float) -> None:
    _histograms[name].append(seconds)
    if len(_histograms[name]) > 1000:
        _histograms[name] = _histograms[name][-1000:]


class LatencyTimer:
    """Context manager for recording latency and emitting completion logs."""

    def __init__(self, metric_name: str, **log_fields: Any):
        self.metric_name = metric_name
        self.log_fields = log_fields
        self._start = 0.0

    def __enter__(self) -> "LatencyTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed = time.perf_counter() - self._start
        observe_latency(self.metric_name, elapsed)
        if exc_type is not None:
            log_event(
                "error",
                f"{self.metric_name}_failed",
                latency_s=round(elapsed, 4),
                error_type=exc_type.__name__,
                **self.log_fields,
            )
            return
        log_event(
            "debug",
            f"{self.metric_name}_completed",
            latency_s=round(elapsed, 4),
            **self.log_fields,
        )


def render_prometheus_metrics() -> str:
    """Render metrics in Prometheus text exposition format."""
    lines: list[str] = []

    for name, value in sorted(_counters.items()):
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {value}")

    for name, values in sorted(_histograms.items()):
        if not values:
            continue
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        p50 = sorted_vals[n // 2]
        p95 = sorted_vals[min(n - 1, int(n * 0.95))]
        p99 = sorted_vals[min(n - 1, int(n * 0.99))]
        lines.append(f"# TYPE {name} summary")
        lines.append(f'{name}{{quantile="0.5"}} {p50:.6f}')
        lines.append(f'{name}{{quantile="0.95"}} {p95:.6f}')
        lines.append(f'{name}{{quantile="0.99"}} {p99:.6f}')
        lines.append(f"{name}_count {n}")
        lines.append(f"{name}_sum {sum(values):.6f}")

    return "\n".join(lines) + "\n"

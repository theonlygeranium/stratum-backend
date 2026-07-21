from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.observability import increment_counter, log_event, render_prometheus_metrics
import app.main as main_module


client = TestClient(main_module.app)


def test_metrics_endpoint_returns_prometheus_text() -> None:
    increment_counter("test_observability_counter")

    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE test_observability_counter counter" in response.text
    assert "test_observability_counter" in response.text


def test_counter_rendering_includes_incremented_value() -> None:
    increment_counter("test_counter_render_value", by=2)

    metrics = render_prometheus_metrics()

    assert "test_counter_render_value 2" in metrics


def test_log_event_emits_valid_json(capsys) -> None:
    log_event("warning", "unit_test_event", detail="ok")

    record = json.loads(capsys.readouterr().out)

    assert record["level"] == "warning"
    assert record["event"] == "unit_test_event"
    assert record["detail"] == "ok"
    assert "timestamp" in record

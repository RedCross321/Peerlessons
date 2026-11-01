"""Наблюдаемость: Sentry, метрики Prometheus и readiness-состояние."""

import logging
from typing import Any

from config import settings
from fastapi import Response

logger = logging.getLogger("peerlessons.observability")

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    SENTRY_AVAILABLE = True
except Exception:  # pragma: no cover - зависит от окружения
    sentry_sdk = None
    SENTRY_AVAILABLE = False


try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover - зависит от окружения
    PROMETHEUS_AVAILABLE = False


class _NoopMetric:
    """Заглушка, чтобы код приложения не зависел от prometheus-client."""

    def labels(self, *args: Any, **kwargs: Any) -> "_NoopMetric":
        return self

    def inc(self, *args: Any, **kwargs: Any) -> None:
        return None

    def dec(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set(self, *args: Any, **kwargs: Any) -> None:
        return None

    def observe(self, *args: Any, **kwargs: Any) -> None:
        return None


if PROMETHEUS_AVAILABLE:
    HTTP_REQUESTS = Counter(
        "peerlessons_http_requests_total",
        "HTTP requests",
        ["method", "path", "status"],
    )
    HTTP_DURATION = Histogram(
        "peerlessons_http_request_duration_seconds",
        "HTTP request duration",
        ["method", "path"],
        buckets=(
            0.005,
            0.01,
            0.025,
            0.05,
            0.1,
            0.25,
            0.5,
            1.0,
            2.5,
            5.0,
            10.0,
        ),
    )
    HTTP_IN_FLIGHT = Gauge("peerlessons_http_in_flight", "In-flight HTTP requests")
    WS_CONNECTIONS = Gauge("peerlessons_ws_connections", "Active WebSocket connections")
    ROOMS = Gauge("peerlessons_rooms", "Rooms with active connections")
    WS_MESSAGES = Counter(
        "peerlessons_ws_messages_total",
        "WebSocket messages",
        ["kind"],
    )
    CHAT_MESSAGES = Counter("peerlessons_chat_messages_total", "Chat messages sent")
    DB_UP = Gauge("peerlessons_db_up", "Database readiness (1 = up, 0 = down)")
else:  # pragma: no cover
    HTTP_REQUESTS = _NoopMetric()
    HTTP_DURATION = _NoopMetric()
    HTTP_IN_FLIGHT = _NoopMetric()
    WS_CONNECTIONS = _NoopMetric()
    ROOMS = _NoopMetric()
    WS_MESSAGES = _NoopMetric()
    CHAT_MESSAGES = _NoopMetric()
    DB_UP = _NoopMetric()


def init_sentry() -> None:
    """Инициализирует Sentry, если задан DSN и установлен SDK."""
    if not settings.sentry_dsn:
        return

    if not SENTRY_AVAILABLE:
        logger.warning(
            "SENTRY_DSN задан, но sentry-sdk не установлен — "
            "ошибки не будут отправляться"
        )
        return

    sample_rate = max(0.0, min(settings.sentry_traces_sample_rate, 1.0))
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
    )
    logger.info(
        "Sentry инициализирован (environment=%s, traces=%.2f)",
        settings.sentry_environment,
        sample_rate,
    )


def set_request_id(request_id: str) -> None:
    """Привязывает request_id к Sentry-событиям текущего запроса."""
    if not SENTRY_AVAILABLE or not settings.sentry_dsn:
        return
    try:
        sentry_sdk.set_tag("request_id", request_id)
    except Exception:
        pass


def metrics_response() -> Response:
    """Возвращает снимок метрик в формате Prometheus."""
    if not PROMETHEUS_AVAILABLE:
        return Response(
            content="prometheus-client is not installed\n",
            status_code=503,
            media_type="text/plain",
        )

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

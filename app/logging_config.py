"""
Structured Logging Configuration for NewsBrief.

Provides environment-aware logging:
- Production: JSON-formatted logs for machine parsing
- Development: Human-readable colored logs

Usage:
    from app.logging_config import configure_logging, log_timing

    configure_logging()  # Call once at startup

    @log_timing
    def my_function():
        ...
"""

import functools
import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any, Callable, Dict, Optional


class JSONFormatter(logging.Formatter):
    """JSON log formatter for production environments."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (duration_ms, counts, etc.)
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "taskName",
                "message",
            ):
                log_data[key] = value

        return json.dumps(log_data, default=str)


class DevFormatter(logging.Formatter):
    """Human-readable formatter for development environments."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Build base message
        base = f"{timestamp} {color}{record.levelname:8}{self.RESET} [{record.name}] {record.getMessage()}"

        # Add extra context if present
        extras = []
        for key in ("duration_ms", "feeds_count", "articles_count", "stories_count"):
            if hasattr(record, key):
                value = getattr(record, key)
                if key == "duration_ms":
                    extras.append(f"{value}ms")
                else:
                    extras.append(f"{key.replace('_count', '')}={value}")

        if extras:
            base += f" ({', '.join(extras)})"

        # Add exception if present
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)

        return base


def configure_logging(
    level: Optional[str] = None,
    force_json: bool = False,
    force_dev: bool = False,
) -> None:
    """
    Configure application-wide logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
        force_json: Force JSON formatting regardless of environment.
        force_dev: Force development formatting regardless of environment.
    """
    environment = os.environ.get("ENVIRONMENT", "development")
    log_level = level or os.environ.get("LOG_LEVEL", "INFO")

    # Determine formatter
    if force_json:
        use_json = True
    elif force_dev:
        use_json = False
    else:
        use_json = environment == "production"

    # Create handler
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter() if use_json else DevFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    for noisy_logger in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "environment": environment,
            "log_level": log_level,
            "format": "json" if use_json else "dev",
        },
    )


def log_timing(
    operation: Optional[str] = None,
    include_args: bool = False,
) -> Callable:
    """
    Decorator to log function execution time.

    Args:
        operation: Custom operation name (defaults to function name)
        include_args: Whether to include function arguments in log

    Usage:
        @log_timing
        def fetch_feeds():
            ...

        @log_timing(operation="LLM Synthesis")
        def generate_summary(text):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            op_name = operation or func.__name__

            start_time = time.perf_counter()

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                extra: Dict[str, Any] = {"duration_ms": round(duration_ms, 2)}

                if include_args and args:
                    extra["args"] = str(args[:3])  # Limit to first 3 args

                logger.info(f"{op_name} completed", extra=extra)
                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    f"{op_name} failed: {e}",
                    extra={"duration_ms": round(duration_ms, 2)},
                    exc_info=True,
                )
                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            op_name = operation or func.__name__

            start_time = time.perf_counter()

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                extra: Dict[str, Any] = {"duration_ms": round(duration_ms, 2)}
                logger.info(f"{op_name} completed", extra=extra)
                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    f"{op_name} failed: {e}",
                    extra={"duration_ms": round(duration_ms, 2)},
                    exc_info=True,
                )
                raise

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    # Handle both @log_timing and @log_timing()
    if callable(operation):
        func = operation
        operation = None
        return decorator(func)

    return decorator

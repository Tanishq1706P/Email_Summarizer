import functools
import threading
import time
from typing import Any, Callable

from logging_utils import setup_logging

logger = setup_logging("circuit_breaker")


class CircuitBreaker:
    """
    Simple circuit breaker pattern for LLM resilience.
    Matches exact usage in pipeline.py.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        expected_exceptions: tuple = (Exception,),
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.expected_exceptions = expected_exceptions
        self._failure_count = 0
        self._last_failure_time = 0
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.RLock()

    @property
    def state(self) -> str:
        with self._lock:
            now = time.time()
            if (
                self._state == "OPEN"
                and (now - self._last_failure_time) > self.recovery_timeout_seconds
            ):
                self._state = "HALF_OPEN"
            return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == "OPEN":
            raise RuntimeError(f"Circuit {self.name} is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exceptions:
            self._on_failure()
            raise

    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = "CLOSED"

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            self._state = (
                "OPEN" if self._failure_count >= self.failure_threshold else "CLOSED"
            )
        logger.warning(
            f"Circuit {self.name} failure #{self._failure_count}/{self.failure_threshold}",
            extra={"props": {"state": self._state}},
        )


def circuit(failure_threshold: int = 3, recovery_timeout: float = 30.0):
    """Decorator version."""

    def decorator(func: Callable):
        breaker = CircuitBreaker(
            name=func.__name__,
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=recovery_timeout,
        )

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator

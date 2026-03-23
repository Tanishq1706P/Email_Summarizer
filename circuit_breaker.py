import time
import logging
from typing import Callable, Any
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """
    ARC-5 Implementation: Circuit Breaker for LLM calls.
    Fails fast if the LLM (Ollama) is consistently failing or timing out.
    """
    def __init__(self, 
                 name: str, 
                 failure_threshold: int = 5, 
                 recovery_timeout_seconds: int = 30):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.logger = logging.getLogger(f"circuit_breaker.{name}")

    def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.logger.info(f"Circuit {self.name} HALF-OPEN: attempting recovery")
                self.state = CircuitState.HALF_OPEN
            else:
                raise RuntimeError(f"Circuit {self.name} is OPEN. LLM call rejected to prevent resource exhaustion.")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.logger.info(f"Circuit {self.name} CLOSED: recovery successful")
        self.state = CircuitState.CLOSED
        self.failure_count = 0

    def _on_failure(self, e: Exception):
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.logger.warning(f"Circuit {self.name} failure {self.failure_count}/{self.failure_threshold}: {e}")
        
        if self.failure_count >= self.failure_threshold:
            self.logger.error(f"Circuit {self.name} OPENED: too many failures")
            self.state = CircuitState.OPEN

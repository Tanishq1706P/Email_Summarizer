import time
from dataclasses import dataclass
from urllib.parse import urlparse

import ollama


def _is_loopback_host(host: str) -> bool:
    """
    Accepts:
      - http(s)://127.0.0.1:11434
      - http(s)://localhost:11434
      - http(s)://[::1]:11434
    """
    try:
        parsed = urlparse(host)
        hostname = parsed.hostname or ""
    except Exception:
        return False
    return hostname in {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class OllamaSettings:
    host: str
    timeout_seconds: float = 120
    keep_alive: str | None = None
    num_retries: int = 0
    retry_backoff_seconds: float = 0.5
    offline: bool = True


class LocalOllama:
    """
    Thin wrapper around the Ollama python client with:
      - explicit host
      - local/offline enforcement (loopback-only)
      - retry/backoff
      - optional keep-alive
    """

    def __init__(self, settings: OllamaSettings) -> None:
        if settings.offline and not _is_loopback_host(settings.host):
            raise ValueError(
                f"Offline mode requires loopback Ollama host, got {settings.host!r}"
            )
        self._settings = settings
        # Fixed ollama Client kwarg conflict
        self._client = ollama.Client(host=settings.host)
        if settings.timeout_seconds is not None:
            self._client.timeout = settings.timeout_seconds

    def warmup(self, model: str) -> None:
        """
        Best-effort: touch the model so the first real request doesn't pay cold-start cost.
        """
        try:
            self._client.show(model)
        except Exception as e:
            # Do not raise; model may not be loaded yet but first inference will attempt then.
            print(f"[warning] Ollama warmup failed for {model}: {e}")

    def chat_json(
        self, *, model: str, system: str | None, user: str, options: dict
    ) -> str:
        attempts = max(1, int(self._settings.num_retries) + 1)
        for i in range(attempts):
            try:
                kwargs = {
                    "model": model,
                    "messages": (
                        ([{"role": "system", "content": system}] if system else [])
                        + [{"role": "user", "content": user}]
                    ),
                    "format": "json",
                    "options": options,
                }

                # keep_alive is supported by the HTTP API; python client support varies.
                if self._settings.keep_alive:
                    try:
                        resp = self._client.chat(
                            **kwargs, keep_alive=self._settings.keep_alive
                        )
                    except TypeError:
                        resp = self._client.chat(**kwargs)
                else:
                    resp = self._client.chat(**kwargs)

                return resp["message"]["content"]
            except Exception:
                if i < attempts - 1:
                    time.sleep(self._settings.retry_backoff_seconds * (2**i))
                    continue
                raise

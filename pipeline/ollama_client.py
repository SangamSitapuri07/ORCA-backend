"""Bounded client for the local Ollama service.

Adapted from Prabhanikaur's Phase-2 Ollama client. Ollama may explain
structured findings, but it never computes measurements, thresholds, GIS
checks, or safety verdicts. Every caller must retain a deterministic fallback.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger("orca.ollama")


class OllamaClient:
    """Small synchronous wrapper around Ollama's non-streaming API."""

    def __init__(self) -> None:
        self.host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "qwen3:8b")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT_S", "25"))
        self.enabled = os.getenv("OLLAMA_ENABLED", "auto").strip().lower() not in {
            "0", "false", "no", "off", "disabled",
        }
        self._available: bool | None = None
        self._last_probe_monotonic = 0.0
        self._last_error: str | None = None
        self._lock = threading.Lock()

    def is_available(self, *, force: bool = False) -> bool:
        """Probe Ollama, caching both success and failure for 30 seconds."""
        if not self.enabled:
            self._available = False
            self._last_error = "disabled by OLLAMA_ENABLED"
            return False

        now = time.monotonic()
        with self._lock:
            if not force and self._available is not None and now - self._last_probe_monotonic < 30:
                return self._available
            try:
                response = httpx.get(f"{self.host}/api/tags", timeout=3.0)
                response.raise_for_status()
                models = [str(item.get("name", "")) for item in response.json().get("models", [])]
                aliases = {name.split(":", 1)[0] for name in models}
                requested_alias = self.model.split(":", 1)[0]
                self._available = self.model in models or requested_alias in aliases
                self._last_error = None if self._available else f"model {self.model!r} is not installed"
            except Exception as exc:  # noqa: BLE001 - optional dependency must degrade
                self._available = False
                self._last_error = f"{type(exc).__name__}: {exc}"
            self._last_probe_monotonic = now
            return self._available

    def generate(
        self,
        prompt: str,
        *,
        system: str,
        temperature: float = 0.1,
        max_tokens: int = 160,
    ) -> str | None:
        """Return generated text, or ``None`` on any optional-service failure."""
        if not self.is_available():
            return None

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "stop": ["</analysis>", "---END---"],
            },
        }
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = str(response.json().get("response", "")).strip()
            if not text:
                self._last_error = "Ollama returned an empty response"
                return None
            logger.info(
                "Ollama model %s responded in %d ms",
                self.model,
                int((time.monotonic() - started) * 1000),
            )
            self._last_error = None
            return text
        except Exception as exc:  # noqa: BLE001 - deterministic result remains valid
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Ollama enrichment failed: %s", self._last_error)
            return None

    def health(self, *, probe: bool = False) -> dict[str, Any]:
        available = self.is_available(force=True) if probe else self._available
        return {
            "enabled": self.enabled,
            "available": available,
            "status": (
                "disabled" if not self.enabled else
                "available" if available is True else
                "unavailable" if available is False else
                "not_probed"
            ),
            "host": self.host,
            "model": self.model,
            "timeout_s": self.timeout,
            "last_error": self._last_error,
            "role": "optional evidence-grounded explanation only; never safety computation",
        }


ollama = OllamaClient()

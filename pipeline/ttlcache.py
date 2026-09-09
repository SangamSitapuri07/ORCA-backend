"""Tiny in-process TTL (time-to-live) cache.

Why not pipeline/cache.py? That one is a persistent SQLite blob cache
built for 50 MB NetCDF downloads. The new Phase-4 modules (INCOIS PFZ
lines, JTWC cyclones, point forecasts) fetch small JSON/text responses
that expire in minutes-to-hours — a simple in-memory dict is the right
tool. Uvicorn runs one process, so module state is shared by every
HTTP request and WebSocket connection in that process.

Not for secrets, not for big data. Just "don't hammer the same public
server 10 times a minute".
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}
_inflight: dict[str, threading.Event] = {}


def cached(key: str, ttl_sec: float, fn: Callable[[], T],
           ttl_for: Callable[[T], float] | None = None) -> T:
    """Return cached value for `key` if fresh, else call fn() and cache it.

    Single-flight: if the same key is computed concurrently (the UI fires
    /reason + /advisory for the same point at the same moment), followers
    JOIN the leader's computation instead of duplicating a 30–90 s
    multi-source fetch. Found the hard way on a Windows laptop where two
    parallel cold fetches rate-limited the free APIs and the Next.js
    proxy reset the connection.

    ttl_for(value): optional per-RESULT ttl override — e.g. cache an
    honest failure for 10 min (so rapid retries don't re-pay the full
    failure chain) while a success stays for 6 h.
    """
    with _lock:
        ent = _store.get(key)
        if ent is not None and ent[0] > time.time():
            return ent[1]
        ev = _inflight.get(key)
        if ev is None:
            ev = threading.Event()
            _inflight[key] = ev
            leader = True
        else:
            leader = False

    if not leader:
        # Another request is already computing this key — wait for it.
        ev.wait(timeout=240)
        with _lock:
            ent = _store.get(key)
            if ent is not None:
                return ent[1]
        # Leader failed before storing; compute ourselves.
        return fn()

    try:
        value = fn()
        eff_ttl = ttl_for(value) if ttl_for is not None else ttl_sec
        with _lock:
            _store[key] = (time.time() + eff_ttl, value)
        return value
    finally:
        with _lock:
            done = _inflight.pop(key, None)
            if done is not None:
                done.set()


def cache_stats() -> dict[str, Any]:
    """Snapshot of what's cached — shown in the app's data-freshness panel."""
    now = time.time()
    with _lock:
        return {
            key: {"fresh_for_sec": round(exp - now)}
            for key, (exp, _v) in _store.items()
            if exp > now
        }


def clear() -> None:
    """Drop every cached entry and in-flight marker. Used by the test
    suite (autouse fixture) so monkey-patched fetchers aren't shadowed
    by values cached under the same key by an earlier test."""
    with _lock:
        _store.clear()
        _inflight.clear()

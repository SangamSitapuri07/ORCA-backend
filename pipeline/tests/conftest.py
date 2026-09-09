"""Shared test helpers — network gating for live-API tests."""
import socket

import pytest


def _network_up(host: str = "marine-api.open-meteo.com", port: int = 443, timeout: float = 4.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


requires_network = pytest.mark.skipif(
    not _network_up(),
    reason="live network/API unreachable from this machine — skipping live test",
)


@pytest.fixture(autouse=True)
def _fresh_ttl_cache():
    """Every test starts with an empty in-process TTL cache.

    Agent-level caches (weather 1 h, anomaly baseline 6 h) are correct in
    production but break tests that monkey-patch fetchers for the same
    coordinates — the first test's value would shadow later patches."""
    from pipeline import ttlcache
    ttlcache.clear()
    yield
    ttlcache.clear()

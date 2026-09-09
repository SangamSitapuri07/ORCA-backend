"""Freshness-aware local cache for ORCA.

Why a cache?
------------
MOSDAC files are 1-50 MB each. INCOIS advisories change daily. We
**never** want to re-download a 50 MB NetCDF when the underlying
satellite pass hasn't been replaced.

What does "freshness-aware" mean?
----------------------------------
Every cached value has a `fresh_until` timestamp. When something
asks for a value, the cache checks:
  - Do we have it?
  - Is `fresh_until` still in the future?
If yes → return the cached value, zero network calls.
If no → invalidate, the caller has to re-fetch.

This is exactly how STAC catalogs, weather APIs, and any "real-time
data" system work. We just write our own small version because the
alternatives (Redis, memcached) are overkill for a hackathon.

Storage
-------
We use SQLite for the metadata (URL, when fetched, fresh_until, hash)
and we keep the actual file blobs on disk in a content-addressed
fashion (sha256 → path). That way:
  * Two requests for the "same" data share one download
  * Cleanup is just `rm -rf data/cache/blobs/`
  * We can see what's in the cache at a glance

This file deliberately does NOT use any heavy framework. Just stdlib
sqlite3 + hashlib + pathlib. Easy to read, easy to debug.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Default location for the cache. Override by setting ORCA_CACHE_DIR.
DEFAULT_CACHE_DIR = os.environ.get(
    "ORCA_CACHE_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "cache"),
)

# A entry is considered "fresh" if it was fetched within this many hours
# and we haven't told the cache otherwise. Different data types have
# different real-time-ness; see DEFAULT_TTLS below.
DEFAULT_TTLS = {
    "mosdac_l4_chlorophyll_hours": 24 * 2,   # 2 days
    "mosdac_l4_wind_hours": 24,                # 1 day
    "mosdac_l4_upwelling_hours": 24 * 2,       # 2 days
    "incois_advisory_hours": 6,                # INCOIS refreshes daily
    "openmeteo_forecast_hours": 1,             # weather changes hourly
}


@dataclass
class CacheEntry:
    """A single value in the cache. The blob itself lives on disk."""
    key: str                # unique identifier, e.g. "mosdac:E06OCM_L4_AC:20260830:indian_ocean"
    source: str             # where it came from
    fetched_at: datetime
    fresh_until: datetime
    blob_path: Path | None  # path on disk if it's a file, None if inline
    inline_value: Any       # for small values (a dict, a few KB), store inline
    metadata: dict


class Cache:
    """The cache. Use like:
        cache = Cache()
        if not cache.has_fresh("mosdac:E06OCM_L4_AC:20260830"):
            file_path = download_from_mosdac(...)
            cache.put("mosdac:E06OCM_L4_AC:20260830",
                      source="MOSDAC", blob_path=file_path,
                      fresh_for=timedelta(days=2))
        entry = cache.get("mosdac:E06OCM_L4_AC:20260830")
    """

    def __init__(self, root: str | os.PathLike | None = None) -> None:
        self.root = Path(root) if root else Path(DEFAULT_CACHE_DIR)
        self.blobs_dir = self.root / "blobs"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "cache.sqlite"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    key          TEXT PRIMARY KEY,
                    source       TEXT NOT NULL,
                    fetched_at   TEXT NOT NULL,
                    fresh_until  TEXT NOT NULL,
                    blob_path    TEXT,
                    inline_value TEXT,
                    metadata     TEXT
                )
                """
            )
            # Index for fast "is it fresh?" lookups
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fresh_until ON entries(fresh_until)"
            )

    def has_fresh(self, key: str, now: datetime | None = None) -> bool:
        """Return True if the cache has a non-expired entry for `key`."""
        now = now or datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT fresh_until FROM entries WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return False
        return datetime.fromisoformat(row[0]) > now

    def get(self, key: str) -> CacheEntry | None:
        """Return the cache entry for `key` or None if missing/expired.

        Returns the entry even if expired (caller can decide what to do);
        use `has_fresh` first if you only want live data.
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT key, source, fetched_at, fresh_until, blob_path, "
                "inline_value, metadata FROM entries WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        inline = row[5]
        if inline is not None:
            try:
                inline = json.loads(inline)
            except (TypeError, ValueError):
                pass
        return CacheEntry(
            key=row[0],
            source=row[1],
            fetched_at=datetime.fromisoformat(row[2]),
            fresh_until=datetime.fromisoformat(row[3]),
            blob_path=Path(row[4]) if row[4] else None,
            inline_value=inline,
            metadata=json.loads(row[6] or "{}"),
        )

    def put(
        self,
        key: str,
        source: str,
        fresh_for: timedelta,
        blob_path: str | os.PathLike | None = None,
        inline_value: Any = None,
        metadata: dict | None = None,
    ) -> CacheEntry:
        """Store a value. `fresh_for` is the TTL from now."""
        now = datetime.now(timezone.utc)
        entry = CacheEntry(
            key=key,
            source=source,
            fetched_at=now,
            fresh_until=now + fresh_for,
            blob_path=Path(blob_path) if blob_path else None,
            inline_value=inline_value,
            metadata=metadata or {},
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO entries
                    (key, source, fetched_at, fresh_until, blob_path,
                     inline_value, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.key,
                    entry.source,
                    entry.fetched_at.isoformat(),
                    entry.fresh_until.isoformat(),
                    str(entry.blob_path) if entry.blob_path else None,
                    json.dumps(inline_value) if inline_value is not None else None,
                    json.dumps(entry.metadata),
                ),
            )
        return entry

    def invalidate(self, key: str) -> None:
        """Remove a key from the cache (next get will re-fetch)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM entries WHERE key = ?", (key,))

    def list(self, only_fresh: bool = True) -> list[CacheEntry]:
        """List all cache entries, optionally filtering to fresh ones."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT key, source, fetched_at, fresh_until, blob_path, "
                "inline_value, metadata FROM entries"
            ).fetchall()
        out: list[CacheEntry] = []
        for row in rows:
            inline = row[5]
            if inline is not None:
                try:
                    inline = json.loads(inline)
                except (TypeError, ValueError):
                    pass
            out.append(
                CacheEntry(
                    key=row[0],
                    source=row[1],
                    fetched_at=datetime.fromisoformat(row[2]),
                    fresh_until=datetime.fromisoformat(row[3]),
                    blob_path=Path(row[4]) if row[4] else None,
                    inline_value=inline,
                    metadata=json.loads(row[6] or "{}"),
                )
            )
        if only_fresh:
            now = datetime.now(timezone.utc)
            out = [e for e in out if e.fresh_until > now]
        return out

    def stats(self) -> dict:
        """Quick stats — useful for `python -m pipeline.cache stats`."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            fresh = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE fresh_until > ?",
                (datetime.now(timezone.utc).isoformat(),),
            ).fetchone()[0]
        blobs = sum(1 for _ in self.blobs_dir.glob("*"))
        return {
            "total_entries": total,
            "fresh_entries": fresh,
            "stale_entries": total - fresh,
            "blob_files_on_disk": blobs,
            "cache_root": str(self.root),
        }


def freshness_label(entry: CacheEntry) -> str:
    """Return a human-readable freshness label like '2h ago' or '3d ago'.

    Useful for the UI's freshness badges.
    """
    age = datetime.now(timezone.utc) - entry.fetched_at
    if age.total_seconds() < 60:
        return "just now"
    if age.total_seconds() < 3600:
        return f"{int(age.total_seconds() // 60)}m ago"
    if age.total_seconds() < 86400:
        return f"{int(age.total_seconds() // 3600)}h ago"
    return f"{int(age.total_seconds() // 86400)}d ago"


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    c = Cache()

    if cmd == "stats":
        s = c.stats()
        print("Cache stats:")
        for k, v in s.items():
            print(f"  {k}: {v}")
        print()
        entries = c.list(only_fresh=False)
        if entries:
            print(f"Entries ({len(entries)}):")
            for e in entries:
                fresh_marker = "🟢" if e.fresh_until > datetime.now(timezone.utc) else "⚪"
                print(
                    f"  {fresh_marker} {e.key}  ·  source={e.source}  ·  "
                    f"age={freshness_label(e)}  ·  "
                    f"fresh_until={e.fresh_until.isoformat()}"
                )
        else:
            print("No entries yet.")
    elif cmd == "clear":
        confirm = input(f"Delete all cache entries under {c.root}? (yes/no): ")
        if confirm.strip().lower() == "yes":
            with sqlite3.connect(c.db_path) as conn:
                conn.execute("DELETE FROM entries")
            print("✅ Cache cleared.")
        else:
            print("Cancelled.")
    else:
        print(f"Unknown command: {cmd!r}. Use 'stats' or 'clear'.")

"""
Generic TTL-aware disk cache.

Every external data source in this project (yfinance, fear & greed, macro
calendar, news/catalysts) goes through this. The point: if a source is down
or rate-limited, callers get the last cached value (even if stale) instead of
a crash, and a clear "fetch failed, using cache from <time>" signal.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

if getattr(sys, "frozen", False):
    # Packaged .exe (PyInstaller onefile): the app runs out of a temp dir
    # (sys._MEIPASS) that's deleted when the process exits, so a cache
    # written there would never survive between launches — every run would
    # have to refetch everything from scratch, defeating the point of
    # caching. Persist next to the .exe itself instead.
    CACHE_ROOT = Path(sys.executable).resolve().parent / "data" / "cache"
else:
    CACHE_ROOT = Path(__file__).resolve().parents[2] / "data" / "cache"


def _path_for(namespace: str, key: str) -> Path:
    safe_key = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    d = CACHE_ROOT / namespace
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe_key}.json"


def get_cached(namespace: str, key: str, ttl_hours: float) -> Optional[Any]:
    """Return cached value if present and not older than ttl_hours, else None."""
    p = _path_for(namespace, key)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    age_hours = (time.time() - payload.get("_cached_at", 0)) / 3600
    if age_hours > ttl_hours:
        return None
    return payload.get("value")


def get_cached_even_if_stale(namespace: str, key: str) -> Optional[Any]:
    """Fallback read: return whatever's cached regardless of age. Used when a
    live fetch fails and something is better than nothing."""
    p = _path_for(namespace, key)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return payload.get("value")


def set_cached(namespace: str, key: str, value: Any) -> None:
    p = _path_for(namespace, key)
    p.write_text(json.dumps({"_cached_at": time.time(), "value": value}, default=str))


def cached_fetch(
    namespace: str,
    key: str,
    ttl_hours: float,
    fetch_fn: Callable[[], Any],
) -> tuple[Any, bool]:
    """
    Fetch-through cache with graceful degradation.

    Returns (value, is_fresh). is_fresh=False means either a cached (possibly
    stale) value was used because the live fetch failed, or a stale cache hit.
    Raises only if fetch_fn fails AND there is no cache at all — callers should
    still catch that and render an "unavailable" state rather than crash a page.
    """
    fresh = get_cached(namespace, key, ttl_hours)
    if fresh is not None:
        return fresh, True

    try:
        value = fetch_fn()
        set_cached(namespace, key, value)
        return value, True
    except Exception:
        stale = get_cached_even_if_stale(namespace, key)
        if stale is not None:
            return stale, False
        raise

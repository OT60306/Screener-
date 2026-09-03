"""
Macro event calendar (NFP, FOMC, CPI, etc). No free live economic-calendar API
is wired in — this reads the maintained list from config.yaml. Swap for a live
source later behind get_upcoming_events(); keep the same return shape.

Each configured event may carry a "date" (YYYY-MM-DD, the next/most recent
occurrence — update as it rolls) and a "consensus" one-line note. When today
falls on (or within a day of) that date, the event is flagged so the UI can
surface the consensus summary instead of just the recurring-frequency text.
"""
from __future__ import annotations

from datetime import date, datetime


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_upcoming_events(cfg: dict, today: date | None = None) -> list[dict]:
    today = today or date.today()
    events = cfg.get("macro_events", [])
    if not events:
        return [{"name": "No macro events configured", "frequency": "—", "is_event_day": False}]

    out = []
    for ev in events:
        ev_date = _parse_date(ev.get("date"))
        days_until = (ev_date - today).days if ev_date else None
        is_event_day = days_until is not None and -1 <= days_until <= 1
        out.append(
            {
                **ev,
                "date": ev_date.isoformat() if ev_date else None,
                "days_until": days_until,
                "is_event_day": is_event_day,
            }
        )
    out.sort(key=lambda e: (e["days_until"] is None, e["days_until"] if e["days_until"] is not None else 0))
    return out

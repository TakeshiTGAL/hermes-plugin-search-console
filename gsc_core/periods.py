"""Choosing comparison windows that only contain finalised Search Console data.

Search Console days are US Pacific time days, and the most recent 2-3 days are still being
processed (numbers keep rising). Comparing them with a finished week makes every site look like
it is falling. The API reports the first unfinished day as ``metadata.firstIncompleteDate`` when
asked with ``dataState: all``; the windows end the day before it and the excluded days are reported.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

try:
    from zoneinfo import ZoneInfo

    _PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover - tzdata missing on a minimal Windows install
    _PACIFIC = None

ASSUMED_LAG_DAYS = 3


def pacific_today() -> dt.date:
    now = dt.datetime.now(_PACIFIC) if _PACIFIC else dt.datetime.utcnow() - dt.timedelta(hours=8)
    return now.date()


@dataclass(frozen=True)
class Window:
    start: dt.date
    end: dt.date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def body(self) -> dict:
        return {"startDate": self.start.isoformat(), "endDate": self.end.isoformat()}

    def to_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "days": self.days}


@dataclass(frozen=True)
class Periods:
    current: Window
    previous: Window
    last_final: dt.date
    excluded: Window | None  # unfinished days left out of the comparison
    source: str  # "metadata" | "rows" | "assumed"

    def to_dict(self) -> dict:
        return {
            "current": self.current.to_dict(),
            "previous": self.previous.to_dict(),
            "last_final_date": self.last_final.isoformat(),
            "excluded_unfinished": self.excluded.to_dict() if self.excluded else None,
            "how_last_final_was_found": self.source,
            "timezone": "Search Console days are US Pacific time (America/Los_Angeles).",
        }


def find_last_final(client, site: str, today: dt.date | None = None) -> tuple[dt.date, Window | None, str]:
    today = today or pacific_today()
    probe = {
        "startDate": (today - dt.timedelta(days=10)).isoformat(),
        "endDate": today.isoformat(),
        "dimensions": ["date"],
        "dataState": "all",
        "type": "web",
    }
    data = client.search_analytics(site, probe)
    first_incomplete = (data.get("metadata") or {}).get("firstIncompleteDate")
    if first_incomplete:
        fid = dt.date.fromisoformat(first_incomplete)
        end = max(today, fid)
        return fid - dt.timedelta(days=1), Window(fid, end), "metadata"
    dates = [dt.date.fromisoformat(r["keys"][0]) for r in data.get("rows") or [] if r.get("keys")]
    if dates:
        # No unfinished marker means every returned day is final.
        return max(dates), None, "rows"
    last = today - dt.timedelta(days=ASSUMED_LAG_DAYS)
    return last, Window(last + dt.timedelta(days=1), today), "assumed"


def make_periods(last_final: dt.date, days: int, excluded: Window | None, source: str) -> Periods:
    current = Window(last_final - dt.timedelta(days=days - 1), last_final)
    previous = Window(current.start - dt.timedelta(days=days), current.start - dt.timedelta(days=1))
    return Periods(current, previous, last_final, excluded, source)


def explicit_periods(current_start: str, current_end: str, previous_start: str | None,
                     previous_end: str | None, last_final: dt.date, excluded: Window | None, source: str) -> Periods:
    cur = Window(dt.date.fromisoformat(current_start), dt.date.fromisoformat(current_end))
    if cur.end < cur.start:
        raise ValueError("current_end is before current_start")
    if previous_start and previous_end:
        prev = Window(dt.date.fromisoformat(previous_start), dt.date.fromisoformat(previous_end))
    else:
        prev = Window(cur.start - dt.timedelta(days=cur.days), cur.start - dt.timedelta(days=1))
    return Periods(cur, prev, last_final, excluded, source)

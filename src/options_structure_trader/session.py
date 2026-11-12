from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd


class SessionCalendar:
    """Standalone US-equity session gate with exchange-calendar authority and a safe fallback."""

    def __init__(self, calendar_name: str = "XNYS"):
        self.calendar_name = calendar_name
        self._calendar = None
        self.authoritative = False
        try:
            import exchange_calendars as xcals
            self._calendar = xcals.get_calendar(calendar_name)
            self.authoritative = True
        except Exception:
            self._calendar = None

    def evaluate(self, at: datetime) -> dict[str, object]:
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        at = at.astimezone(timezone.utc)
        eastern = at.astimezone(ZoneInfo("America/New_York"))
        if self._calendar is not None:
            minute = pd.Timestamp(at).floor("min")
            try:
                is_open = bool(self._calendar.is_open_on_minute(minute, ignore_breaks=True))
                session_label = self._calendar.minute_to_session(minute, direction="previous")
                session_close = self._calendar.session_close(session_label).to_pydatetime()
                session_open = self._calendar.session_open(session_label).to_pydatetime()
                is_session_day = bool(self._calendar.is_session(pd.Timestamp(eastern.date())))
                next_open = self.next_open(at)
                next_close = None
                if is_open:
                    next_close = session_close
                elif next_open:
                    next_label = self._calendar.date_to_session(pd.Timestamp(next_open.date()), direction="none")
                    next_close = self._calendar.session_close(next_label).to_pydatetime()
                return {"calendar": self.calendar_name, "authoritative": True, "is_open": is_open,
                        "is_session_day": is_session_day, "state": "regular" if is_open else "closed",
                        "session_open_utc": session_open.isoformat(), "session_close_utc": session_close.isoformat(),
                        "next_rth_open_utc": next_open.isoformat() if next_open else None,
                        "next_rth_close_utc": next_close.isoformat() if next_close else None,
                        "last_rth_close_utc": session_close.isoformat(),
                        "evaluated_at_utc": at.isoformat()}
            except Exception as exc:
                error = str(exc)
            else:
                error = None
        else:
            error = "exchange_calendars unavailable"
        weekday = eastern.weekday() < 5
        is_open = weekday and time(9, 30) <= eastern.time().replace(tzinfo=None) < time(16, 0)
        next_open = self.next_open(at)
        close_local = eastern.replace(hour=16, minute=0, second=0, microsecond=0)
        if not is_open and next_open:
            close_local = next_open.astimezone(ZoneInfo("America/New_York")).replace(
                hour=16, minute=0, second=0, microsecond=0)
        return {"calendar": self.calendar_name, "authoritative": False, "is_open": is_open,
                "is_session_day": weekday, "state": "regular" if is_open else "closed",
                "session_open_utc": None, "session_close_utc": None,
                "next_rth_open_utc": next_open.isoformat() if next_open else None,
                "next_rth_close_utc": close_local.astimezone(timezone.utc).isoformat(),
                "last_rth_close_utc": close_local.astimezone(timezone.utc).isoformat() if not is_open else None,
                "evaluated_at_utc": at.isoformat(), "fallback_reason": error}

    def next_open(self, at: datetime) -> datetime | None:
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        at = at.astimezone(timezone.utc)
        if self._calendar is not None:
            start = pd.Timestamp(at.date())
            sessions = self._calendar.sessions_in_range(start, start + pd.Timedelta(days=14))
            for session in sessions:
                opening = self._calendar.session_open(session).to_pydatetime().astimezone(timezone.utc)
                if opening > at:
                    return opening
        eastern_zone = ZoneInfo("America/New_York")
        local = at.astimezone(eastern_zone)
        for offset in range(8):
            day = (local + timedelta(days=offset)).date()
            if day.weekday() >= 5:
                continue
            candidate = datetime.combine(day, time(9, 30), eastern_zone).astimezone(timezone.utc)
            if candidate > at:
                return candidate
        return None

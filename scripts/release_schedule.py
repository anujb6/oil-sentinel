"""When the next EIA Weekly Petroleum Status Report comes out.

EIA's rule: Wednesday 10:30 a.m. Eastern, five days after the Friday the data week ends. Holiday weeks move to
another day and time, listed on EIA's schedule page (e.g. Veterans Day 2026: Thursday 12 Nov, 12:00 p.m.). This reads
that page's table; when it can't be read, the standard rule is used and the result says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import html as html_lib
import re
from zoneinfo import ZoneInfo

SCHEDULE_URL = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"
EASTERN = ZoneInfo("America/New_York")
STANDARD_RELEASE_DELAY_DAYS = 5  # Friday week end -> Wednesday
STANDARD_RELEASE_TIME = time(10, 30)
DAYS_PER_WEEK = 7
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
CLOCK = re.compile(r"(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?", re.I)


@dataclass(frozen=True)
class HolidayRelease:
    release: datetime  # aware, Eastern
    holiday: str


class ReleaseSchedule:
    """Parses EIA's holiday table and answers when a given data week is released."""

    def __init__(self, exceptions: dict[date, HolidayRelease] | None = None, source: str = "standard rule"):
        self.exceptions = exceptions or {}
        self.source = source

    @classmethod
    def from_html(cls, page: str) -> "ReleaseSchedule":
        exceptions: dict[date, HolidayRelease] = {}
        for row in ROW.findall(page):
            cells = [html_lib.unescape(TAG.sub("", c)).strip() for c in CELL.findall(row)]
            if len(cells) < 5:
                continue
            week, released, _weekday, clock, holiday = cells[:5]
            try:
                week_end = datetime.strptime(week, "%B %d, %Y").date()
                day = datetime.strptime(released, "%B %d, %Y").date()
            except ValueError:
                continue
            match = CLOCK.search(clock)
            if match is None:
                continue
            hour = int(match.group(1)) % 12 + (12 if match.group(3).lower() == "p" else 0)
            at = datetime.combine(day, time(hour, int(match.group(2))), tzinfo=EASTERN)
            exceptions[week_end] = HolidayRelease(at, holiday)
        return cls(exceptions, "EIA schedule" if exceptions else "standard rule")

    def release_for(self, week_ending: date) -> dict:
        """The release of the data week ending on `week_ending` (a Friday), in UTC and Eastern."""
        special = self.exceptions.get(week_ending)
        if special is not None:
            at, holiday = special.release, special.holiday
        else:
            day = week_ending + timedelta(days=STANDARD_RELEASE_DELAY_DAYS)
            at, holiday = datetime.combine(day, STANDARD_RELEASE_TIME, tzinfo=EASTERN), None
        return {
            "week_ending": week_ending.isoformat(),
            "release_utc": at.astimezone(timezone.utc).isoformat(timespec="minutes"),
            "release_eastern": at.strftime("%a %d %b, %I:%M %p ET").replace(" 0", " "),
            "holiday": holiday,
            "source": self.source,
        }

    def next_after(self, latest_week: date) -> dict:
        """The report after the latest one published: the next data week."""
        return self.release_for(latest_week + timedelta(days=DAYS_PER_WEEK))

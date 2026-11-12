"""The newest week from EIA's Weekly Petroleum Status Report tables, published at the release itself.

EIA's per-series history workbooks (dnav/pet/hist_xls) can lag the release by hours: on 12 Nov 2026 Cushing's file
updated at 17:36 UTC but US crude, gasoline and distillate still ended a week earlier. The release's own tables
(ir.eia.gov/wpsr/table1.csv and table4.csv, million barrels) carry the new week at release time, together with the
week before it. A table week is added to a series only when it is exactly one week after the series' last week AND
the table's prior-week figure matches the series' last value, so a renamed row or a unit change can never slip in.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import io

TABLE1_URL = "https://ir.eia.gov/wpsr/table1.csv"
TABLE4_URL = "https://ir.eia.gov/wpsr/table4.csv"
# Series key -> (table, row label). Table 1 holds the national stocks, table 4 the Cushing line.
ROWS = {
    "us_crude": ("table1", "Commercial (Excluding SPR)"),
    "gasoline": ("table1", "Total Motor Gasoline"),
    "distillate": ("table1", "Distillate Fuel Oil"),
    "cushing": ("table4", "Cushing"),
}
HEADER_DATE = "%m/%d/%y"
WEEK = timedelta(days=7)
# The table rounds to thousand barrels and the workbook keeps thousands too: anything off by more is not the same row.
MATCH_TOLERANCE_MB = 0.0015


@dataclass(frozen=True)
class ReleaseWeek:
    """One series' newest week in the release tables and the week before it, in million barrels."""

    week: date
    mb: float
    prior_week: date
    prior_mb: float


class ReleaseTables:
    """Parses table1.csv and table4.csv into the newest week of each series it knows."""

    @staticmethod
    def parse(tables: dict[str, str]) -> dict[str, ReleaseWeek]:
        found: dict[str, ReleaseWeek] = {}
        for key, (table, label) in ROWS.items():
            text = tables.get(table)
            if not text:
                continue
            week = ReleaseTables._row(text, label)
            if week is not None:
                found[key] = week
        return found

    @staticmethod
    def _row(text: str, label: str) -> ReleaseWeek | None:
        rows = list(csv.reader(io.StringIO(text)))
        if not rows or len(rows[0]) < 3:
            return None
        try:
            week = datetime.strptime(rows[0][1].strip(), HEADER_DATE).date()
            prior_week = datetime.strptime(rows[0][2].strip(), HEADER_DATE).date()
        except ValueError:
            return None
        for row in rows[1:]:
            # The first table in the file ends at the next header row; a later table has other columns.
            if row and row[0].strip() == rows[0][0].strip():
                break
            if len(row) >= 3 and row[0].strip() == label:
                try:
                    return ReleaseWeek(week, ReleaseTables._number(row[1]), prior_week, ReleaseTables._number(row[2]))
                except ValueError:
                    return None
        return None

    @staticmethod
    def _number(text: str) -> float:
        return float(text.replace(",", "").strip())

    @staticmethod
    def extend(points: list[dict], release: ReleaseWeek) -> list[dict] | None:
        """The history ({"date", "mb"}, oldest first) with the release week added, or None when it can't be added
        safely (not the next week, or the prior week doesn't match the stored value)."""
        if not points:
            return None
        last = points[-1]
        last_day = date.fromisoformat(last["date"])
        if release.week != last_day + WEEK or release.prior_week != last_day:
            return None
        if abs(float(last["mb"]) - release.prior_mb) > MATCH_TOLERANCE_MB:
            return None
        return [*points, {"date": release.week.isoformat(), "mb": round(release.mb, 3)}]

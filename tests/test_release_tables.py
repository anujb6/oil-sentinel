import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from datetime import date

import release_tables as rt
import update

TABLE1 = '''"STUB_1","11/6/26","10/30/26","Difference","Percent Change","11/7/25","Difference","Percent Change"
"Crude Oil","693.952","691.944","2.008","0.300","837.974","-144.022","-17.200"
"Commercial (Excluding SPR)","414.417","409.760","4.657","1.100","427.581","-13.164","-3.100"
"Total Motor Gasoline","210.757","208.958","1.799","0.9","1","1","1"
"Distillate Fuel Oil","103.330","99.259","4.071","4.1","1","1","1"
"Total Stocks (Including SPR)","1,495.268","1,490.000","5","0.3","1","1","1"
"STUB_1","STUB_2","11/6/26","10/30/26"
"Crude Oil Supply ","(1)     Domestic Production","14,013","13,900"
'''
TABLE4 = '''"STUB_1","11/6/26","10/30/26","Difference","11/7/25","Percent Change","11/8/24","Percent Change"
"Crude Oil","693.952","691.944","2.008","837.974","-17.200","817.537","-15.100"
"Cushing","27.356","27.250","0.106","22.519","21.500","25.191","8.600"
'''


def history(last_day, last_mb):
    return [{"date": "2026-10-23", "mb": last_mb - 1.0}, {"date": last_day, "mb": last_mb}]


def test_parses_the_newest_week_of_each_series():
    found = rt.ReleaseTables.parse({"table1": TABLE1, "table4": TABLE4})
    assert found["us_crude"] == rt.ReleaseWeek(date(2026, 11, 6), 414.417, date(2026, 10, 30), 409.760)
    assert found["cushing"].mb == 27.356 and found["distillate"].prior_mb == 99.259
    assert found["gasoline"].week == date(2026, 11, 6)


def test_adds_the_next_week_only_when_the_prior_week_matches():
    week = rt.ReleaseTables.parse({"table1": TABLE1})["distillate"]
    assert rt.ReleaseTables.extend(history("2026-10-30", 99.259), week)[-1] == {"date": "2026-11-06", "mb": 103.33}
    assert rt.ReleaseTables.extend(history("2026-10-30", 98.0), week) is None  # another row or unit
    assert rt.ReleaseTables.extend(history("2026-11-06", 103.33), week) is None  # already there
    assert rt.ReleaseTables.extend(history("2026-10-23", 99.259), week) is None  # a week missing in between


def series(key, points):
    return update.series_from_points(points, key.upper(), key)


def test_a_lagging_workbook_is_filled_from_the_release_and_the_weeks_line_up():
    base = [{"date": f"2026-10-{d:02d}", "mb": 100.0 + d} for d in (2, 9, 16, 23, 30)]
    data = {
        "us_crude": series("us_crude", [*base, {"date": "2026-11-06", "mb": 140.0}]),
        "distillate": series("distillate", [*base[:-1], {"date": "2026-10-30", "mb": 99.259}]),
    }
    releases = rt.ReleaseTables.parse({"table1": TABLE1})
    assert update.extend_from_release(data, releases) == ["distillate"]
    assert data["distillate"]["as_of"] == "2026-11-06" and data["distillate"]["week_change_mb"] == 4.071
    assert update.align_weeks(data, ("us_crude", "distillate")) == "2026-11-06"


def test_mixed_weeks_are_held_at_the_week_every_series_has():
    base = [{"date": f"2026-10-{d:02d}", "mb": 100.0 + d} for d in (2, 9, 16, 23, 30)]
    data = {
        "cushing": series("cushing", [*base, {"date": "2026-11-06", "mb": 27.356}]),
        "us_crude": series("us_crude", base),
    }
    assert update.align_weeks(data, ("cushing", "us_crude")) == "2026-10-30"
    assert data["cushing"]["as_of"] == "2026-10-30" and "Held at the week" in data["cushing"]["source_note"]

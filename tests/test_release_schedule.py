import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from release_schedule import ReleaseSchedule
from update import next_report_sentence

PAGE = '''<table>
<tr><th>Data for week ending</th><th>Release date</th><th>Day</th><th>Time</th><th>Holiday</th></tr>
<tr class="holiday"><th scope="row">November 6, 2026</th><td>November 12, 2026</td><td>Thursday</td><td>12:00 p.m.</td><td>Veterans Day</td></tr>
<tr class="past-holiday"><th scope="row">December 19, 2025</th><td class="message-updated">December 29, 2025</td><td>Monday</td><td>5:00 p.m.</td><td>Christmas</td></tr>
</table>'''


def test_holiday_weeks_come_from_the_eia_table():
    s = ReleaseSchedule.from_html(PAGE)
    assert s.source == 'EIA schedule'
    r = s.release_for(date(2026, 11, 6))
    assert r['release_utc'] == '2026-11-12T17:00+00:00'  # noon Eastern
    assert r['holiday'] == 'Veterans Day'
    assert s.release_for(date(2025, 12, 19))['release_utc'] == '2025-12-29T22:00+00:00'  # 5 p.m. Eastern, Monday


def test_other_weeks_use_wednesday_1030_eastern_in_both_daylight_seasons():
    s = ReleaseSchedule.from_html(PAGE)
    assert s.release_for(date(2026, 11, 13))['release_utc'] == '2026-11-18T15:30+00:00'  # EST
    assert s.release_for(date(2026, 7, 3))['release_utc'] == '2026-07-08T14:30+00:00'  # EDT


def test_unreadable_page_falls_back_to_the_standard_rule():
    s = ReleaseSchedule.from_html('<html>nothing here</html>')
    assert s.source == 'standard rule'
    assert s.next_after(date(2026, 10, 30))['week_ending'] == '2026-11-06'
    assert s.next_after(date(2026, 10, 30))['holiday'] is None


def test_spoken_line():
    assert next_report_sentence({'release_eastern': 'Thu 12 Nov, 12:00 PM ET', 'holiday': 'Veterans Day'}) == 'Next report due Thu 12 Nov, 12:00 PM ET, moved for Veterans Day. '
    assert next_report_sentence({}) == ''

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from report_verdict import ReportVerdict, Walk


def walk(actual, expected, weeks):
    idx = pd.date_range('2015-01-02', periods=weeks, freq='W-FRI')
    frame = pd.DataFrame({'y': actual, 'p': expected}, index=idx)
    return Walk.of(frame)


def test_lower_than_normal_stocks_read_bullish_and_higher_bearish():
    n = 60
    expected = np.zeros(n)
    us_actual = np.r_[np.tile([2.0, -2.0], (n - 2) // 2), [0.0, -4.0]]
    flat = walk(np.zeros(n), expected, n)
    v = ReportVerdict(walk(us_actual, expected, n), flat, flat)
    assert v.latest()['verdict'] == 'bullish'
    assert v.latest()['parts'][0]['leans'] == 'bullish'
    us_actual[-1] = 4.0
    assert ReportVerdict(walk(us_actual, expected, n), flat, flat).latest()['verdict'] == 'bearish'
    us_actual[-1] = 0.2
    assert ReportVerdict(walk(us_actual, expected, n), flat, flat).latest()['verdict'] == 'neutral'


def test_levels_bracket_the_expected_change_for_the_next_report():
    n = 60
    actual = np.r_[np.tile([2.0, -2.0], n // 2 - 1), [1.0, np.nan]]
    expected = np.r_[np.zeros(n - 1), [2.4]]
    us = walk(actual, expected, n)
    flat = walk(np.zeros(n), np.zeros(n), n)
    lv = ReportVerdict(us, flat, flat).levels()
    assert lv['expected_mb'] == 2.4
    assert lv['bullish_below_mb'] < 2.4 < lv['bearish_above_mb']


def test_track_record_counts_release_day_moves_in_the_called_direction():
    n = 40
    expected = np.zeros(n)
    actual = np.tile([-3.0, 3.0], n // 2)  # alternating bullish / bearish reports
    flat = walk(np.zeros(n), expected, n)
    v = ReportVerdict(walk(actual, expected, n), flat, flat)
    days = pd.bdate_range('2014-12-01', '2015-12-31')
    weeks = pd.date_range('2015-01-02', periods=n, freq='W-FRI')
    up_days = {w + pd.Timedelta(days=5) for w, a in zip(weeks, actual) if a < 0}
    moves = [1.0 if d in up_days else -1.0 for d in days]
    prices = pd.Series(100 * np.cumprod(1 + np.array(moves) / 100), index=days)
    record = v.track_record(prices)
    assert record['called'] == n
    assert record['right_pct'] == 100.0
    assert record['bullish_avg_move_pct'] > 0 > record['bearish_avg_move_pct']

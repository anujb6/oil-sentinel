import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from forecast import InventoryForecaster, US_SPEC, CUSHING_SPEC, SeriesSpec
from update import build_forecast, forecast_sentence

WEEKS = 52 * 18


def seasonal_levels(noise=0.0, seed=0):
    """Weekly stocks whose change follows a fixed yearly pattern (+3M early year, -3M mid-year)."""
    dates = pd.date_range('2005-01-07', periods=WEEKS, freq='W-FRI')
    week = np.minimum(dates.isocalendar().week.to_numpy(dtype=int), 52)
    change = 3.0 * np.cos(2 * np.pi * week / 52) + np.random.default_rng(seed).normal(0, noise, len(dates))
    return pd.Series(400 + np.cumsum(change), index=dates)


def test_seasonal_forecast_recovers_a_pure_pattern():
    levels = seasonal_levels()
    out = InventoryForecaster().forecast(levels, US_SPEC)
    target = pd.Timestamp(out['target_week'])
    expected = 3.0 * np.cos(2 * np.pi * min(target.isocalendar().week, 52) / 52)
    assert out['target_week'] == (levels.index[-1] + pd.Timedelta(weeks=1)).date().isoformat()
    assert out['change_mb'] == pytest.approx(expected, abs=0.25)
    assert out['backtest']['mae_mb'] < out['backtest']['naive_mae_mb']
    assert out['low_mb'] <= out['change_mb'] <= out['high_mb']


def test_ridge_beats_no_change_on_noisy_pattern():
    out = InventoryForecaster().forecast(seasonal_levels(noise=1.0), CUSHING_SPEC)
    assert out['method'] == 'ridge'
    assert out['backtest']['mae_mb'] < out['backtest']['naive_mae_mb']
    assert 0.6 <= out['backtest']['band_coverage'] <= 0.95


@pytest.mark.parametrize('spec', [US_SPEC, CUSHING_SPEC])
def test_no_lookahead_past_forecasts_ignore_later_data(spec):
    levels = seasonal_levels(noise=1.0, seed=3)
    cut = levels.iloc[:-30]
    shocked = levels.copy()
    shocked.iloc[-30:] += 500.0  # wild future data must not change a forecast made before it
    a = InventoryForecaster().forecast(cut, spec)
    b = InventoryForecaster().forecast(shocked.iloc[:-29], spec)
    assert a['change_mb'] == pytest.approx(b['last_week']['forecast_mb'], abs=0.01)


def test_rejects_short_history_and_unknown_method():
    with pytest.raises(ValueError):
        InventoryForecaster().forecast(seasonal_levels().iloc[:100], US_SPEC)
    with pytest.raises(ValueError):
        InventoryForecaster().forecast(seasonal_levels(), SeriesSpec('x', 'magic', 1.0))


def test_outlook_sums_four_reports():
    out = InventoryForecaster().outlook(seasonal_levels())
    assert out['weeks'] == 4
    assert out['low_mb'] <= out['change_mb'] <= out['high_mb']


def to_series_dict(levels):
    return {'mb': float(levels.iloc[-1]), '_full_history': [{'date': d.date().isoformat(), 'mb': float(v)} for d, v in levels.items()]}


def test_build_forecast_and_spoken_sentence():
    fc = build_forecast({'us_crude': to_series_dict(seasonal_levels(1.0, 1)), 'cushing': to_series_dict(seasonal_levels(0.3, 2) / 10)})
    assert fc['status'] == 'live' and fc['us_crude']['target_week'] == fc['cushing']['target_week']
    text = forecast_sentence(fc)
    assert 'US crude' in text and 'Cushing' in text and fc['us_crude']['target_week'] in text
    assert forecast_sentence({'status': 'unavailable'}) == ''

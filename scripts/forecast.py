"""Next-report forecasts for weekly EIA crude stock changes.

Chosen by a walk-forward study (2010 onward, yearly refits, weeks never seen in training):
- US commercial crude: 10-year seasonal average of the same week (+-1 week). Ridge and
  gradient-boosting models on fundamentals did not beat it reliably, so the simple rule is used.
- Cushing: ridge regression on 5- and 10-year seasonal averages, the stock gap versus the
  5-year norm, and the last 4 weeks' average change. It beat every simple rule in both halves.

Every number shown is backed by this module's own walk-forward backtest, recomputed on each run.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

WEEKS_PER_YEAR = 52
SEASON_WINDOW_WEEKS = 1
MIN_SEASON_SAMPLES = 3
TEST_START_YEAR = 2010
MIN_TRAIN_ROWS = 200
BAND_WEEKS = 156  # residuals from the last ~3 years set the 80% range
BAND_LOW, BAND_HIGH = 0.10, 0.90
RIDGE_ALPHA = 10.0
RIDGE_FEATURES = ("seas5", "seas10", "gap", "mean4")


@dataclass(frozen=True)
class SeriesSpec:
    key: str
    method: str  # "seasonal" or "ridge"
    direction_threshold_mb: float  # backtest direction hit-rate counts only moves at least this big


class InventoryForecaster:
    """Forecasts the next weekly change from a weekly stock-level series (million barrels)."""

    def __init__(self, test_start_year: int = TEST_START_YEAR, band_weeks: int = BAND_WEEKS,
                 ridge_alpha: float = RIDGE_ALPHA):
        self.test_start_year = test_start_year
        self.band_weeks = band_weeks
        self.ridge_alpha = ridge_alpha

    # ---------- public ----------
    def forecast(self, levels: pd.Series, spec: SeriesSpec) -> dict:
        levels = self._clean(levels)
        frame = self._features(levels)
        if spec.method == "seasonal":
            predictions = frame["seas10"]
        elif spec.method == "ridge":
            predictions = self._ridge_walk_forward(frame)
        else:
            raise ValueError(f"unknown method {spec.method}")
        target = frame.index[-1]
        point = predictions.iloc[-1]
        if not np.isfinite(point):
            raise ValueError(f"{spec.key}: not enough history to forecast")
        backtest = self._backtest(frame["y"], predictions, spec.direction_threshold_mb)
        low, high = point + backtest.pop("band_low"), point + backtest.pop("band_high")
        latest = frame.index[-2]
        last_pred = predictions.iloc[-2]
        return {
            "target_week": target.date().isoformat(),
            "change_mb": round(float(point), 2),
            "low_mb": round(float(low), 2),
            "high_mb": round(float(high), 2),
            "method": spec.method,
            "backtest": backtest,
            "last_week": {
                "week": latest.date().isoformat(),
                "forecast_mb": round(float(last_pred), 2) if np.isfinite(last_pred) else None,
                "actual_mb": round(float(frame["y"].iloc[-2]), 2),
            },
        }

    def outlook(self, levels: pd.Series, weeks: int = 4) -> dict:
        """Cumulative seasonal (10-year) change over the next `weeks` reports."""
        levels = self._clean(levels)
        future = [levels.index[-1] + pd.Timedelta(weeks=i) for i in range(1, weeks + 1)]
        change = levels.diff()
        seas = self._seasonal(change, pd.DatetimeIndex(future), 10)
        if seas.isna().any():
            raise ValueError("not enough history for the outlook")
        point = float(seas.sum())
        hist_seas = self._seasonal(change, change.index, 10)
        actual = change.rolling(weeks).sum()
        expected = hist_seas.rolling(weeks).sum()
        resid = (actual - expected)[change.index.year >= self.test_start_year].dropna()
        recent = resid.iloc[-self.band_weeks:]
        return {
            "weeks": weeks,
            "through_week": future[-1].date().isoformat(),
            "change_mb": round(point, 2),
            "low_mb": round(point + float(recent.quantile(BAND_LOW)), 2),
            "high_mb": round(point + float(recent.quantile(BAND_HIGH)), 2),
            "mae_mb": round(float(resid.abs().mean()), 2),
            "naive_mae_mb": round(float(actual[resid.index].abs().mean()), 2),
        }

    # ---------- internals ----------
    @staticmethod
    def _clean(levels: pd.Series) -> pd.Series:
        levels = levels.dropna().sort_index()
        levels = levels[~levels.index.duplicated(keep="last")]
        if len(levels) < 3 * WEEKS_PER_YEAR:
            raise ValueError("need at least three years of weekly history")
        return levels

    @staticmethod
    def _week(index: pd.DatetimeIndex) -> np.ndarray:
        return np.minimum(index.isocalendar().week.to_numpy(dtype=int), WEEKS_PER_YEAR)

    def _table(self, values: pd.Series):
        """Per (year, week-of-year) sums and counts, for fast seasonal look-ups."""
        values = values.dropna()
        years = values.index.year.to_numpy()
        first = int(years.min())
        sums = np.zeros((int(years.max()) - first + 2, WEEKS_PER_YEAR + 1))
        counts = np.zeros_like(sums)
        np.add.at(sums, (years - first, self._week(values.index)), values.to_numpy())
        np.add.at(counts, (years - first, self._week(values.index)), 1)
        return first, sums, counts

    def _seasonal(self, values: pd.Series, dates: pd.DatetimeIndex, years: int) -> pd.Series:
        """Mean of `values` in the same week (+-1) over the `years` calendar years before each date."""
        first, sums, counts = self._table(values)
        out = np.full(len(dates), np.nan)
        weeks = self._week(dates)
        for i, (year, week) in enumerate(zip(dates.year, weeks)):
            lo, hi = max(year - years - first, 0), min(year - first, sums.shape[0])
            if hi <= lo:
                continue
            cols = [((week - 1 + d) % WEEKS_PER_YEAR) + 1 for d in range(-SEASON_WINDOW_WEEKS, SEASON_WINDOW_WEEKS + 1)]
            n = counts[lo:hi, cols].sum()
            if n >= MIN_SEASON_SAMPLES:
                out[i] = sums[lo:hi, cols].sum() / n
        return pd.Series(out, index=dates)

    def _features(self, levels: pd.Series) -> pd.DataFrame:
        """One row per report week plus the next (unknown) week; features use only earlier data."""
        index = levels.index.append(pd.DatetimeIndex([levels.index[-1] + pd.Timedelta(weeks=1)]))
        change = levels.diff().reindex(index)
        frame = pd.DataFrame(index=index)
        frame["y"] = change
        frame["seas5"] = self._seasonal(change, index, 5)
        frame["seas10"] = self._seasonal(change, index, 10)
        gap = levels - self._seasonal(levels, levels.index, 5)
        frame["gap"] = gap.reindex(index).shift(1)
        frame["mean4"] = change.shift(1).rolling(4).mean()
        return frame

    def _ridge_walk_forward(self, frame: pd.DataFrame) -> pd.Series:
        cols = list(RIDGE_FEATURES)
        pred = pd.Series(np.nan, index=frame.index)
        last_year = frame.index[-1].year
        for year in range(self.test_start_year, last_year + 1):
            train = frame[frame.index.year < year].dropna(subset=cols + ["y"])
            test = frame[frame.index.year == year].dropna(subset=cols)
            if len(train) < MIN_TRAIN_ROWS or test.empty:
                continue
            x = train[cols].to_numpy()
            mean, std = x.mean(axis=0), x.std(axis=0)
            std[std == 0] = 1.0
            z = (x - mean) / std
            y = train["y"].to_numpy()
            beta = np.linalg.solve(z.T @ z + self.ridge_alpha * np.eye(len(cols)), z.T @ (y - y.mean()))
            pred[test.index] = ((test[cols].to_numpy() - mean) / std) @ beta + y.mean()
        return pred

    def _backtest(self, actual: pd.Series, predicted: pd.Series, threshold: float) -> dict:
        ok = actual.notna() & predicted.notna() & (actual.index.year >= self.test_start_year)
        y, p = actual[ok], predicted[ok]
        if len(y) < MIN_TRAIN_ROWS:
            raise ValueError("backtest too short")
        resid = y - p
        big = y.abs() >= threshold
        recent = resid.iloc[-self.band_weeks:]
        # Out-of-sample check: each week's band comes only from residuals before it.
        rolling = resid.shift(1).rolling(self.band_weeks, min_periods=WEEKS_PER_YEAR * 2)
        lo, hi = rolling.quantile(BAND_LOW), rolling.quantile(BAND_HIGH)
        has_band = lo.notna()
        coverage = ((resid >= lo) & (resid <= hi))[has_band].mean()
        return {
            "from": y.index[0].date().isoformat(),
            "to": y.index[-1].date().isoformat(),
            "weeks": int(len(y)),
            "mae_mb": round(float(resid.abs().mean()), 2),
            "naive_mae_mb": round(float(y.abs().mean()), 2),
            "direction_hit": round(float((np.sign(y[big]) == np.sign(p[big])).mean()), 3),
            "direction_min_move_mb": threshold,
            "band_coverage": round(float(coverage), 3),
            "band_low": float(recent.quantile(BAND_LOW)),
            "band_high": float(recent.quantile(BAND_HIGH)),
        }


US_SPEC = SeriesSpec("us_crude", "seasonal", 1.0)
CUSHING_SPEC = SeriesSpec("cushing", "ridge", 1.0)

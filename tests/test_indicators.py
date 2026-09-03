import numpy as np
import pandas as pd

from src.trading import indicators as ind
from src.trading import trend_template as tt


def _synthetic_uptrend_df(days=300, start=50.0, daily_drift=0.003, seed=42):
    rng = np.random.default_rng(seed)
    closes = [start]
    for _ in range(days - 1):
        closes.append(closes[-1] * (1 + daily_drift + rng.normal(0, 0.01)))
    closes = np.array(closes)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="B")
    df = pd.DataFrame(
        {
            "Open": closes * 0.99,
            "High": closes * 1.01,
            "Low": closes * 0.98,
            "Close": closes,
            "Volume": rng.integers(1_000_000, 5_000_000, size=days),
        },
        index=dates,
    )
    return df


def test_sma_returns_none_on_short_history():
    df = _synthetic_uptrend_df(days=10)
    assert ind.sma(df, 200) is None


def test_sma_computes_on_sufficient_history():
    df = _synthetic_uptrend_df(days=300)
    s = ind.sma(df, 50)
    assert s is not None
    assert not s.dropna().empty


def test_pct_above_52wk_low_positive_for_uptrend():
    df = _synthetic_uptrend_df(days=300)
    pct = ind.pct_above_52wk_low(df)
    assert pct is not None
    assert pct > 0


def test_trend_template_evaluate_all_shape():
    df = _synthetic_uptrend_df(days=300)
    result = tt.evaluate_all(df, rs_value=80)
    assert set(result["results"].keys()) == set(tt.CHECK_NAMES)
    assert 0 <= result["match_pct"] <= 100


def test_pivot_breakout_degrades_gracefully_on_short_history():
    df = _synthetic_uptrend_df(days=20)
    result = ind.find_pivot_breakout(df)
    assert result["pivot_price"] is None
    assert result["breakout"] is None

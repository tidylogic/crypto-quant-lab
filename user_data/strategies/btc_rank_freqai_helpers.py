from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional, Sequence


BASE_FEATURE_COLUMNS = [
    "%-rank-ma3-distance",
    "%-rank-ma7-distance",
    "%-rank-ma25-distance",
    "%-rank-ma50-distance",
    "%-rank-rsi",
    "%-rank-volatility",
    "%-rank-volume-ratio",
    "%-rank-bullish-ob",
    "%-rank-bullish-fvg",
    "%-rank-bearish-ob",
    "%-rank-bearish-fvg",
    "%-rank-y1-range-pos",
    "%-rank-y1-return",
]

MTF_PREFIXES = ["m1", "m5", "h1", "d1"]
MTF_FEATURE_NAMES = [
    "ret-1",
    "ret-3",
    "rsi",
    "volatility",
    "volume-ratio",
    "trend-fast",
    "trend-slow",
    "dist-fast-ma",
    "dist-slow-ma",
]
MTF_FEATURE_COLUMNS = [
    f"%-rank-{prefix}-{name}"
    for prefix in MTF_PREFIXES
    for name in MTF_FEATURE_NAMES
]

V3_FEATURE_COLUMNS = [
    "%-rank-v3-ret-1",
    "%-rank-v3-ret-2",
    "%-rank-v3-ret-3",
    "%-rank-v3-ret-6",
    "%-rank-v3-ret-12",
    "%-rank-v3-ret-24",
    "%-rank-v3-body-pct",
    "%-rank-v3-range-pct",
    "%-rank-v3-upper-wick-pct",
    "%-rank-v3-lower-wick-pct",
    "%-rank-v3-close-pos",
    "%-rank-v3-body-to-range",
    "%-rank-v3-volume-ratio-20",
    "%-rank-v3-volume-ratio-60",
    "%-rank-v3-range-ratio-20",
    "%-rank-v3-range-ratio-60",
    "%-rank-v3-breakout-pos-12",
    "%-rank-v3-breakout-pos-48",
    "%-rank-v3-breakout-pos-144",
    "%-rank-v3-dist-ma7",
    "%-rank-v3-dist-ma25",
    "%-rank-v3-dist-ma50",
    "%-rank-v3-ma7-slope",
    "%-rank-v3-ma25-slope",
    "%-rank-v3-ma50-slope",
    "%-rank-v3-pullback-long",
    "%-rank-v3-pullback-short",
    "%-rank-v3-trend-alignment-long",
    "%-rank-v3-trend-alignment-short",
    "%-rank-v3-hour-sin",
    "%-rank-v3-hour-cos",
    "%-rank-v3-asia-active",
    "%-rank-v3-us-active",
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def row_value(row: Any, *names: str, default: float = 0.0) -> float:
    for name in names:
        try:
            raw = row.get(name) if hasattr(row, "get") else row[name]
        except Exception:
            continue
        value = _finite_float(raw, default=math.nan)
        if not math.isnan(value):
            return value
    return default


def create_scalping_targets_from_ohlc(
    close: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    take_profit_pct: float,
    stop_loss_pct: float,
    window: int,
) -> tuple[list[Optional[int]], list[Optional[int]]]:
    long_targets: list[Optional[int]] = [None] * len(close)
    short_targets: list[Optional[int]] = [None] * len(close)

    for i in range(max(0, len(close) - window)):
        entry = _finite_float(close[i])
        if entry <= 0:
            long_targets[i] = 0
            short_targets[i] = 0
            continue

        long_label = 0
        short_label = 0

        for j in range(i + 1, i + 1 + window):
            future_high = _finite_float(high[j])
            future_low = _finite_float(low[j])
            if future_low <= entry * (1 - stop_loss_pct):
                break
            if future_high >= entry * (1 + take_profit_pct):
                long_label = 1
                break

        for j in range(i + 1, i + 1 + window):
            future_high = _finite_float(high[j])
            future_low = _finite_float(low[j])
            if future_high >= entry * (1 + stop_loss_pct):
                break
            if future_low <= entry * (1 - take_profit_pct):
                short_label = 1
                break

        long_targets[i] = long_label
        short_targets[i] = short_label

    return long_targets, short_targets


def combine_scalping_targets(
    long_targets: Sequence[Optional[int]],
    short_targets: Sequence[Optional[int]],
) -> list[Optional[float]]:
    combined: list[Optional[float]] = []
    for long_value, short_value in zip(long_targets, short_targets):
        if long_value is None or short_value is None:
            combined.append(None)
            continue
        combined.append(float(long_value) - float(short_value))
    return combined


def rolling_percentile_rank_values(
    values: Sequence[float],
    window: int,
    min_periods: int,
) -> list[float]:
    ranks: list[float] = []
    for idx, raw_value in enumerate(values):
        value = _finite_float(raw_value)
        start = max(0, idx - window + 1)
        distribution = [
            _finite_float(item)
            for item in values[start : idx + 1]
            if not math.isnan(_finite_float(item, default=math.nan))
        ]
        if len(distribution) < min_periods:
            ranks.append(0.0)
            continue
        ranks.append(sum(item <= value for item in distribution) / len(distribution))
    return ranks


@dataclass(frozen=True)
class DecisionConfig:
    min_rank: float = 0.78
    min_edge_rank: float = 0.03
    min_raw_prob: float = 0.02
    min_score: float = 0.61
    min_expected_value: float = 0.00030
    long_min_rank: float = 0.84
    long_min_score: float = 0.62
    long_min_expected_value: float = 0.00035
    long_min_trend: float = -0.00400
    take_profit_pct: float = 0.0055
    stop_loss_pct: float = 0.0045
    taker_fee_rate: float = 0.0004
    slippage_rate: float = 0.0002


@dataclass(frozen=True)
class DecisionResult:
    signal: str
    reason: str
    score: float
    expected_value: float
    effective_win_prob: float
    confidence: float
    edge_rank: float
    regime: str
    side_rank: float
    other_rank: float


def classify_regime(row: Any) -> tuple[str, float]:
    vol = row_value(row, "%-rank-volatility", "volatility")
    m5_vol = row_value(row, "%-rank-m5-volatility", "m5_volatility", default=vol)
    m5_trend = row_value(row, "%-rank-m5-trend-fast", "m5_trend_fast")
    h1_trend = row_value(row, "%-rank-h1-trend-fast", "h1_trend_fast")
    volume_ratio = row_value(row, "%-rank-m5-volume-ratio", "m5_volume_ratio", default=1.0)

    if max(vol, m5_vol) >= 0.006:
        return "shock", 0.82
    if abs(h1_trend) >= 0.003 or abs(m5_trend) >= 0.002:
        return "trend", 1.00
    if max(vol, m5_vol) < 0.0007 and volume_ratio < 0.85:
        return "dead_range", 0.72
    if max(vol, m5_vol) < 0.0011:
        return "quiet_range", 0.86
    return "normal", 0.95


def side_trend_strength(row: Any, side: str) -> float:
    m5_trend = row_value(
        row,
        "%-rank-m5-trend-fast",
        "%-rank-v3-ma25-slope",
        "m5_trend_fast",
    )
    h1_trend = row_value(
        row,
        "%-rank-h1-trend-fast",
        "%-rank-v3-ma50-slope",
        "h1_trend_fast",
    )
    signed = (m5_trend * 0.6) + (h1_trend * 0.4)
    return -signed if side == "short" else signed


def side_trend_bonus(row: Any, side: str) -> float:
    return clamp(side_trend_strength(row, side) * 35.0, -0.06, 0.06)


def effective_probability(
    side_rank: float,
    edge_rank: float,
    raw_prob: float,
    row: Any,
    side: str,
) -> float:
    raw_component = clamp(raw_prob, 0.0, 0.80) * 0.08
    rank_component = (side_rank - 0.5) * 0.42
    edge_component = edge_rank * 0.16
    trend_component = side_trend_bonus(row, side)
    return clamp(
        0.50 + rank_component + edge_component + raw_component + trend_component,
        0.05,
        0.95,
    )


def expected_value(win_prob: float, config: DecisionConfig) -> float:
    roundtrip_cost = (2.0 * config.taker_fee_rate) + (2.0 * config.slippage_rate)
    reward = max(0.0, config.take_profit_pct - roundtrip_cost)
    risk = config.stop_loss_pct + roundtrip_cost
    return (win_prob * reward) - ((1.0 - win_prob) * risk)


def decide_rank_signal(
    row: Any,
    long_prob: float,
    short_prob: float,
    long_rank: float,
    short_rank: float,
    config: Optional[DecisionConfig] = None,
) -> DecisionResult:
    config = config or DecisionConfig()
    side = "long" if long_rank >= short_rank else "short"
    side_rank = max(long_rank, short_rank)
    other_rank = min(long_rank, short_rank)
    edge_rank = side_rank - other_rank
    side_prob = long_prob if side == "long" else short_prob
    regime, regime_score = classify_regime(row)
    win_prob = effective_probability(side_rank, edge_rank, side_prob, row, side)
    ev = expected_value(win_prob, config)
    score = clamp(
        (side_rank * 0.48)
        + (edge_rank * 0.20)
        + (win_prob * 0.20)
        + (regime_score * 0.08)
        + (clamp(ev, -0.001, 0.003) * 13.0),
        0.0,
        1.0,
    )

    def result(signal: str, reason: str) -> DecisionResult:
        return DecisionResult(
            signal=signal,
            reason=reason,
            score=score,
            expected_value=ev,
            effective_win_prob=win_prob,
            confidence=side_rank,
            edge_rank=edge_rank,
            regime=regime,
            side_rank=side_rank,
            other_rank=other_rank,
        )

    if side_prob < config.min_raw_prob:
        return result("none", "raw_probability_too_low")
    if side == "long" and side_trend_strength(row, side) < config.long_min_trend:
        return result("none", "long_trend_not_supported")
    if side_rank < config.min_rank:
        return result("none", "rank_below_min")
    if side == "long" and side_rank < config.long_min_rank:
        return result("none", "long_rank_below_min")
    if edge_rank < config.min_edge_rank:
        return result("none", "edge_below_min")
    if ev < config.min_expected_value:
        return result("none", "expected_value_below_min")
    if side == "long" and ev < config.long_min_expected_value:
        return result("none", "long_expected_value_below_min")
    if score < config.min_score:
        return result("none", "score_below_min")
    if side == "long" and score < config.long_min_score:
        return result("none", "long_score_below_min")

    return result(side, "rank_entry_candidate")


def _rsi(close: Any, period: int = 14) -> Any:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period, min_periods=max(2, period // 2)).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period, min_periods=max(2, period // 2)).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def add_period_features(dataframe: Any, period: int) -> Any:
    out = dataframe.copy()
    close = out["close"]
    high = out["high"]
    low = out["low"]
    volume = out["volume"]

    out[f"%-rank-ret-{period}"] = close.pct_change(period)
    out[f"%-rank-rsi-{period}"] = _rsi(close, period)
    out[f"%-rank-volatility-{period}"] = (high - low).rolling(period).mean() / close
    out[f"%-rank-volume-ratio-{period}"] = volume / volume.rolling(period).mean().replace(0, 1e-9)
    return out


def add_rank_features(dataframe: Any) -> Any:
    import pandas as pd

    out = dataframe.copy()
    open_ = pd.to_numeric(out["open"], errors="coerce")
    high = pd.to_numeric(out["high"], errors="coerce")
    low = pd.to_numeric(out["low"], errors="coerce")
    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce")

    for period in [3, 7, 25, 50]:
        ma = close.rolling(period, min_periods=max(2, period // 3)).mean()
        out[f"%-rank-ma{period}-distance"] = (close / ma.replace(0, math.nan)) - 1.0

    out["%-rank-rsi"] = _rsi(close, 14)
    out["%-rank-volatility"] = (high - low) / open_.replace(0, math.nan)
    out["%-rank-volume-ratio"] = volume / volume.rolling(48, min_periods=12).mean().replace(0, 1e-9)

    is_green = close > open_
    is_red = close < open_
    out["%-rank-bullish-ob"] = (
        is_red.shift(1) & is_green & (close > open_.shift(1)) & (open_ < close.shift(1))
    ).astype(float)
    out["%-rank-bullish-fvg"] = (high.shift(2) < low).astype(float)
    out["%-rank-bearish-ob"] = (
        is_green.shift(1) & is_red & (close < open_.shift(1)) & (open_ > close.shift(1))
    ).astype(float)
    out["%-rank-bearish-fvg"] = (low.shift(2) > high).astype(float)

    yearly_window = min(35040, max(120, len(out) // 2))
    min_periods = min(100, max(20, yearly_window // 4))
    rolling_high = high.rolling(yearly_window, min_periods=min_periods).max()
    rolling_low = low.rolling(yearly_window, min_periods=min_periods).min()
    out["%-rank-y1-range-pos"] = (close - rolling_low) / (rolling_high - rolling_low).replace(0, 1e-9)
    out["%-rank-y1-return"] = close.pct_change(yearly_window).fillna(close.pct_change(96))

    for period in [1, 2, 3, 6, 12, 24]:
        out[f"%-rank-v3-ret-{period}"] = close.pct_change(period)

    candle_range = (high - low).abs()
    body = close - open_
    out["%-rank-v3-body-pct"] = body / open_.replace(0, math.nan)
    out["%-rank-v3-range-pct"] = candle_range / open_.replace(0, math.nan)
    out["%-rank-v3-upper-wick-pct"] = (high - pd.concat([open_, close], axis=1).max(axis=1)) / open_.replace(0, math.nan)
    out["%-rank-v3-lower-wick-pct"] = (pd.concat([open_, close], axis=1).min(axis=1) - low) / open_.replace(0, math.nan)
    out["%-rank-v3-close-pos"] = ((close - low) / (high - low).replace(0, math.nan)).clip(0.0, 1.0)
    out["%-rank-v3-body-to-range"] = (body.abs() / candle_range.replace(0, math.nan)).clip(0.0, 1.0)
    out["%-rank-v3-volume-ratio-20"] = volume / volume.rolling(20, min_periods=5).mean().replace(0, 1e-9)
    out["%-rank-v3-volume-ratio-60"] = volume / volume.rolling(60, min_periods=10).mean().replace(0, 1e-9)
    out["%-rank-v3-range-ratio-20"] = out["%-rank-v3-range-pct"] / out["%-rank-v3-range-pct"].rolling(20, min_periods=5).mean().replace(0, 1e-9)
    out["%-rank-v3-range-ratio-60"] = out["%-rank-v3-range-pct"] / out["%-rank-v3-range-pct"].rolling(60, min_periods=10).mean().replace(0, 1e-9)

    for period in [12, 48, 144]:
        period_high = high.rolling(period, min_periods=max(4, period // 4)).max()
        period_low = low.rolling(period, min_periods=max(4, period // 4)).min()
        out[f"%-rank-v3-breakout-pos-{period}"] = ((close - period_low) / (period_high - period_low).replace(0, 1e-9)).clip(0.0, 1.0)

    for period in [7, 25, 50]:
        ma = close.rolling(period, min_periods=max(3, period // 3)).mean()
        out[f"%-rank-v3-dist-ma{period}"] = (close / ma.replace(0, math.nan)) - 1.0
        out[f"%-rank-v3-ma{period}-slope"] = ma.pct_change(3)

    out["%-rank-v3-pullback-long"] = (
        (out["%-rank-v3-ma25-slope"] > 0).astype(float)
        * (out["%-rank-v3-dist-ma25"] < 0).astype(float)
        * (out["%-rank-v3-close-pos"] > 0.45).astype(float)
    )
    out["%-rank-v3-pullback-short"] = (
        (out["%-rank-v3-ma25-slope"] < 0).astype(float)
        * (out["%-rank-v3-dist-ma25"] > 0).astype(float)
        * (out["%-rank-v3-close-pos"] < 0.55).astype(float)
    )
    out["%-rank-v3-trend-alignment-long"] = (out["%-rank-v3-ma25-slope"] > 0).astype(float)
    out["%-rank-v3-trend-alignment-short"] = (out["%-rank-v3-ma25-slope"] < 0).astype(float)

    date_column = "date" if "date" in out.columns else "timestamp"
    timestamp = pd.to_datetime(out[date_column], errors="coerce") if date_column in out.columns else None
    if timestamp is not None:
        hour = timestamp.dt.hour.fillna(0).astype(float)
    else:
        hour = pd.Series(0.0, index=out.index)
    out["%-rank-v3-hour-sin"] = (2 * math.pi * hour / 24.0).map(math.sin)
    out["%-rank-v3-hour-cos"] = (2 * math.pi * hour / 24.0).map(math.cos)
    out["%-rank-v3-asia-active"] = hour.between(9, 14).astype(float)
    out["%-rank-v3-us-active"] = ((hour >= 21) | (hour <= 2)).astype(float)

    feature_columns = BASE_FEATURE_COLUMNS + V3_FEATURE_COLUMNS
    out[feature_columns] = out[feature_columns].replace([math.inf, -math.inf], math.nan).ffill().fillna(0.0)
    return out


def create_scalping_targets(
    dataframe: Any,
    take_profit_pct: float,
    stop_loss_pct: float,
    window: int,
) -> Any:
    import pandas as pd

    long_values, short_values = create_scalping_targets_from_ohlc(
        close=list(dataframe["close"]),
        high=list(dataframe["high"]),
        low=list(dataframe["low"]),
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        window=window,
    )
    signal_values = combine_scalping_targets(long_values, short_values)
    return pd.Series(signal_values, index=dataframe.index)


def rolling_percentile_rank(series: Any, window: int, min_periods: int) -> Any:
    import pandas as pd

    return pd.Series(
        rolling_percentile_rank_values(list(series), window=window, min_periods=min_periods),
        index=series.index,
    )

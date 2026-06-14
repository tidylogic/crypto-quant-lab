from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import IStrategy

try:
    from user_data.strategies.btc_rank_freqai_helpers import (
        DecisionConfig,
        create_scalping_targets,
        decide_rank_signal,
        add_period_features,
        add_rank_features,
        rolling_percentile_rank,
    )
except ModuleNotFoundError:
    from btc_rank_freqai_helpers import (
        DecisionConfig,
        create_scalping_targets,
        decide_rank_signal,
        add_period_features,
        add_rank_features,
        rolling_percentile_rank,
    )


SIGNAL_TARGET = "&-rank-signal-score"


class BtcRankFreqaiStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 240
    rank_decision = DecisionConfig()

    minimal_roi = {
        "0": rank_decision.take_profit_pct,
    }
    stoploss = -rank_decision.stop_loss_pct
    use_exit_signal = True

    rank_window = 720
    rank_min_periods = 120

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)
        return self._add_decision_columns(dataframe)

    def feature_engineering_expand_all(
        self,
        dataframe: DataFrame,
        period: int,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        return add_period_features(dataframe, period)

    def feature_engineering_expand_basic(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        return add_rank_features(dataframe)

    def feature_engineering_standard(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        dataframe["%-rank-day-of-week"] = (dataframe["date"].dt.dayofweek + 1) / 7
        dataframe["%-rank-hour-of-day"] = (dataframe["date"].dt.hour + 1) / 24
        return dataframe

    def set_freqai_targets(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        label_period = int(
            self.freqai_info.get("feature_parameters", {}).get("label_period_candles", 8)
        )
        signal_target = create_scalping_targets(
            dataframe,
            take_profit_pct=self.rank_decision.take_profit_pct,
            stop_loss_pct=self.rank_decision.stop_loss_pct,
            window=label_period,
        )
        dataframe[SIGNAL_TARGET] = signal_target
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_conditions = (
            (dataframe["do_predict"] == 1)
            & (dataframe["rank_signal"] == "long")
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = (
            1,
            "btc_rank_freqai_long",
        )

        if self.can_short:
            short_conditions = (
                (dataframe["do_predict"] == 1)
                & (dataframe["rank_signal"] == "short")
                & (dataframe["volume"] > 0)
            )
            dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = (
                1,
                "btc_rank_freqai_short",
            )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_long = (
            (dataframe["do_predict"] == 1)
            & (
                (dataframe["rank_short_rank"] > dataframe["rank_long_rank"] + 0.03)
                | (dataframe["rank_signal_score"] < 0)
            )
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = (
            1,
            "btc_rank_freqai_short_pressure",
        )

        if self.can_short:
            exit_short = (
                (dataframe["do_predict"] == 1)
                & (
                    (dataframe["rank_long_rank"] > dataframe["rank_short_rank"] + 0.03)
                    | (dataframe["rank_signal_score"] > 0)
                )
                & (dataframe["volume"] > 0)
            )
            dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = (
                1,
                "btc_rank_freqai_long_pressure",
            )

        return dataframe

    def _add_decision_columns(self, dataframe: DataFrame) -> DataFrame:
        if SIGNAL_TARGET not in dataframe.columns:
            dataframe[SIGNAL_TARGET] = 0.0

        dataframe["rank_signal_score"] = dataframe[SIGNAL_TARGET].astype(float).fillna(0.0)
        dataframe["rank_long_prob"] = dataframe["rank_signal_score"].clip(lower=0.0, upper=1.0)
        dataframe["rank_short_prob"] = (-dataframe["rank_signal_score"]).clip(lower=0.0, upper=1.0)
        dataframe["rank_long_rank"] = rolling_percentile_rank(
            dataframe["rank_long_prob"],
            window=self.rank_window,
            min_periods=self.rank_min_periods,
        )
        dataframe["rank_short_rank"] = rolling_percentile_rank(
            dataframe["rank_short_prob"],
            window=self.rank_window,
            min_periods=self.rank_min_periods,
        )

        signals: list[str] = []
        reasons: list[str] = []
        scores: list[float] = []
        expected_values: list[float] = []
        confidences: list[float] = []
        regimes: list[str] = []

        for _, row in dataframe.iterrows():
            if row.get("do_predict", 0) != 1:
                signals.append("none")
                reasons.append("do_predict_not_ready")
                scores.append(0.0)
                expected_values.append(0.0)
                confidences.append(0.0)
                regimes.append("unknown")
                continue

            decision = decide_rank_signal(
                row,
                long_prob=float(row["rank_long_prob"]),
                short_prob=float(row["rank_short_prob"]),
                long_rank=float(row["rank_long_rank"]),
                short_rank=float(row["rank_short_rank"]),
                config=self.rank_decision,
            )
            signals.append(decision.signal)
            reasons.append(decision.reason)
            scores.append(decision.score)
            expected_values.append(decision.expected_value)
            confidences.append(decision.confidence)
            regimes.append(decision.regime)

        dataframe["rank_signal"] = signals
        dataframe["rank_reason"] = reasons
        dataframe["rank_score"] = scores
        dataframe["rank_expected_value"] = expected_values
        dataframe["rank_confidence"] = confidences
        dataframe["rank_regime"] = regimes
        return dataframe

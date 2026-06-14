from __future__ import annotations

from datetime import datetime

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy

try:
    from user_data.strategies.btc_rank_freqai_helpers import (
        DecisionConfig,
        DecisionResult,
        LocalTradeGateConfig,
        create_scalping_targets,
        decide_rank_signal,
        dynamic_leverage,
        evaluate_local_trade_gate,
        add_period_features,
        add_rank_features,
        position_fraction,
        rolling_percentile_rank,
    )
except ModuleNotFoundError:
    from btc_rank_freqai_helpers import (
        DecisionConfig,
        DecisionResult,
        LocalTradeGateConfig,
        create_scalping_targets,
        decide_rank_signal,
        dynamic_leverage,
        evaluate_local_trade_gate,
        add_period_features,
        add_rank_features,
        position_fraction,
        rolling_percentile_rank,
    )


SIGNAL_TARGET = "&-rank-signal-score"


class BtcRankFreqaiStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 720
    rank_decision = DecisionConfig()
    rank_trade_gate = LocalTradeGateConfig()

    minimal_roi = {
        "0": rank_decision.take_profit_pct,
    }
    stoploss = -rank_decision.stop_loss_pct
    use_exit_signal = False

    rank_window = 8000
    rank_min_periods = 240
    fixed_leverage = 100.0
    min_leverage = 100.0
    max_leverage = 100.0
    position_fraction_min = 0.18
    position_fraction_max = 0.18
    trade_time_filter_enabled = True
    trade_block_hours_kst = frozenset({0, 4, 12, 13, 16, 20})
    trade_allowed_hours_kst = frozenset()

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
            & (dataframe["rank_trade_time_allow"])
            & (dataframe["rank_local_gate_allow"])
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
                & (dataframe["rank_trade_time_allow"])
                & (dataframe["rank_local_gate_allow"])
                & (dataframe["volume"] > 0)
            )
            dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = (
                1,
                "btc_rank_freqai_short",
            )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        if self.can_short:
            dataframe["exit_short"] = 0

        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        row = self._latest_analyzed_row(pair)
        if row is None:
            return proposed_stake

        fraction = float(row.get("rank_position_fraction", 0.0))
        if fraction <= 0 or max_stake <= 0:
            return proposed_stake

        stake = max_stake * fraction
        if min_stake is not None:
            stake = max(stake, min_stake)
        return min(stake, max_stake)

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        row = self._latest_analyzed_row(pair)
        if row is None:
            return proposed_leverage

        leverage = float(row.get("rank_leverage", proposed_leverage))
        return max(1.0, min(leverage, max_leverage))

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        if not self._trade_time_allowed(current_time):
            return False

        row = self._latest_analyzed_row(pair)
        if row is None:
            return True

        decision = self._decision_from_row(row)
        if decision is None or decision.signal != side:
            return False

        gate = evaluate_local_trade_gate(
            row,
            decision,
            current_price=float(rate),
            signal_price=float(row.get("close", rate)),
            config=self.rank_trade_gate,
        )
        return gate.allow

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
        local_gate_allows: list[bool] = []
        local_gate_reasons: list[str] = []
        trade_time_allows: list[bool] = []
        position_fractions: list[float] = []
        leverages: list[float] = []

        for _, row in dataframe.iterrows():
            if row.get("do_predict", 0) != 1:
                signals.append("none")
                reasons.append("do_predict_not_ready")
                scores.append(0.0)
                expected_values.append(0.0)
                confidences.append(0.0)
                regimes.append("unknown")
                local_gate_allows.append(False)
                local_gate_reasons.append("do_predict_not_ready")
                trade_time_allows.append(False)
                position_fractions.append(0.0)
                leverages.append(1.0)
                continue

            decision = decide_rank_signal(
                row,
                long_prob=float(row["rank_long_prob"]),
                short_prob=float(row["rank_short_prob"]),
                long_rank=float(row["rank_long_rank"]),
                short_rank=float(row["rank_short_rank"]),
                config=self.rank_decision,
            )
            signal = decision.signal
            reason = decision.reason

            trade_time_allow = self._trade_time_allowed(row.get("date"))
            gate = evaluate_local_trade_gate(
                row,
                decision,
                current_price=float(row.get("close", 0.0)),
                signal_price=float(row.get("close", 0.0)),
                config=self.rank_trade_gate,
            )
            if signal != "none" and not trade_time_allow:
                signal = "none"
                reason = "blocked_trading_hour"
            elif signal != "none" and not gate.allow:
                signal = "none"
                reason = gate.reason

            confidence = decision.confidence if signal != "none" else 0.0
            leverage = dynamic_leverage(
                confidence=decision.confidence,
                edge_rank=decision.edge_rank,
                min_leverage=self.min_leverage,
                max_leverage=self.max_leverage,
                fixed_leverage=self.fixed_leverage,
            ) if signal != "none" else 1.0
            fraction = position_fraction(
                confidence=decision.confidence,
                fixed_leverage=self.fixed_leverage,
                min_fraction=self.position_fraction_min,
                max_fraction=self.position_fraction_max,
            ) if signal != "none" else 0.0

            signals.append(signal)
            reasons.append(reason)
            scores.append(decision.score)
            expected_values.append(decision.expected_value)
            confidences.append(confidence)
            regimes.append(decision.regime)
            local_gate_allows.append(gate.allow)
            local_gate_reasons.append(gate.reason)
            trade_time_allows.append(trade_time_allow)
            position_fractions.append(fraction)
            leverages.append(leverage)

        dataframe["rank_signal"] = signals
        dataframe["rank_reason"] = reasons
        dataframe["rank_score"] = scores
        dataframe["rank_expected_value"] = expected_values
        dataframe["rank_confidence"] = confidences
        dataframe["rank_regime"] = regimes
        dataframe["rank_local_gate_allow"] = local_gate_allows
        dataframe["rank_local_gate_reason"] = local_gate_reasons
        dataframe["rank_trade_time_allow"] = trade_time_allows
        dataframe["rank_position_fraction"] = position_fractions
        dataframe["rank_leverage"] = leverages
        return dataframe

    def _latest_analyzed_row(self, pair: str):
        if not self.dp:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        if dataframe is None or dataframe.empty:
            return None
        return dataframe.iloc[-1].squeeze()

    def _decision_from_row(self, row) -> DecisionResult | None:
        signal = str(row.get("rank_signal", "none"))
        if signal == "none":
            return None
        confidence = float(row.get("rank_confidence", 0.0))
        long_rank = float(row.get("rank_long_rank", 0.0))
        short_rank = float(row.get("rank_short_rank", 0.0))
        side_rank = max(long_rank, short_rank)
        other_rank = min(long_rank, short_rank)
        return DecisionResult(
            signal=signal,
            reason=str(row.get("rank_reason", "")),
            score=float(row.get("rank_score", 0.0)),
            expected_value=float(row.get("rank_expected_value", 0.0)),
            effective_win_prob=0.0,
            confidence=confidence or side_rank,
            edge_rank=side_rank - other_rank,
            regime=str(row.get("rank_regime", "unknown")),
            side_rank=side_rank,
            other_rank=other_rank,
        )

    def _trade_time_allowed(self, value) -> bool:
        if not self.trade_time_filter_enabled:
            return True
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return False
        kst_hour = (timestamp + pd.Timedelta(hours=9)).hour
        if self.trade_allowed_hours_kst and kst_hour not in self.trade_allowed_hours_kst:
            return False
        return kst_hour not in self.trade_block_hours_kst

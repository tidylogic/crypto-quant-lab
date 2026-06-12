from functools import reduce

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class ScalpingFreqaiStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 200

    minimal_roi = {
        "0": 0.01
    }
    stoploss = -0.01
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def feature_engineering_expand_all(
        self,
        dataframe: DataFrame,
        period: int,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-mfi-period"] = ta.MFI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        dataframe["%-ema-period"] = ta.EMA(dataframe, timeperiod=period)
        dataframe["%-roc-period"] = ta.ROC(dataframe, timeperiod=period)
        dataframe["%-relative-volume-period"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )
        return dataframe

    def feature_engineering_expand_basic(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        dataframe["%-pct-change"] = dataframe["close"].pct_change()
        dataframe["%-raw-volume"] = dataframe["volume"]
        dataframe["%-raw-price"] = dataframe["close"]
        dataframe["%-range-ratio"] = (dataframe["high"] - dataframe["low"]) / dataframe["close"]
        return dataframe

    def feature_engineering_standard(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        dataframe["%-day-of-week"] = (dataframe["date"].dt.dayofweek + 1) / 7
        dataframe["%-hour-of-day"] = (dataframe["date"].dt.hour + 1) / 24
        return dataframe

    def set_freqai_targets(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        dataframe = dataframe.copy()
        label_period = self.freqai_info["feature_parameters"]["label_period_candles"]
        dataframe["&-future-return"] = (
            dataframe["close"].shift(-label_period).rolling(label_period).mean()
            / dataframe["close"]
            - 1
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = [
            dataframe["do_predict"] == 1,
            dataframe["&-future-return"] > 0.002,
            dataframe["volume"] > 0,
        ]

        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), ["enter_long", "enter_tag"]] = (
                1,
                "freqai_positive_return",
            )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = [
            dataframe["do_predict"] == 1,
            dataframe["&-future-return"] < 0,
            dataframe["volume"] > 0,
        ]

        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), ["exit_long", "exit_tag"]] = (
                1,
                "freqai_negative_return",
            )

        return dataframe

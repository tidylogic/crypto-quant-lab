# BTC Rank FreqAI

## Hypothesis

Standalone `btc-rank-scalper`의 핵심 가설은 5분봉 기준 짧은 시간 안에 TP가 SL보다 먼저 도달할 가능성이 높은 BTC 구간을 long/short 확률과 percentile rank로 고르는 것이다. 이 마이그레이션은 해당 가설을 FreqAI lifecycle 안에서 재학습 가능한 전략으로 옮기되, Freqtrade-native runtime 안에서 원본 decision/risk gate에 최대한 가깝게 동작시키는 것을 목표로 한다.

## Entry Logic

- FreqAI가 단일 scalar target인 `&-rank-signal-score`를 예측한다.
- 최근 예측 분포에서 rolling percentile rank를 계산한다.
- `DecisionConfig`가 raw probability, side rank, rank edge, expected value, long trend guard, score를 검사한다.
- 원본 local trade gate에 맞춰 price chase, adverse drift, low-volume weak edge, dead/quiet range weak edge, shock regime weak quality 후보를 차단한다.
- 원본 meta 모델은 포함하지 않으므로 weak-meta/shock-meta 조건은 FreqAI rank, EV, edge로 만든 safety score proxy로 근사한다.
- 원본 forward-test 설정에 맞춰 KST 00, 04, 12, 13, 16, 20시 신규 진입을 차단한다.
- 기본 설정은 spot PR 백테스트 호환성을 위해 long entry만 낸다.
- short target과 short pressure는 계산하지만, 실제 short entry는 futures 설정 전환 후 `can_short`를 켜는 별도 검증이 필요하다.

## Exit Logic

- 원본 C# runner와 더 비슷하게 모델 반대 신호만으로는 조기 청산하지 않는다.
- Static ROI는 원본 TP에 가까운 `0.55%`에서 시작한다.
- Static stoploss는 원본 SL에 가까운 `0.45%`에서 시작한다.

## Risk Controls

- Rank threshold: 낮은 예측 rank 후보를 차단한다.
- Edge threshold: long/short 간 차이가 작은 후보를 차단한다.
- Expected value threshold: 수수료와 슬리피지를 반영한 기대값이 낮은 후보를 차단한다.
- Long trend guard: 장기/중기 추세가 너무 불리한 long 후보를 차단한다.
- Local gate: 원본 runtime의 chase, adverse drift, low volume, weak range, shock regime filter를 Freqtrade dataframe/callback으로 재현한다. 원본 meta 확률은 Freqtrade-native safety score proxy로 대체한다.
- Stake callback: source default처럼 후보 confidence에 따라 stake fraction을 계산하며, 현재 기본값은 원본 forward-test 설정과 같은 18%다.
- Leverage callback: futures mode에서는 원본 default인 100x 고정 레버리지를 반환한다. Spot mode에서는 Freqtrade가 무시한다.
- PR/manual backtest helper는 BTC rank 단독 실행 시 5분봉을 기본값으로 권장한다.
- `can_short=False`가 기본값이므로 현재 spot 설정과 PR 백테스트를 깨지 않는다.

## FreqAI Features And Target

Features:

- Moving average distance: MA3, MA7, MA25, MA50.
- RSI, volatility, volume ratio.
- Bullish/bearish order-block and fair-value-gap style candle markers.
- Long-range position and long-range return.
- V3 chart-context family: short returns, wick/body shape, close position, volume/range ratios, breakout position, MA distance/slope, pullback and trend-alignment flags, hour encodings.
- FreqAI-expanded 5m, 1h, and 1d feature sets when `config.btc-rank-freqai.example.json` is applied and matching data is downloaded.

Known difference:

- The standalone bot used explicit 1m, 5m, 1h, and 1d values in its rank gate. FreqAI requires expanded include timeframes to be greater than or equal to the strategy timeframe, so this 5m strategy trains on 5m, 1h, and 1d context. The post-prediction decision gate only uses direct m5/h1 columns if FreqAI returns those names on the strategy dataframe; otherwise it falls back to migrated V3 MA slope context.

Targets:

- `&-rank-signal-score`: next `label_period_candles` window reaches long TP before long SL as `+1`, short TP before short SL as `-1`, otherwise `0`.
- Strategy timeframe and `config.btc-rank-freqai.example.json` use `5m`.
- `config.btc-rank-freqai.example.json` uses `label_period_candles=8`, matching the source bot's default target window of about 40 minutes on 5m candles.

## Backtest Evidence

Not yet run in this migration pass. Backtesting should be done through PR automation or a separate explicit run, then reviewed with trade count, drawdown, fees, slippage, and fill assumptions.

## Dry-Run Observations

Not yet observed. Before live capital, run dry-run and inspect signal frequency, exit timing, rejected candidates, order fill behavior, and whether long-only behavior is acceptable.

## Decision

Proceed as a FreqAI-native runtime approximation, not as direct model-file inference. This means exact source predictions and C# runner fills will differ, but the signal horizon, entry gate, position sizing intent, leverage callback, and ROI/SL behavior now track the source runtime more closely while remaining reproducible under this repository's training, backtest, and dry-run workflow.

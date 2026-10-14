# 전략 상태와 이름

현재 활성 연구 전략은 **추세·거래량 전략**이다. 이전 코드 G와 같은 계열이며, SMA20/50/100/200 정·역배열, 이중 Stochastic 교차, MFI와 상대 거래량을 사용했던 기준형에서 변형을 이어간다. 기준형과 변형의 조건·결과를 구분하고, 코인마다 따로 최적의 값을 골라 공통 전략처럼 표시하지 않는다.

나머지 시안은 초안(draft)으로 보관한다. 코드, Pine 파일, 과거 거래 기록과 결과를 삭제하지 않는다.

| 이전 코드 | 이름 | 상태 |
|---|---|---|
| A | Stoch RSI 시안 | 초안 |
| B | 일반 Stochastic 시안 | 초안 |
| C | 이중 Stochastic 기준 시안 | 초안 |
| D | ADX·DMI 결합 시안 | 초안 |
| E | MACD 모멘텀 결합 시안 | 초안 |
| F | MFI 결합 시안 | 초안 |
| G | 추세·거래량 전략 | 활성 |
| H | MACD·RSI 결합 시안 | 초안 |

상태의 원본은 `ppp-strategy-catalog.json`이다. 표시 이름을 바꿔도 이전 결과의 내부 코드, 파일 이름, 계산 설정은 보존한다.

기준형은 이전 G/R2+S2(이중 Stochastic·MFI·RVOL 진입, SMA50/반대 교차 청산, 첫 진입 봉1% 가격 손절)이다. ZEC에서 높은 수익을 냈던 기록이 모든 코인에서 승률·손익비가 가장 높다는 뜻은 아니다.

초입·이격 제한형(T2-R4)은 **실험 변형**으로 기록하며 기준형을 교체하지 않는다. BTC/ETH 선택 단계의 비용·공통성 기준에 실패했다. 새 대형 코인 비교와 전체 차트는 로컬의 `user_data/backtest_results/ppp-largecap-2026-10-14/index.html`, 초안들은 `user_data/backtest_results/ppp-largecap-2026-10-14/draft-history.html`에서 확인한다. 생성된 보고서는 GitHub에 포함하지 않는다.

과거 보고서의 로컬 경로는 전체 기존 연구 `user_data/backtest_results/ppp-selective-2026-10-14/ppp-research-report.html`, WLD 초안 비교 `user_data/backtest_results/ppp-wld-2026-10-14/index.html`이다. Pine 원본은 `docs/tradingview/ppp`, `docs/tradingview/ppp-combinations`에 있다.

# 추세·거래량 전략

이전 G를 이름만 바꾼 **기준형**을 활성 기준으로 유지한다. 원래 G Pine 파일과 모든 다른 시안은 기록용으로 보존한다. `trend-volume-baseline-v6.pine`의 기본값은 이전 G와 동일하다.

`trend-volume-early-experimental-v6.pine`은 고정 후보 T2-R4의 **진입 조건 표시용 실험 지표**다. 전체 코인 공통성과 보수적 비용의 합격 기준에 실패했다. 기준형을 교체하지 않는다. 두 파일은 실제 주문·포지션·계좌를 추적하는 TradingView 전략이 아니라 후보 신호를 그리는 indicator다. 보유 중에도 후보 삼각형이 표시될 수 있다. 실제 체결·리스크 관리는 Python 백테스트와 HTML 거래 기록을 따른다.

실험형은 SMA20>50>100>200 롱·반대 배열 숏을 그대로 유지한다. 새 이중 Stochastic 교차, 본선 롱≤35/숏≥65, MFI 롱30–80/숏20–70, 이전20봉 RVOL0.5–3, 방향별 SMA20 이격−0.25–1.25ATR, ATR/가격≥명목 왕복비용3배를 사용한다. 확인 종가 다음 실제 봉 시가에 진입한다. 반대 지표 교차 또는 진입가 기준 신호 봉ATR×1.5 종가 손절은 다음 시가에 체결하고, 별도1% 가격 손절은 실제 진입 봉에만 적용한다. Pine 지표는 이 청산 주문을 실행하지 않는다.

Pine Editor에 각 파일을 붙여 차트에 추가하면 된다. 보조 수치는 Data Window에서 확인한다. 로컬 검증은 Python 계산·백테스트·HTML을 대상으로 했으며, TradingView Pine 컴파일러로 실행한 검증은 하지 않았다. 자료 제공자와 캔들 준비 구간 차이로 차트 결과가 다를 수 있다.

재현 명령:

```sh
python scripts/ppp_largecap_research.py --stage train
python scripts/ppp_largecap_research.py --stage validate
python scripts/ppp_largecap_report.py
```

Python 환경에는 NumPy가 필요하다. 원본 자료 폴더는 `ppp_largecap_research.DATA_ROOTS`를 따른다. `train`은 기존 선택을 새로 만드는 명시적 명령이다. 가설·비용·계산 소스가 변경되면 `validate`가 중단하므로 기존 결과와 다른 전략을 같은 이름으로 비교하지 않는다. 활성 이름과 draft 분류는 `docs/strategy-notes/ppp-strategy-catalog.json`이 원본이다.

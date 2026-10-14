# PPP / 추세·거래량 전략 연구

영상에서 추론한 Pine Script 시안, Python 백테스트, 거래별 차트 검토 도구를 보관한다. 원본 PPP의 계산식은 공개된 소스를 확인한 것이 아니므로 같은 지표라고 단정하지 않는다.

새 세션은 [연구 인계 기록](../../../.agents/rules/ppp-research-continuation.md)과 [활성 전략 상태](../../strategy-notes/ppp-strategy-status.md)를 먼저 읽는다. 최신 결론은 [연구 결과 요약](../../strategy-notes/ppp-research-findings.md)에 있다.

## 소스

- 활성 기준형: [Pine v6](../../tradingview/ppp-trend-volume/trend-volume-baseline-v6.pine), [설명](../../tradingview/ppp-trend-volume/README.ko.md).
- A–C 시안: `docs/tradingview/ppp`; D–H 조합: `docs/tradingview/ppp-combinations`. G 이외에는 draft다. 원본 파일은 유지한다.
- 신호·청산·복리 엔진: `scripts/ppp_backtest.py`, `ppp_combo_backtest.py`, `ppp_risk_backtest.py`, `ppp_selective_backtest.py`, `ppp_capital_replay.py`.
- 임의 코인 기본 연구: `scripts/ppp_asset_research.py`.
- 초입 비교: `scripts/ppp_largecap_research.py`, `ppp_largecap_report.py`.
- 1분 확인 / 기준 주기 손절 비교: `scripts/ppp_support_ladder.py`, `ppp_support_report.py`.
- 차트 모음: `scripts/ppp_chart_gallery.py`, `scripts/templates/ppp-*.html`, `ppp-chart-trades.js`.
- 연구 자료실: `scripts/ppp_research_portal.py`, `ppp-research-portal.html`, `ppp-research-document.html`. 기존 생성 명령으로 함께 갱신한다.

Pine 기준형과 Python의 새 지지·저항 실험은 구현 범위가 다르다. 새 지지·저항 실험을 Pine에 포팅한 것으로 표현하지 않는다.

## 환경과 검증

Python 3.11 이상을 사용한다. 차트 모음 서버는 Python 표준 라이브러리만 필요하다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ppp.txt
.venv/bin/python -m unittest discover -s tests -p 'test_ppp*.py'
```

전체 저장소 테스트는 `python -m unittest discover -s tests`다. 다른 전략의 선택적 의존성과 fixtures도 필요할 수 있다. Pine 컴파일은 TradingView에서 별도로 확인한다. Python 테스트 통과를 Pine 컴파일 확인으로 표시하지 않는다.

## 데이터와 재현

시세 CSV, 거래 로그, 결과 JSON, 생성된 HTML, 브라우저 프로필은 `user_data/data`와 `user_data/backtest_results`에 보관하며 Git에는 포함하지 않는다. 새 clone에는 차트 데이터가 없으므로 먼저 내려받고 연구를 실행해야 한다. 같은 호스트의 새 세션에서는 기존 로컬 결과를 우선 재사용한다.

기존 연구의 고정 기간은 **2026-04-14 00:00 → 2026-10-14 00:00 KST**, 종료 시각 미포함이다. 워밍업은 그보다 앞선다. 기본 연구 엔진의 날짜가 자동으로 오늘에 맞춰 이동하지 않는다.

예시: Binance BTC 1분 데이터를 내려받고 기본 G 연구를 생성한다.

```bash
.venv/bin/python scripts/ppp_binance_download.py --symbols BTCUSDT --output user_data/data/ppp-binance
.venv/bin/python scripts/ppp_asset_research.py --asset BTC --models G --profiles R2 --binance-data user_data/data/ppp-binance --output user_data/backtest_results/ppp-btc-review
```

`ppp_asset_research.py`는 기본 청산 연구다. 활성 기준형의 첫 진입 봉 S2까지 포함한 실험을 이 명령과 동일하다고 표시하지 않는다. S2 계열과 고정 코인 집합은 기존 `ppp_largecap_research.py` / `ppp_support_ladder.py` 계약을 따른다.

새 코인의 기본 연구는 `--asset`, 데이터 폴더, 기간을 지정할 수 있다. 지지 확인 실험의 대상 목록과 데이터 매핑은 아직 연구 코드에 고정되어 있으므로 새 코인을 넣을 때 해당 매핑과 검증을 함께 바꾼다. 거래소 간 데이터를 합쳐 부족한 1분 구간을 채우지 않는다.

## 차트 모음과 서버

```bash
python3 scripts/ppp_chart_gallery.py
python3 scripts/ppp_chart_gallery.py --serve --host 127.0.0.1 --port 8765
```

기본 입력은 `user_data/backtest_results`, 출력은 그 아래 `ppp-chart-gallery`다. 기존 차트 원본을 바꾸지 않고 모음용 사본을 만든다. 새 결과를 추가한 뒤 생성 명령을 다시 실행하면 현재 서버도 갱신된 목록을 읽는다. `--source`, `--output`으로 위치를 바꿀 수 있다.

다음 기능을 제공한다.

- 상단 연구 메뉴: 연구 요약, 전략, 실험·결과, 통계·그림, Pine Script, 차트, 자료실.
- 같은 서버의 `/research.html`에서 설명 문서, 과거 상세 보고서, 통계 그림과 차트 캡처를 탐색한다. 그림을 눌러 확대하고 관련 보고서로 이동할 수 있다.
- Pine 코드 보기·복사·파일 다운로드, 집계 통계 CSV 다운로드. HTTP 접속에서도 지원되는 브라우저는 코드 복사를 사용할 수 있다.
- 코인·실험·draft 선택, 한 번에 하나의 차트 로드.
- 거래소·주기·리스크 방식 선택, 전체 실제 캔들과 보조지표.
- 거래 목록, 롱·숏 / 수익·손실 필터, 행 선택 시 진입 1시간 전부터 청산 1시간 후까지 확대.
- 초기 최근 구간 확대: 데스크톱 약 240개, 모바일 약 120개 실행 봉.
- 거래 선택 시 목록과 페이지 위치 유지. 세로 터치는 페이지 스크롤, 가로 터치는 차트 이동.

자료실은 `docs/strategy-notes/ppp*.md`, PPP Pine와 안내 문서, 지정된 실험 보고서·그림·집계 CSV만 게시한다. 시세 원본·거래 원장·로그·브라우저 프로필·개인 설정은 게시하지 않는다. 원본 파일을 바꾸지 않고 출력 폴더에 사본을 만들며, 보고서의 연결은 게시된 문서·차트·파일로 바꾼다. 새 clone에서는 설명과 Pine가 제공되고, 아직 생성하지 않은 결과는 없는 상태로 표시한다. 초기 영상 관찰·합성 입력 그림은 로컬에 존재하는 경우에만 포함한다.

지속 실행에는 `scripts/ppp-chart-gallery.service`를 사용할 수 있다. 템플릿의 저장소 경로를 실제 checkout에 맞춘 뒤 설치한다. 예시 환경 파일의 호스트 기본값은 loopback이다. Tailscale 공유를 요청받은 경우에만 노드의 실제 Tailscale IP를 로컬 환경 파일에 넣는다. 공용 네트워크 바인딩이나 Funnel은 별도의 공개 범위다.

```bash
mkdir -p ~/.config/systemd/user
cp scripts/ppp-chart-gallery.env.example ~/.config/ppp-chart-gallery.env
cp scripts/ppp-chart-gallery.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ppp-chart-gallery.service
systemctl --user status ppp-chart-gallery.service
```

현재 설치된 서비스 설정은 이 템플릿과 분리되어 있다. 새 템플릿을 설치하면 환경 파일 설정이 적용되므로, 기존 주소를 유지하려면 먼저 로컬 설정을 확인한다. 로그는 `journalctl --user -u ppp-chart-gallery.service`에서 확인한다. 로그아웃·부팅 후 실행에는 사용자 서비스의 linger 상태도 확인한다.

## 재사용 스킬

- `ppp-strategy-research`: 새 코인 비교, 신호/체결 시간축, 승률·손익비·복리·낙폭 해석.
- `ppp-chart-review`: 차트 모음 생성, 서버 운영, 실제 모바일 터치 회귀 검증.

스킬과 세션 인계 규칙은 `.agents`가 원본이다. 호스트 IP, 계정, 인증 정보, 실제 거래 기록을 스킬에 복사하지 않는다.

모바일 터치 검증 도구는 실제 거래가 있는 차트를 대상으로 실행한다. Chromium이 필요하며 호스트의 GUI/headless 실행 권한 지침을 따른다.

```bash
.venv/bin/python -m pip install -r requirements-ppp-browser.txt
.venv/bin/python .agents/skills/ppp-chart-review/scripts/check_mobile.py --url http://127.0.0.1:8765/
```

# Strategy Workflow

이 문서는 사람이 이 저장소에서 처음부터 끝까지 직접 실행할 때 보는 절차서입니다. 세부 설명은 기존 문서로 분리되어 있으므로, 이 문서는 순서와 판단 기준에 집중합니다.

관련 문서:

- [Environment Setup](setup.md): Docker, Freqtrade, 로컬 설정 파일, 데이터 다운로드.
- [Backtest Policy](backtest-policy.md): 백테스트 결과를 해석하는 기준.
- [Project Architecture](architecture.md): 디렉터리 구조와 책임 경계.
- [Freqtrade References](freqtrade-references.md): 공식 Freqtrade/FreqAI 문서 링크.
- [Strategy Notes](strategy-notes/README.md): 전략별 가설 기록 템플릿.

## 1. 프로젝트 구조를 먼저 이해한다

핵심 경로는 다음과 같다.

- `user_data/strategies`: Freqtrade 전략 클래스.
- `user_data/freqaimodels`: 커스텀 FreqAI 모델 클래스.
- `user_data/configs`: 추적되는 예제 설정과 무시되는 로컬 설정.
- `user_data/data`: 다운로드한 OHLCV 데이터. git에 포함하지 않는다.
- `user_data/models`: 학습된 FreqAI 모델 산출물. git에 포함하지 않는다.
- `user_data/backtest_results`: 백테스트 결과. git에 포함하지 않는다.
- `docs/strategy-notes`: 전략별 가설, 실험, 판단 기록.
- `.agents/skills/freqtrade-strategy-work`: AI 에이전트가 전략을 만들거나 수정할 때 따르는 스킬.

Freqtrade 명령과 동작은 [Freqtrade References](freqtrade-references.md)에 연결된 공식 문서를 기준으로 확인한다.

## 2. 로컬 환경을 준비한다

처음 한 번만 로컬 설정 파일을 만든다.

```bash
cp user_data/configs/config.dryrun.example.json user_data/configs/config.dryrun.json
cp user_data/configs/config.freqai.example.json user_data/configs/config.freqai.json
cp user_data/configs/config.private.example.json user_data/configs/config.private.json
```

`user_data/configs/config.private.json`에는 개인 API 키나 로컬 전용 값을 넣을 수 있지만, 이 파일은 절대 git에 커밋하지 않는다.

FreqAI가 포함된 Freqtrade Docker 이미지를 가져온다.

```bash
docker compose pull
docker compose run --rm freqtrade --version
```

문제가 있으면 [Environment Setup](setup.md)을 먼저 다시 확인한다.

## 3. 전략 아이디어를 문서로 먼저 적는다

새 전략이나 큰 수정은 코드보다 먼저 `docs/strategy-notes/<strategy-name>.md`에 기록한다.

최소한 다음을 적는다.

- 어떤 시장 비효율을 노리는가.
- 진입 조건은 무엇인가.
- 청산 조건은 무엇인가.
- 손절, 포지션 관리, 거래 빈도 제한은 무엇인가.
- FreqAI를 쓴다면 어떤 feature와 target을 쓸 것인가.
- 성공과 실패를 어떤 기준으로 판단할 것인가.

템플릿은 [Strategy Notes](strategy-notes/README.md)를 사용한다.

## 4. 구현 방식을 고른다

규칙 기반 전략이면 `user_data/strategies/<StrategyName>.py` 안에서 Freqtrade 전략 클래스를 작성하거나 수정한다.

FreqAI 전략이면 다음을 함께 확인한다.

- `feature_engineering_*`에서 feature를 만든다.
- `set_freqai_targets`에서 학습 target을 정의한다.
- 전략 설정의 `freqai.identifier`는 feature, target, 모델, 학습 구간이 바뀔 때 변경한다.
- 커스텀 모델이 필요할 때만 `user_data/freqaimodels`에 모델 클래스를 추가한다.

FreqAI feature와 target 이름 규칙은 [Freqtrade References](freqtrade-references.md)의 FreqAI 문서를 따른다.

## 5. 과거 데이터를 받는다

먼저 기본 데이터 다운로드를 실행한다.

```bash
bash scripts/download-data.sh
```

스캘핑 연구는 짧은 timeframe과 충분한 데이터 구간이 중요하다. 연구용으로 범위를 넓히려면 다음처럼 실행한다.

```bash
DATA_TIMERANGE=20250101-20250415 \
BACKTEST_TIMEFRAMES="1m 5m 15m" \
bash scripts/download-data.sh
```

FreqAI 백테스트는 학습 구간과 startup candle이 필요하므로, 데이터 시작일은 백테스트 시작일보다 충분히 앞서야 한다.

## 6. 로컬 백테스트를 돌린다

기본 백테스트:

```bash
bash scripts/backtest.sh
```

특정 전략과 FreqAI 모델을 지정한 백테스트:

```bash
STRATEGY=ScalpingFreqaiStrategy \
FREQAI_MODEL=LightGBMRegressor \
BACKTEST_TIMERANGE=20250301-20250415 \
BACKTEST_TIMEFRAME=1m \
BACKTEST_RESULT_DIR=user_data/backtest_results/manual \
bash scripts/backtest.sh
```

FreqAI 백테스트는 닫힌 timerange가 필요하다. `20250301-`처럼 종료일이 없는 값이 아니라 `20250301-20250415`처럼 시작일과 종료일을 모두 지정한다.

## 7. 결과를 해석한다

수익률만 보지 않는다. [Backtest Policy](backtest-policy.md)를 기준으로 최소한 다음을 확인한다.

- 거래 수가 충분한가.
- 수익이 수수료 이후에도 남는가.
- 최대 낙폭이 감당 가능한가.
- 평균 보유 시간이 스캘핑 의도와 맞는가.
- 특정 시장 구간에만 맞춘 과최적화는 아닌가.
- FreqAI feature나 target 변경이 lookahead bias를 만들지 않았는가.
- limit fill 가정이 실제 dry-run이나 실거래에서 유지될 수 있는가.

진입/청산 signal이나 feature가 크게 바뀌면 Freqtrade의 `lookahead-analysis`를 별도로 돌린다. indicator window, startup candle, recursive indicator가 바뀌면 `recursive-analysis`도 확인한다.

## 8. 전략 노트를 갱신한다

백테스트 결과를 본 뒤 전략 노트에 판단을 남긴다.

- 유지: 더 긴 기간, 더 많은 pair, dry-run으로 진행할 가치가 있다.
- 수정: hypothesis는 유지하지만 entry, exit, risk control을 다시 조정한다.
- 폐기: 거래 수, drawdown, 실현 가능성, 과최적화 위험 때문에 더 진행하지 않는다.

좋은 결과 하나만으로 전략을 승격하지 않는다. 짧은 PR 백테스트는 빠른 검증용이고, 승격 전에는 더 넓은 시장 구간과 dry-run 관찰이 필요하다.

## 9. PR을 올린다

작업 브랜치를 만든다.

```bash
git switch -c codex/my-strategy
```

전략, 노트, 필요한 설정 변경만 커밋한다.

```bash
git add user_data/strategies docs/strategy-notes user_data/configs scripts
git commit -m "feat: add my strategy experiment"
git push -u origin codex/my-strategy
```

GitHub에서 PR을 열면 `.github/workflows/pr-backtest.yml`이 전략 관련 변경을 감지한다. workflow는 데이터를 다운로드하고, 변경된 전략을 찾아 Freqtrade 백테스트를 실행한 뒤 PR 코멘트에 요약을 남긴다.

자동 백테스트가 감지하는 주요 경로:

- `user_data/strategies/**`
- `user_data/freqaimodels/**`
- `user_data/configs/**`
- `scripts/**`
- `docker-compose.yml`

PR 백테스트는 [Backtest Policy](backtest-policy.md)의 기본 구간과 repository variables를 사용한다.

## 10. Dry-run으로 확인한다

PR 백테스트와 리뷰를 통과한 뒤에도 바로 live capital을 쓰지 않는다. 먼저 dry-run을 실행한다.

```bash
bash scripts/dry-run.sh
```

FreqUI는 `docker-compose.yml` 기준으로 `127.0.0.1:8080`에서 접근한다. dry-run에서는 signal 빈도, 주문 생성 방식, 체결 가정, pair별 행동, 로그 오류를 관찰한다.

## 11. 자주 막히는 지점

- FreqAI 백테스트가 timerange 오류로 실패하면 시작일과 종료일이 모두 있는지 확인한다.
- 학습 데이터 부족 오류가 나면 `DATA_TIMERANGE` 시작일을 더 앞당긴다.
- GitHub-hosted PR 백테스트에서 Binance.com 접근이 막히면 CI용 설정인 `config.ci.json` 경로가 추가되어 있는지 확인한다.
- 전략 파일을 삭제한 PR은 자동 백테스트가 실패할 수 있다. 삭제 의도라면 PR 설명에 명시한다.
- FreqAI feature, target, model, training window를 바꿨는데 결과가 이상하게 재사용되는 것 같으면 `freqai.identifier` 변경 여부를 확인한다.

## 12. 하지 말아야 할 것

- API key, secret, live trading credential을 커밋하지 않는다.
- `user_data/data`, `user_data/models`, `user_data/backtest_results` 산출물을 커밋하지 않는다.
- 짧은 기간의 높은 수익률만 보고 전략을 채택하지 않는다.
- dry-run 없이 live trading으로 넘어가지 않는다.
- 백테스트 결과를 실제 체결 품질, 슬리피지, 거래소 제한, 장애 상황의 대체물로 보지 않는다.

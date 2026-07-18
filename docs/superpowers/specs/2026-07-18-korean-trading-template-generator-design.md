# 한국어 거래 실험 템플릿 및 생성기 설계

## 목표

기존 거래 실험 템플릿과 전략 아이디어 검증 스킬의 사용자 작성 문구를 한국어로 제공하고, 사용자가 템플릿을 직접 복사하지 않아도 전략별 작성용 Markdown 파일 네 개를 생성할 수 있게 한다.

## 범위

- `.agents/templates/trading-experiments/`의 여섯 템플릿을 한국어화한다.
- `.agents/skills/validate-freqtrade-strategy-idea/SKILL.md`의 사용자 대화·입력 계약·절차 문구를 한국어화한다.
- `.agents/scripts/create-trading-experiment.sh`를 추가한다.
- 생성기의 기본 출력 위치는 `docs/strategy-notes/experiments/<experiment-slug>/`이다.
- 생성기는 `strategy-idea.md`, `market-regime.md`, `backtest-evaluation.md`, `experiment-log.md`를 만든다.
- 템플릿 원본은 계속 `.agents/templates/trading-experiments/`에만 유지한다. 작성 완료본을 원본 위치에 저장하지 않는다.

## 안정성 및 인터페이스

명령은 다음과 같다.

```bash
bash .agents/scripts/create-trading-experiment.sh <experiment-slug>
```

- `experiment-slug`는 소문자 영문, 숫자, 하이픈만 허용한다 (`[a-z0-9][a-z0-9-]*`).
- 기본 출력 경로에 같은 실험 폴더가 있으면 실패하며 기존 파일을 덮어쓰지 않는다.
- 테스트 또는 별도 보관 위치가 필요할 때만 `--output-root <directory>`를 사용한다. 이 값은 실험 폴더의 상위 경로다.
- `--help`는 사용법과 기본 출력 경로를 보여 준다.
- 스크립트는 원본 네 템플릿이 모두 존재하는지 확인한 뒤에만 폴더를 생성한다.

## 언어 정책

- 제목, 안내 문장, 입력 라벨, 결정·거절 문구, 스킬이 사용자에게 요구하는 내용은 한국어로 쓴다.
- 파일명, 디렉터리명, 프리셋 ID (`STOP-ATR` 등), Freqtrade 명령, 코드 식별자와 수식 변수는 영문을 유지한다.
- 리스크 한도와 평가 규칙은 번역 중에도 바꾸지 않는다: 진입 5%, 거래당 최대 세 번/15%, 동시 두 포지션/30%, 전략 낙폭 5%, 일 손실 30%, 평가 낙폭 5% 초과 시 수익과 무관하게 거절한다.

## 검증

- 새 Python `unittest`는 생성기가 네 파일을 올바른 이름·한국어 템플릿 본문으로 생성하는지 검증한다.
- 같은 slug 재생성 및 잘못된 slug가 비영(0) 종료로 실패하고 기존 파일을 유지하는지 검증한다.
- 전체 `unittest` 스위트, 스킬 구조 검증, `git diff --check`를 실행한다.

# 리스크 프리셋 카드 생성기 설계

## 목표

전략별 실험 문서 생성기를 제거하고, 공용 리스크 관리 라이브러리에 재사용 가능한 프리셋 카드 초안을 자동으로 추가하는 생성기로 교체한다.

## 구조

- 기본 프리셋 카탈로그는 `.agents/templates/trading-experiments/risk-management-presets.md`에 유지한다.
- 사용자 정의 프리셋 카드는 `.agents/templates/trading-experiments/risk-presets/<PRESET-ID>.md`에 둔다.
- 새 스크립트 `.agents/scripts/create-risk-preset.sh`는 한국어 카드 양식을 해당 폴더에 만든다.
- 기존 `create-trading-experiment.sh`와 해당 테스트는 제거한다. 전략별 파일 생성은 공용 라이브러리 흐름의 일부가 아니다.
- 카탈로그와 전략 검증 스킬은 기본 카탈로그와 `risk-presets/`의 완성 카드를 모두 선택 가능한 프리셋 원본으로 읽는다.

## 인터페이스와 안전 규칙

```bash
bash .agents/scripts/create-risk-preset.sh <PRESET-ID>
```

- ID는 `STOP-`, `TP-`, `SCALE-` 중 하나로 시작하고, 나머지는 대문자 영문·숫자·하이픈만 허용한다.
- 같은 ID의 파일이 있으면 실패하며 절대 덮어쓰지 않는다.
- 생성 카드는 적용 장세, 계산식, 허용 범위, 발동/금지 조건, 주문/청산 동작, 비용 가정, 실패/무효화 조건을 모두 요구한다.
- 카드 생성은 프리셋을 승인하거나 수익성을 주장하지 않는다. 선택 시에도 계층별 최대 두 개·전체 최대 여덟 조합과 기존 하드 리스크 한도를 유지한다.

## 검증

- 단위 테스트는 유효한 세 계층 ID의 카드 생성, 잘못된 ID 거절, 중복 카드 보존을 확인한다.
- 스킬 구조 검증, 전체 `unittest`, `git diff --check`를 실행한다.

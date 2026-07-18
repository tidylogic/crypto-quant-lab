# Risk Preset Card Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전략별 실험 파일 생성기를 공용 리스크 프리셋 카드 생성기로 교체한다.

**Architecture:** 기본 카탈로그와 사용자 정의 카드 디렉터리를 함께 프리셋 원본으로 사용한다. Bash 생성기는 ID별 한국어 카드 초안을 안전하게 만들고, 스킬은 이 두 원본에서 후보를 읽도록 한다.

**Tech Stack:** Markdown, Bash, Python `unittest`.

## Global Constraints

- 프리셋 ID는 `STOP-`, `TP-`, `SCALE-`로 시작하며 카드 ID는 계층을 바꾸지 않는다.
- 카드 생성은 수익성·안전성을 보증하지 않으며 기존 5%/15%/두 포지션/30%/5% 낙폭/30% 일손실 한도를 바꾸지 않는다.
- 계층별 최대 두 ID, 전체 최대 여덟 조합, 5% 초과 평가 낙폭 거절, 게이트 우선 평가 규칙을 유지한다.
- 기존 전략별 실험 생성기와 테스트는 삭제한다. 생성된 결과·전략·실행 설정은 커밋하지 않는다.

---

### Task 1: 실패하는 카드 생성기 테스트

**Files:**
- Delete: `tests/test_create_trading_experiment.py`
- Create: `tests/test_create_risk_preset.py`

- [ ] **Step 1: 새 테스트를 작성한다.**

`subprocess.run(["bash", str(SCRIPT), preset_id, "--output-root", tmp], ...)`으로 `STOP-VWAP-FAIL`, `TP-VOLUME-EXIT`, `SCALE-RECLAIM-PYRAMID` 각각이 `<tmp>/<ID>.md`를 만들고 `# 리스크 프리셋 카드` 및 ID를 포함하는지 검증한다. `BAD-ID`는 실패하고, 같은 ID를 두 번 실행하면 두 번째가 실패하며 첫 카드의 내용이 유지되는지 검증한다.

- [ ] **Step 2: RED를 확인한다.**

Run: `python3 -m unittest tests.test_create_risk_preset -v`

Expected: `create-risk-preset.sh`가 없어 실패한다.

### Task 2: 카드 생성기와 라이브러리 연결

**Files:**
- Delete: `.agents/scripts/create-trading-experiment.sh`
- Create: `.agents/scripts/create-risk-preset.sh`
- Modify: `.agents/templates/trading-experiments/template-index.md`
- Modify: `.agents/templates/trading-experiments/risk-management-presets.md`
- Modify: `.agents/skills/validate-freqtrade-strategy-idea/SKILL.md`

- [ ] **Step 1: 최소 생성기를 구현한다.**

`bash .agents/scripts/create-risk-preset.sh <PRESET-ID> [--output-root DIR]`를 구현한다. 기본 출력은 `.agents/templates/trading-experiments/risk-presets/`다. 정규식 `^(STOP|TP|SCALE)-[A-Z0-9][A-Z0-9-]*$`로 ID를 검증하고, 기존 대상 파일을 거절한다. 생성 카드는 적용 장세, 계산식, 허용 범위, 발동 조건, 금지 조건, 주문/청산 동작, 비용 가정, 실패/무효화 조건의 한국어 빈칸을 가진다.

- [ ] **Step 2: 카탈로그와 스킬을 연결한다.**

카탈로그는 기본 카드와 `risk-presets/*.md` 완성 카드를 함께 읽는다고 명시한다. 스킬은 새 카드 생성 명령·경로를 안내하고, 선택된 사용자 정의 ID의 카드가 존재하며 필수 필드가 완성됐는지 요구한다.

- [ ] **Step 3: GREEN을 확인하고 커밋한다.**

```bash
python3 -m unittest tests.test_create_risk_preset -v
bash .agents/scripts/create-risk-preset.sh --help
git diff --check
git add .agents/scripts/create-risk-preset.sh tests/test_create_risk_preset.py .agents/templates/trading-experiments/template-index.md .agents/templates/trading-experiments/risk-management-presets.md .agents/skills/validate-freqtrade-strategy-idea/SKILL.md
git rm .agents/scripts/create-trading-experiment.sh tests/test_create_trading_experiment.py
git commit -m "feat: add risk preset card generator"
```

### Task 3: 최종 검증과 리뷰

- [ ] **Step 1: 전체 검증을 실행한다.**

```bash
python3 /home/user/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/validate-freqtrade-strategy-idea
python3 -m unittest discover -s tests -v
git diff --check origin/main..HEAD
```

- [ ] **Step 2: 독립 리뷰의 중요 지적을 반영한 뒤 PR을 생성·머지한다.**

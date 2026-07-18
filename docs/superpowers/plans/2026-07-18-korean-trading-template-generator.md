# Korean Trading Template Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 한국어 거래 실험 템플릿과 전략별 Markdown 작성 파일 생성기를 제공한다.

**Architecture:** 원본 템플릿은 `.agents/templates/trading-experiments/`에 유지한다. Bash 생성기는 그중 작성용 네 템플릿을 기본 `docs/strategy-notes/experiments/<slug>/`로 복사하며, 원본과 기존 작성 파일을 덮어쓰지 않는다. 검증 스킬은 한국어로 이 흐름과 보수적 리스크 규칙을 안내한다.

**Tech Stack:** Markdown, Bash, Python `unittest`, skill-creator validator.

## Global Constraints

- 제목·안내·입력 라벨·스킬의 사용자 요구 문구는 한국어로 쓴다. 파일명, 경로, preset ID, 명령, 코드 식별자·수식 변수는 영문을 유지한다.
- 원본 템플릿은 `.agents/templates/trading-experiments/`에, 작성 완료본은 `docs/strategy-notes/experiments/<experiment-slug>/`에 둔다.
- `experiment-slug`는 `[a-z0-9][a-z0-9-]*`만 허용하고 기존 slug 폴더는 절대 덮어쓰지 않는다.
- 리스크 한도는 고정한다: 진입 5%; 거래당 최대 세 번/15%; 동시 두 포지션/30%; 전략 낙폭 5%; 일 손실 30%; 평가 낙폭이 5% 초과면 수익과 무관하게 거절한다.
- 전략, FreqAI 모델, 실행 config, 시장 데이터, 백테스트 결과, 로그, 비공개 설정을 변경하거나 커밋하지 않는다.

---

### Task 1: 한국어 원본 템플릿과 검증 스킬

**Files:**
- Modify: `.agents/templates/trading-experiments/template-index.md`
- Modify: `.agents/templates/trading-experiments/risk-management-presets.md`
- Modify: `.agents/templates/trading-experiments/strategy-idea-template.md`
- Modify: `.agents/templates/trading-experiments/market-regime-template.md`
- Modify: `.agents/templates/trading-experiments/backtest-evaluation-template.md`
- Modify: `.agents/templates/trading-experiments/experiment-log-template.md`
- Modify: `.agents/skills/validate-freqtrade-strategy-idea/SKILL.md`

- [ ] **Step 1: 템플릿 여섯 개를 한국어화한다.**

  본문, 표 제목, 입력 라벨, 오류·거절·의사결정 문구를 한국어로 번역한다. `STOP-ATR`, `TP-FIXED-R`, `SCALE-PYRAMID`와 수식·경로·파일명은 유지한다. 인덱스에 다음 생성 명령과 기본 출력 경로를 추가한다.

  ```bash
  bash .agents/scripts/create-trading-experiment.sh <experiment-slug>
  # docs/strategy-notes/experiments/<experiment-slug>/
  ```

- [ ] **Step 2: 검증 스킬의 사용자 프롬프트를 한국어화한다.**

  아이디어 계약, 선택 기준, 절차, 결정·보고 문구를 한국어로 번역한다. 생성 명령을 재사용 프리셋 절에 추가하고, 생성 파일은 입력 초안이며 모든 필수 항목을 채워야 한다고 명시한다.

- [ ] **Step 3: 구조와 불변 규칙을 확인한다.**

  Run:

  ```bash
  rg -n "STOP-FIXED-PCT|STOP-ATR|STOP-STRUCTURE|STOP-CHANDELIER|TP-FIXED-R|TP-ATR-TRAIL|TP-INDICATOR|SCALE-NONE|SCALE-AVERAGE-DOWN|SCALE-PYRAMID" .agents/templates/trading-experiments/risk-management-presets.md
  rg -n "5%|15%|30%|두 개|eight|8" .agents/templates/trading-experiments .agents/skills/validate-freqtrade-strategy-idea/SKILL.md
  git diff --check
  ```

- [ ] **Step 4: 커밋한다.**

  ```bash
  git add .agents/templates/trading-experiments .agents/skills/validate-freqtrade-strategy-idea/SKILL.md
  git commit -m "docs: translate trading experiment templates"
  ```

### Task 2: Markdown 실험 파일 생성기

**Files:**
- Create: `.agents/scripts/create-trading-experiment.sh`
- Create: `tests/test_create_trading_experiment.py`

**Interfaces:**
- Consumes: `.agents/templates/trading-experiments/{strategy-idea,market-regime,backtest-evaluation,experiment-log}-template.md`.
- Produces: `strategy-idea.md`, `market-regime.md`, `backtest-evaluation.md`, `experiment-log.md` below `<output-root>/<experiment-slug>/`.
- CLI: `bash .agents/scripts/create-trading-experiment.sh <experiment-slug> [--output-root <directory>]`.

- [ ] **Step 1: 실패하는 생성기 테스트를 작성한다.**

  `tests/test_create_trading_experiment.py`에 `unittest`와 `subprocess.run`을 사용해 다음 세 가지를 작성한다.

  ```python
  def run_generator(self, *args: str) -> subprocess.CompletedProcess[str]:
      return subprocess.run(
          ["bash", str(SCRIPT), *args],
          cwd=REPO_ROOT,
          text=True,
          capture_output=True,
          check=False,
      )

  def test_creates_four_korean_template_files(self):
      with tempfile.TemporaryDirectory() as tmp:
          result = self.run_generator("ema-bollinger-retest", "--output-root", tmp)
          target = Path(tmp) / "ema-bollinger-retest"
          self.assertEqual(result.returncode, 0, result.stderr)
          self.assertEqual(
              {path.name for path in target.iterdir()},
              {"strategy-idea.md", "market-regime.md", "backtest-evaluation.md", "experiment-log.md"},
          )
          self.assertIn("전략 아이디어", (target / "strategy-idea.md").read_text())

  def test_rejects_invalid_or_existing_slug_without_overwrite(self):
      with tempfile.TemporaryDirectory() as tmp:
          self.assertNotEqual(self.run_generator("bad/name", "--output-root", tmp).returncode, 0)
          self.assertEqual(self.run_generator("demo", "--output-root", tmp).returncode, 0)
          original = (Path(tmp) / "demo" / "strategy-idea.md").read_text()
          self.assertNotEqual(self.run_generator("demo", "--output-root", tmp).returncode, 0)
          self.assertEqual(original, (Path(tmp) / "demo" / "strategy-idea.md").read_text())
  ```

- [ ] **Step 2: 테스트가 생성기 부재 때문에 실패하는지 확인한다.**

  Run: `python3 -m unittest tests.test_create_trading_experiment -v`

  Expected: `create-trading-experiment.sh`가 없어서 두 테스트가 실패한다.

- [ ] **Step 3: 최소 Bash 생성기를 구현한다.**

  스크립트는 아래 동작을 구현한다.

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  # slug 1개와 선택적 --output-root DIR만 파싱한다.
  # --help는 0으로 종료하고 사용법을 출력한다.
  # slug는 ^[a-z0-9][a-z0-9-]*$로 검증한다.
  # 기본 output_root는 "$repo_root/docs/strategy-notes/experiments"다.
  # 대상 폴더가 이미 있거나 네 원본 중 하나가 없으면 비영(0)으로 종료한다.
  # 네 원본을 고정된 출력 이름으로 복사한 뒤 생성 위치를 출력한다.
  ```

- [ ] **Step 4: 집중 테스트와 도움말을 확인한다.**

  Run:

  ```bash
  python3 -m unittest tests.test_create_trading_experiment -v
  bash .agents/scripts/create-trading-experiment.sh --help
  git diff --check
  ```

  Expected: 두 테스트 통과, 도움말에 기본 출력 경로와 `--output-root`가 표시되며 공백 오류가 없다.

- [ ] **Step 5: 커밋한다.**

  ```bash
  git add .agents/scripts/create-trading-experiment.sh tests/test_create_trading_experiment.py
  git commit -m "feat: add trading experiment template generator"
  ```

### Task 3: 최종 검증과 범위 점검

**Files:**
- Verify: `.agents/templates/trading-experiments/`
- Verify: `.agents/skills/validate-freqtrade-strategy-idea/SKILL.md`
- Verify: `.agents/scripts/create-trading-experiment.sh`
- Verify: `tests/test_create_trading_experiment.py`

- [ ] **Step 1: 전체 검증을 실행한다.**

  ```bash
  python3 /home/user/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/validate-freqtrade-strategy-idea
  python3 -m unittest discover -s tests -v
  git diff --check origin/main..HEAD
  ```

- [ ] **Step 2: 범위를 점검한다.**

  `git diff --name-only origin/main..HEAD`가 설계/계획 문서, 한국어 템플릿, 검증 스킬, 생성기, 생성기 테스트만 포함하는지 확인한다. 기존 사용자 미추적 파일과 생성된 `docs/strategy-notes/experiments/` 파일은 stage하지 않는다.

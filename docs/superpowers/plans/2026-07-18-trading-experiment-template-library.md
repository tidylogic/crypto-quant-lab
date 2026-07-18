# Trading Experiment Template Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add modular, reusable trading-experiment templates and connect them to the existing validation skill.

**Architecture:** Keep all reusable assets under `.agents/templates/trading-experiments/`. A catalog defines immutable-risk-aware preset IDs; companion templates consume those IDs for strategy ideas, market regimes, evaluation, and logging. The strategy-validation skill links to the catalog and constrains selection to the documented protocol.

**Tech Stack:** Markdown, YAML frontmatter already present in the skill, Python `unittest` suite, skill-creator validator.

## Global Constraints

- Do not change strategy, FreqAI model, runtime config, private config, market data, model, log, or result artifacts.
- Retain fixed ceilings: 5% per entry; three entries/15% per trade; two positions/30% aggregate; 5% drawdown breaker; 30% daily-loss breaker.
- Reject an acceptance backtest with drawdown above 5%, regardless of profit.
- Select no more than two presets from each of stop, profit-taking, and scale-in layers; compare no more than eight combinations.
- Rank surviving evaluation-period candidates by expectancy, profit factor, and sufficient trade count. Treat win rate and net return as secondary observations.

---

### Task 1: Add the index and risk-preset catalog

**Files:**
- Create: `.agents/templates/trading-experiments/template-index.md`
- Create: `.agents/templates/trading-experiments/risk-management-presets.md`

- [ ] **Step 1: Add the index.**

  Include the exact selection envelope: select up to two stop IDs, two profit-taking IDs, and two scale-in IDs; enumerate at most eight combinations; keep hard limits fixed; use development data only to narrow candidates and a later untouched evaluation period to rank survivors. Include an explicit rejection row for drawdown above 5%.

- [ ] **Step 2: Add preset cards.**

  Define the following IDs and fields on every card: purpose/regime, inputs/formula, allowed range, trigger, prohibition, order/exit behavior, and caveats:

  ```text
  Stop: STOP-FIXED-PCT, STOP-ATR, STOP-STRUCTURE, STOP-CHANDELIER
  Profit: TP-FIXED-R, TP-ATR-TRAIL, TP-INDICATOR
  Scale-in: SCALE-NONE, SCALE-AVERAGE-DOWN, SCALE-PYRAMID
  ```

  State that no scale-in is allowed after invalidation and that the card range is a bounded hypothesis, not a profit search space.

- [ ] **Step 3: Check the catalog.**

  Run:

  ```bash
  rg -n "STOP-FIXED-PCT|STOP-ATR|STOP-STRUCTURE|STOP-CHANDELIER|TP-FIXED-R|TP-ATR-TRAIL|TP-INDICATOR|SCALE-NONE|SCALE-AVERAGE-DOWN|SCALE-PYRAMID" .agents/templates/trading-experiments/risk-management-presets.md
  ```

  Expected: every required ID is present.

### Task 2: Add the four experiment-input templates

**Files:**
- Create: `.agents/templates/trading-experiments/strategy-idea-template.md`
- Create: `.agents/templates/trading-experiments/market-regime-template.md`
- Create: `.agents/templates/trading-experiments/backtest-evaluation-template.md`
- Create: `.agents/templates/trading-experiments/experiment-log-template.md`

- [ ] **Step 1: Add the strategy-idea template.**

  Require hypothesis, market scope, exact initial entry, no-trade rules, invalidation, and permitted preset IDs. Reserve exact fields for two stop, two profit, and two scale-in IDs; non-risk parameter ranges; and forbidden parameters.

- [ ] **Step 2: Add the market-regime template.**

  Require observable trend, volatility, liquidity, session, and funding conditions for both permitted and excluded regimes. Include the consequence for an unavailable or ambiguous signal: do not trade.

- [ ] **Step 3: Add the evaluation template.**

  Require development/evaluation date ranges, pair list, fee/slippage/funding assumptions, minimum trade count, hard rejection gates, a combination score table, and exactly one decision. The table must include expectancy, profit factor, trade count, max drawdown, win rate, net return, and status.

- [ ] **Step 4: Add the log template.**

  Record the idea, selected IDs, execution assumptions, result links or paths, rejected candidates, chosen candidate, and the next action. Include a rule that a result path may be recorded but a generated artifact is never committed.

- [ ] **Step 5: Check all templates.**

  Run:

  ```bash
  for file in .agents/templates/trading-experiments/*.md; do test -s "$file"; done
  ```

  Expected: exit status 0.

### Task 3: Integrate the library with the validation skill and verify

**Files:**
- Modify: `.agents/skills/validate-freqtrade-strategy-idea/SKILL.md`
- Test: `tests/` via `python3 -m unittest discover -s tests -v`

- [ ] **Step 1: Add a template-library section to the skill.**

  Require reading `template-index.md` whenever reusable presets are selected. Require the strategy idea to name selected IDs, enforce the two-per-layer/eight-combination limit, and use the evaluation template's rejection and ranking protocol. Preserve the existing complete-contract gate and all numeric hard limits.

- [ ] **Step 2: Run structural and repository validation.**

  Run:

  ```bash
  python3 /home/user/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/validate-freqtrade-strategy-idea
  python3 -m unittest discover -s tests -v
  git diff --check
  ```

  Expected: `Skill is valid!`, all tests pass, and no whitespace errors.

- [ ] **Step 3: Perform a self-review.**

  Verify that only `.agents/templates/trading-experiments/`, the existing skill, and the approved design/plan documents are staged; that no template weakens the fixed ceilings; and that no generated artifact is staged.

- [ ] **Step 4: Commit.**

  ```bash
  git add .agents/templates/trading-experiments .agents/skills/validate-freqtrade-strategy-idea/SKILL.md docs/superpowers/specs/2026-07-18-trading-experiment-template-library-design.md docs/superpowers/plans/2026-07-18-trading-experiment-template-library.md
  git commit -m "feat: add trading experiment templates"
  ```

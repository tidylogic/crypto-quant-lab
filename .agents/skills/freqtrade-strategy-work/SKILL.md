---
name: freqtrade-strategy-work
description: Use when creating or modifying Freqtrade strategies, FreqAI features, or strategy notes in this repository. Keeps strategy work hypothesis-driven while leaving backtests to PR automation.
---

# Freqtrade Strategy Work

## Overview

Use this workflow for strategy creation and edits under `user_data/strategies`, FreqAI model work under `user_data/freqaimodels`, and related strategy notes.

Backtests are intentionally outside this skill. PR automation detects strategy/config/script changes, runs Freqtrade backtesting, and comments results on the PR.

## Workflow

1. Read `AGENTS.md`, `docs/architecture.md`, and `docs/backtest-policy.md`.
2. State the strategy hypothesis before editing code.
3. Update or create a note under `docs/strategy-notes/` with:
   - hypothesis
   - entry logic
   - exit logic
   - risk controls
   - FreqAI features and target when applicable
4. Keep strategy edits scoped to the hypothesis.
5. When changing FreqAI feature definitions, labels, or model behavior, update `freqai.identifier` or document why the old model namespace remains valid.
6. Do not commit exchange keys, live credentials, downloaded data, trained models, logs, or backtest result artifacts.
7. Run static checks that do not perform backtesting, such as Python compilation and strategy discovery.

## Backtest Boundary

- Do not run `scripts/backtest.sh`, `scripts/pr-backtest.sh`, or `freqtrade backtesting` as part of this skill.
- If the user explicitly asks for a backtest, treat it as a separate verification task after the strategy edit is complete.
- Do not judge a strategy by profit alone. Review trade count, drawdown, fees, slippage, fill assumptions, and overfitting risk.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| Editing signal logic without a hypothesis | Write the hypothesis first, then change code. |
| Changing FreqAI features without a model namespace change | Update `freqai.identifier` or document why reuse is intentional. |
| Running backtests inside this skill | Leave backtesting to PR automation or a separate explicit verification task. |
| Committing runtime artifacts | Keep generated files ignored and out of git. |

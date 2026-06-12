# Agent Instructions

## Source of Truth

- Keep all AI-agent owned assets under `.agents`.
- Put reusable skills under `.agents/skills`.
- Put project rules, workflow notes, and agent-specific operating guidance under `.agents/rules`.
- Do not create root-level `skills` or `rules` paths. Keep those assets under `.agents`.
- Do not create `.claude/skills` or `.codex/skills` directories with real content. Use symbolic links to `.agents` instead.

## Symlink Policy

- Do not create a root-level `skills` compatibility path.
- `.claude/skills` should point to `../.agents/skills`.
- `.claude/rules` should point to `../.agents/rules`.
- `CLAUDE.md` should point to `AGENTS.md`.
- If a Codex-specific project directory is needed, prefer symlinks into `.agents` instead of duplicating files.

## Project Context

- This repository is a Freqtrade and FreqAI crypto trading lab.
- Strategy files live under `user_data/strategies`.
- Custom FreqAI model files live under `user_data/freqaimodels`.
- Runtime artifacts such as downloaded market data, logs, trained models, backtest results, and private configs must stay out of git.

## Strategy Work

- Keep strategy edits focused and hypothesis-driven.
- Avoid committing exchange secrets or live trading credentials.
- Do not treat backtest profit alone as proof of a good strategy. Always consider trade count, drawdown, fees, slippage, and overfitting risk.
- For PR automation, strategy changes should be detectable from paths under `user_data/strategies`, `user_data/freqaimodels`, and relevant config/script files.

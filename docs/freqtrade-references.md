# Freqtrade References

Use the official Freqtrade documentation as the source of truth for commands and behavior.

- [Docker quickstart](https://www.freqtrade.io/en/stable/docker_quickstart/): Docker Compose setup, `create-userdir`, `download-data`, `backtesting`, logs, and UI access.
- [Configuration](https://www.freqtrade.io/en/stable/configuration/): multi-config usage, environment variables, dry-run, order pricing, and production switching.
- [Strategy customization](https://www.freqtrade.io/en/stable/strategy-customization/): strategy class structure and Freqtrade strategy API.
- [Backtesting](https://www.freqtrade.io/en/stable/backtesting/): `backtesting`, `--strategy-list`, exported result directories, result interpretation, and backtesting assumptions.
- [Lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/): bias checks for indicators and entry/exit signals.
- [Recursive analysis](https://www.freqtrade.io/en/stable/recursive-analysis/): startup candle and recursive indicator checks.
- [FreqAI configuration](https://www.freqtrade.io/en/stable/freqai-configuration/): `freqai` config block, `identifier`, feature engineering, and model configuration.
- [FreqAI feature engineering](https://www.freqtrade.io/en/stable/freqai-feature-engineering/): feature and target naming conventions for FreqAI strategies.

## Notes For This Repo

- Freqtrade Docker docs use `docker compose run --rm freqtrade <command>` for one-off commands and `docker compose up` for trading mode.
- Freqtrade supports multiple `--config` arguments; this repo separates dry-run, FreqAI, and private config files.
- Freqtrade backtesting exports to `user_data/backtest_results` by default; this repo uses subdirectories for manual and PR runs.
- FreqAI `identifier` should change when feature set, target, model, or training window changes.


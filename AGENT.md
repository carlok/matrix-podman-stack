# Agent and contributor guide

This repository ships Python helpers (example bot, config loader) and shell automation for a Podman-based Matrix stack. When you change code here, keep tests and coverage from regressing.

## Before every commit

1. Run the unit test suite with coverage (see below).
2. Fix any failures.
3. **Always try to increase code coverage; never decrease it.** Add or extend tests for any new or changed Python behavior.
4. Run `shellcheck scripts/*.sh bootstrap/*.sh` when you touch shell scripts.
5. If you changed `scripts/install-systemd-service.sh`, run the bats tests when `bats` is available.

## Local unit tests and coverage

```bash
python3 -m pip install -r requirements-dev.txt
pytest --cov --cov-report=term-missing --cov-branch
```

Coverage is enforced via `pyproject.toml` (`fail_under`). The measured modules are:

- `bots/example_bot/bot.py`
- `bots/example_bot/duo.py`
- `scripts/load_bot_config.py`
- `scripts/matrix_testutil.py`

Optional shell tests:

```bash
bats tests/bats/
```

## Conventions

- Prefer small, testable pure functions for parsing, validation, and state transitions.
- Mock Matrix (`matrix-nio`) and HTTP clients in unit tests; do not require a live Synapse for pytest.
- Match existing style (ruff, shellcheck in CI).
- Do not commit secrets, host-specific paths, or personal `.env` values.

For human-oriented stack setup and smoke tests, see `README.md`.

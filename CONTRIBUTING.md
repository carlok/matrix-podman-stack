# Contributing

Thanks for your interest in improving **matrix-podman-stack**. This document covers local setup, checks that match CI, and how to open changes.

For day-to-day expectations (especially coverage), also read [AGENT.md](AGENT.md).

## Development setup

1. Clone the repository and copy configuration templates (do not commit real secrets):

   ```bash
   git clone https://github.com/carlok/matrix-podman-stack.git
   cd matrix-podman-stack
   cp .env.example .env
   cp bots.example.yaml bots.yaml   # optional, for bot provisioning scripts
   ```

2. Install Python dev dependencies:

   ```bash
   python3 -m pip install -r requirements-dev.txt
   ```

3. Install script helpers used by bootstrap (optional for Python-only changes):

   ```bash
   python3 -m pip install --user -r scripts/requirements.txt
   ```

4. For compose validation locally, install **Podman** and **podman compose**, then:

   ```bash
   cp .env.example .env
   podman compose config
   ```

## Lint and static checks (same as CI)

From the repository root:

```bash
# Compose file
cp .env.example .env
podman compose config > /dev/null

# Shell scripts
shellcheck -e SC1090,SC1091 scripts/*.sh bootstrap/*.sh

# Python
ruff check scripts/ bots/
python3 -m py_compile scripts/*.py bots/example_bot/bot.py
python3 scripts/load_bot_config.py --config bots.example.yaml --json | python3 -m json.tool
```

Install `shellcheck`, `ruff`, and `PyYAML` if they are not already on your system (CI installs them via `apt` and `pip`).

## Unit tests and coverage

```bash
pytest --cov --cov-report=term-missing --cov-branch
```

Coverage thresholds and measured modules are defined in `pyproject.toml`. **Always try to increase code coverage; never decrease it.** Add or extend tests for any new or changed Python behavior (see [AGENT.md](AGENT.md)).

Optional shell tests when `bats` is installed:

```bash
bats tests/bats/
```

Run these before opening a pull request, especially if you changed `scripts/install-systemd-service.sh`.

## Branch and pull request flow

1. Fork the repository (or branch from `main` if you have write access).
2. Create a descriptive branch, for example `cursor/my-change` or `fix/bootstrap-typo`.
3. Make focused commits; avoid unrelated changes.
4. Ensure lint steps and `pytest` pass locally.
5. Open a pull request against **`main`** with a clear description and testing notes.
6. Address review feedback; keep the PR scoped so CI stays green.

Do not commit secrets, host-specific paths, `.env`, `bots.yaml`, or anything under `data/` (see `.gitignore` and [SECURITY.md](SECURITY.md)).

## Questions

Open a [GitHub issue](https://github.com/carlok/matrix-podman-stack/issues) or reach the maintainer via [@carlok](https://github.com/carlok) on GitHub.

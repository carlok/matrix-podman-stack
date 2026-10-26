## Summary

<!-- What does this PR change and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature or optional profile
- [ ] Documentation / repository metadata
- [ ] Refactor or tooling
- [ ] Other (describe below)

## Testing

- [ ] `shellcheck -e SC1090,SC1091 scripts/*.sh bootstrap/*.sh` (if shell scripts changed)
- [ ] `ruff check scripts/ bots/` (if Python changed)
- [ ] `pytest --cov --cov-report=term-missing --cov-branch` — **coverage did not decrease**
- [ ] `bats tests/bats/` (if `scripts/install-systemd-service.sh` changed)
- [ ] `podman compose config` (if `compose.yaml` or `.env.example` changed)

## Checklist

- [ ] Tests added or updated for behavior changes
- [ ] [AGENT.md](AGENT.md) expectations followed (coverage must not drop)
- [ ] No secrets, tokens, or host-specific paths committed
- [ ] [CHANGELOG.md](CHANGELOG.md) updated for user-visible changes (if applicable)

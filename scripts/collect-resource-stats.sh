#!/usr/bin/env bash
# Print podman stats for matrix-podman-stack containers (idle snapshot).
# Run after services are healthy; optional second arg labels the scenario.
set -euo pipefail

LABEL="${1:-snapshot}"
echo "# $LABEL — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
podman stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' \
  --filter "label=io.podman.compose.project=matrix-podman-stack" 2>/dev/null || \
  podman stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'

if pgrep -af 'bots/example_bot/bot.py' >/dev/null 2>&1; then
  echo "# host bot processes (not in podman stats)"
  pgrep -af 'bots/example_bot/bot.py' || true
fi

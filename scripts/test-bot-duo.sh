#!/usr/bin/env bash
# Smoke test: master/worker duo mode with turn cap and stop marker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
set -a
source .env
# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"
# shellcheck disable=SC1090
source "${BOT_TOKENS_FILE:-$DATA_ROOT/bots/tokens.env}"
set +a

first="${BOTS_LOCALPARTS%%,*}"
second="${BOTS_LOCALPARTS#*,}"
if [[ -z "$first" || "$second" == "$first" ]]; then
  echo "Need at least two bots in bots.yaml (pattern count >= 2)" >&2
  exit 1
fi

slug1="$(PYTHONPATH="$ROOT/scripts" python3 -c "from load_bot_config import env_key; print(env_key('${first}'))")"
slug2="$(PYTHONPATH="$ROOT/scripts" python3 -c "from load_bot_config import env_key; print(env_key('${second}'))")"

python3 -m venv "$ROOT/.venv-bot-test"
"$ROOT/.venv-bot-test/bin/pip" install -q -r "$ROOT/bots/example_bot/requirements.txt"

export BOT_DUO_STATE_DIR="${DATA_ROOT}/bots/duo-state"

master_user_var="${slug1}_USER_ID"
master_token_var="${slug1}_ACCESS_TOKEN"
worker_user_var="${slug2}_USER_ID"
worker_token_var="${slug2}_ACCESS_TOKEN"

exec timeout 120 python3 "$ROOT/scripts/test-bot-duo.py" \
  --server-name "$SYNAPSE_SERVER_NAME" \
  --admin-password "${TEST_ADMIN_PASSWORD:?Set TEST_ADMIN_PASSWORD}" \
  --master-user-id "${!master_user_var}" \
  --master-token "${!master_token_var}" \
  --worker-user-id "${!worker_user_var}" \
  --worker-token "${!worker_token_var}" \
  --bot-script "$ROOT/bots/example_bot/bot.py" \
  --venv-python "$ROOT/.venv-bot-test/bin/python" \
  --max-turns "${BOT_MAX_TURNS:-3}" \
  --stop-marker "${BOT_DUO_STOP_MARKER:-[DONE]}"

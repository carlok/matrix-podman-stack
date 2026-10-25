#!/usr/bin/env bash
# Smoke test: bot @mention reply + ignore-other-bots (bounded runtime).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
set -a
source .env
# shellcheck disable=SC1090
# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"
# shellcheck disable=SC1090
source "${BOT_TOKENS_FILE:-$DATA_ROOT/bots/tokens.env}"
set +a

first_localpart="${BOTS_LOCALPARTS%%,*}"
second_localpart="${BOTS_LOCALPARTS#*,}"
if [[ "$second_localpart" == "$first_localpart" ]]; then
  second_localpart=""
fi

if [[ -z "$first_localpart" ]]; then
  echo "BOTS_LOCALPARTS missing — run scripts/create-bots.sh" >&2
  exit 1
fi

slug1="$(PYTHONPATH="$ROOT/scripts" python3 -c "from load_bot_config import env_key; print(env_key('${first_localpart}'))")"
token1_var="${slug1}_ACCESS_TOKEN"
user1_var="${slug1}_USER_ID"
display1_var="${slug1}_DISPLAY_NAME"

python3 -m venv "$ROOT/.venv-bot-test"
"$ROOT/.venv-bot-test/bin/pip" install -q -r "$ROOT/bots/example_bot/requirements.txt"

args=(
  --server-name "$SYNAPSE_SERVER_NAME"
  --admin-password "${TEST_ADMIN_PASSWORD:?Set TEST_ADMIN_PASSWORD}"
  --bot-user-id "${!user1_var}"
  --bot-token "${!token1_var}"
  --bot-localpart "$first_localpart"
  --bot-display-name "${!display1_var:-$first_localpart}"
  --bot-script "$ROOT/bots/example_bot/bot.py"
  --venv-python "$ROOT/.venv-bot-test/bin/python"
  --timeout 30
)

if [[ -n "$second_localpart" ]]; then
  slug2="$(PYTHONPATH="$ROOT/scripts" python3 -c "from load_bot_config import env_key; print(env_key('${second_localpart}'))")"
  user2_var="${slug2}_USER_ID"
  token2_var="${slug2}_ACCESS_TOKEN"
  args+=(--second-bot-user-id "${!user2_var}")
  args+=(--second-bot-token "${!token2_var}")
  args+=(--second-bot-localpart "$second_localpart")
fi

exec timeout 90 python3 "$ROOT/scripts/test-bot-mention.py" "${args[@]}"

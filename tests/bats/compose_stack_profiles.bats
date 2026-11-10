#!/usr/bin/env bats

setup() {
  ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
  BIN="$(mktemp -d)"
}

teardown() {
  rm -rf "${BIN}"
}

_install_fake_compose() {
  local help_text="$1"
  cat > "${BIN}/podman-compose" <<EOF
#!/bin/sh
if [ "\${1:-}" = "--help" ]; then
  printf '%s\n' "${help_text}"
  exit 0
fi
printf '%s\n' "\$@"
EOF
  chmod +x "${BIN}/podman-compose"
}

@test "podman-compose with --profile receives one flag per COMPOSE_PROFILES entry" {
  _install_fake_compose "--profile  Specify a profile to enable"
  PATH="${BIN}:${PATH}" COMPOSE_PROFILES=" bus, llm " run "${ROOT}/scripts/compose_stack.sh" up -d nats
  [ "$status" -eq 0 ]
  [[ "$output" == *"--profile"* ]]
  [[ "$output" == *"bus"* ]]
  [[ "$output" == *"llm"* ]]
  profile_line="$(printf '%s\n' "$output" | grep -n -- '--profile' | head -n 1 | cut -d: -f1)"
  up_line="$(printf '%s\n' "$output" | grep -n '^up$' | head -n 1 | cut -d: -f1)"
  [ -n "$profile_line" ]
  [ -n "$up_line" ]
  [ "$profile_line" -lt "$up_line" ]
}

@test "podman-compose 1.0 without --profile keeps COMPOSE_PROFILES only" {
  _install_fake_compose "podman-compose 1.0.6"
  PATH="${BIN}:${PATH}" COMPOSE_PROFILES="bus" run "${ROOT}/scripts/compose_stack.sh" up -d nats
  [ "$status" -eq 0 ]
  [[ "$output" != *"--profile"* ]]
  [[ "$output" == *"up"* ]]
}

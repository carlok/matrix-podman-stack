#!/usr/bin/env bats

setup() {
  export TEST_HOME
  TEST_HOME="$(mktemp -d)"
  export XDG_CONFIG_HOME="${TEST_HOME}/.config"
  export HOME="${TEST_HOME}"
  ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
  SCRIPT="${ROOT}/scripts/install-systemd-service.sh"
}

teardown() {
  rm -rf "${TEST_HOME}"
}

@test "install writes expected systemd user unit" {
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  unit="${XDG_CONFIG_HOME}/systemd/user/matrix-podman-stack.service"
  [ -f "$unit" ]
  grep -q "WorkingDirectory=${ROOT}" "$unit"
  grep -q "ExecStart=" "$unit"
}

@test "uninstall removes unit file" {
  "$SCRIPT"
  unit="${XDG_CONFIG_HOME}/systemd/user/matrix-podman-stack.service"
  [ -f "$unit" ]
  run "$SCRIPT" --uninstall
  [ "$status" -eq 0 ]
  [ ! -f "$unit" ]
}

@test "profiles override appears in unit" {
  run "$SCRIPT" --profiles "bus,monitoring"
  [ "$status" -eq 0 ]
  unit="${XDG_CONFIG_HOME}/systemd/user/matrix-podman-stack.service"
  grep -q 'COMPOSE_PROFILES=bus,monitoring' "$unit"
}

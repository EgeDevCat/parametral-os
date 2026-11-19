#!/usr/bin/env bash
# End-to-end smoke test of the *shipped* entry points (two real processes, real sockets).
set -euo pipefail
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
export ULTRAOS_STATE="$TMP/state"
export ULTRAOS_RUNTIME="$TMP/run"
export XDG_RUNTIME_DIR="$TMP/run-xdg"
export PYTHONPATH=src
KEY="${ULTRAOS_OPERATOR_KEY:-$HOME/.local/state/ultraos/operator.key}"

mkdir -p "$ULTRAOS_RUNTIME" "$XDG_RUNTIME_DIR"

echo "== starting harddenyd =="
python3 bin/harddenyd --rules policy/hard_deny.v1.json --key "$KEY" \
  --socket "$ULTRAOS_RUNTIME/harddeny.sock" > "$TMP/harddeny.log" 2>&1 &
HD_PID=$!
trap 'kill $HD_PID $OS_PID 2>/dev/null || true; rm -rf "$TMP"' EXIT

for _ in $(seq 1 100); do [ -S "$ULTRAOS_RUNTIME/harddeny.sock" ] && break; sleep 0.05; done
[ -S "$ULTRAOS_RUNTIME/harddeny.sock" ] || { echo 'harddenyd did not start'; cat "$TMP/harddeny.log"; exit 1; }
cat "$TMP/harddeny.log"

echo "== oracle check: git (allow), modprobe (deny) =="
python3 -m ultraos.cli harddeny check exec.run --scope '{"command":"git"}' | head -3
python3 -m ultraos.cli harddeny check exec.run --scope '{"command":"modprobe"}' | head -3

echo "== starting ultraosd =="
python3 bin/ultraosd --harddeny-socket "$ULTRAOS_RUNTIME/harddeny.sock" > "$TMP/osd.log" 2>&1 &
OS_PID=$!
for _ in $(seq 1 100); do [ -S "$ULTRAOS_RUNTIME/v1/control.sock" ] && break; sleep 0.05; done
[ -S "$ULTRAOS_RUNTIME/v1/control.sock" ] || { echo 'ultraosd did not start'; cat "$TMP/osd.log"; exit 1; }
cat "$TMP/osd.log"

echo "== status =="
python3 bin/ultraos status

echo "== doctor =="
python3 bin/ultraos doctor

echo "SMOKE OK"

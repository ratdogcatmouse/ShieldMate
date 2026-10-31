#!/usr/bin/env bash
# Live smoke test: boot the real backend with the built frontend and check that they work together.
# Run it with `make smoke` (which rebuilds the frontend in real-API mode first).
#
# What it does:
#   * starts uvicorn on a spare port (SMOKE_PORT, default 18000) with a throwaway database,
#     so it never touches backend/shieldmate.db or a server you already have running
#   * checks the API, the pages the backend serves for the React app, and one built asset
#   * stops the server and deletes the temp folder when it finishes, pass or fail
#
# Not isolated: POST /api/demo/reset always regenerates backend/demo_backup/ (that is what a reset
# is for, and the folder is gitignored), so that folder is rewritten.
#
# Bash 3.2-safe (macOS default).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
DIST="$ROOT/frontend/dist"
VENV_PY="$BACKEND/.venv/bin/python"
PORT="${SMOKE_PORT:-18000}"
BASE="http://127.0.0.1:$PORT"

PASS=0
FAIL=0
SERVER_PID=""
TMP=""

ok()  { PASS=$((PASS + 1)); printf '  \033[32mPASS\033[0m %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
die() { printf '\033[1;31m[smoke] error:\033[0m %s\n' "$*" >&2; exit 1; }

cleanup() {
  trap - EXIT
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [ -n "$TMP" ]; then rm -rf "$TMP"; fi
}

# expect NAME METHOD PATH STATUS [REGEX]
# Sends the request, then checks the HTTP status and (optionally) that the body matches REGEX.
expect() {
  local name="$1" method="$2" path="$3" want="$4" pattern="${5:-}" code
  code="$(curl -sS -o "$TMP/body" -w '%{http_code}' -X "$method" "$BASE$path" 2>/dev/null || true)"
  if [ "$code" != "$want" ]; then
    bad "$name (HTTP $code, wanted $want)"
    return 0
  fi
  if [ -n "$pattern" ] && ! grep -Eq -- "$pattern" "$TMP/body"; then
    bad "$name (body does not match: $pattern)"
    return 0
  fi
  ok "$name"
}

# --- preflight ---------------------------------------------------------------------------
[ -x "$VENV_PY" ] || die "backend/.venv is missing; run 'make install'"
[ -f "$DIST/index.html" ] || die "frontend/dist is missing; run 'make build' (or use 'make smoke', which builds)"
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  die "port $PORT is in use; pick another with SMOKE_PORT=<port> make smoke"
fi

TMP="$(mktemp -d)"
trap cleanup EXIT
trap 'exit 130' INT TERM

# --- boot the backend --------------------------------------------------------------------
echo "Booting the backend on $BASE (temp database in $TMP)"
(cd "$BACKEND" && DB_PATH="$TMP/smoke.db" exec "$VENV_PY" -m uvicorn main:app \
  --host 127.0.0.1 --port "$PORT") >"$TMP/server.log" 2>&1 &
SERVER_PID=$!

started=0
for _ in $(seq 1 40); do
  if curl -fsS "$BASE/api/status" >/dev/null 2>&1; then started=1; break; fi
  kill -0 "$SERVER_PID" 2>/dev/null || break
  sleep 0.5
done
if [ "$started" -ne 1 ]; then
  cat "$TMP/server.log" >&2
  die "the backend did not start (log above)"
fi

# --- checks ------------------------------------------------------------------------------
echo "Checking the API"
expect "GET /api/status is JSON with alert_source" GET /api/status 200 '"alert_source"'
expect "GET /api/clinic"                           GET /api/clinic 200
expect "GET /api/nope is a JSON 404, not HTML"     GET /api/nope 404 '"error" *: *"not_found"'

echo "Checking the frontend served by the backend"
expect "GET /           returns the React app"   GET /           200 'id="root"'
expect "GET /owner      falls back to the app"   GET /owner      200 'id="root"'
expect "GET /staff/1    falls back to the app"   GET /staff/1    200 'id="root"'
expect "GET /drill/1234 falls back to the app"   GET /drill/1234 200 'id="root"'
expect "GET /backstage  falls back to the app"   GET /backstage  200 'id="root"'

# The first script the built index.html loads must actually be served (catches a broken /assets mount).
asset="$(grep -oE '/assets/[^"]+\.js' "$DIST/index.html" | head -n1 || true)"
if [ -n "$asset" ]; then
  expect "GET $asset (built bundle)" GET "$asset" 200
else
  bad "frontend/dist/index.html references no /assets/*.js bundle"
fi

echo "Checking a demo round trip (reset, replay an alert, read it back)"
expect "POST /api/demo/reset"                         POST /api/demo/reset 200 '"ok" *: *true'
expect "POST /api/demo/replay/password_guessing"      POST /api/demo/replay/password_guessing 200
expect "GET /api/alerts?role=owner has an alert card" GET "/api/alerts?role=owner&lang=en" 200 '"alerts" *: *\[ *\{'

# --- result ------------------------------------------------------------------------------
echo
if [ "$FAIL" -ne 0 ]; then
  echo "Server log (last 20 lines):" >&2
  tail -n 20 "$TMP/server.log" >&2
  printf '\033[1;31mSmoke test failed:\033[0m %d passed, %d failed\n' "$PASS" "$FAIL"
  exit 1
fi
printf '\033[1;32mSmoke test passed:\033[0m %d checks\n' "$PASS"

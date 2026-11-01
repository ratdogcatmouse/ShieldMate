#!/usr/bin/env bash
# ShieldMate: run the backend and the frontend together so you can test the whole stack.
#
#   ./start.sh                 serve mode (the demo setup): build the frontend, then FastAPI serves
#                              the React app and /api together on :8000
#   ./start.sh dev             dev mode: uvicorn on :8000 + the Vite dev server on :5173
#                              (hot reload; Vite proxies /api to :8000). Ctrl-C stops both.
#   ./start.sh --fresh         also delete the SQLite DB first (the backend recreates it)
#   ./start.sh --clean-slate   --fresh, plus delete the event log and empty the restore sandbox
#                              (a completely fresh session for a presentation)
#   ./start.sh --no-build      serve mode only: reuse the existing frontend/dist
#
# The ports are fixed because frontend/vite.config.js hard-codes the proxy target
# (http://localhost:8000) and the dev port (5173).
#
# Written for bash 3.2 (the macOS default): no `wait -n`, no mapfile, no associative arrays.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
# Call the project venv's python by path. A bare `python3` on PATH may be some other venv.
VENV_PY="$BACKEND/.venv/bin/python"
BACKEND_PORT=8000
FRONTEND_PORT=5173

MODE="serve"
FRESH=0
CLEAN_SLATE=0
BUILD=1

info() { printf '\033[1;36m[shieldmate]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[shieldmate] warning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[shieldmate] error:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: ./start.sh [serve|dev] [--fresh] [--clean-slate] [--no-build] [-h]

  serve         build the frontend and serve everything from FastAPI on :$BACKEND_PORT (default)
  dev           uvicorn on :$BACKEND_PORT + Vite dev server on :$FRONTEND_PORT (hot reload)
  --fresh       delete the SQLite database before starting
  --clean-slate --fresh, plus delete the event log and empty the restore sandbox
  --no-build    serve mode: skip the frontend build and reuse frontend/dist
EOF
}

# --- arguments ---------------------------------------------------------------------------
for arg in "$@"; do
  case "$arg" in
    serve|dev)  MODE="$arg" ;;
    --fresh)    FRESH=1 ;;
    --clean-slate) FRESH=1; CLEAN_SLATE=1 ;;
    --no-build) BUILD=0 ;;
    -h|--help)  usage; exit 0 ;;
    *)          usage >&2; die "unknown argument: $arg" ;;
  esac
done

# --- preflight ---------------------------------------------------------------------------
# Fail early with a clear message instead of halfway through a build.
check_tools() {
  local tool
  for tool in node npm curl lsof; do
    command -v "$tool" >/dev/null 2>&1 || die "'$tool' is not installed or not on PATH"
  done
  local node_major
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
  if [ "$node_major" -lt 24 ]; then
    warn "Node $node_major found; frontend/package.json asks for >= 24 (see frontend/.nvmrc)"
  fi
}

# Exit if something is already listening on the port. Without this, uvicorn dies with a
# less helpful error, and Vite silently moves to the next port, which breaks the printed URLs.
check_port_free() {
  local port="$1" what="$2" listeners
  listeners="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$listeners" ]; then
    printf '%s\n' "$listeners" >&2
    die "port $port ($what) is already in use. Stop that process first (see above)."
  fi
}

# --- backend environment -----------------------------------------------------------------
ensure_backend_env() {
  if [ ! -x "$VENV_PY" ]; then
    local base_py
    base_py="$(command -v python3.12 || command -v python3 || true)"
    [ -n "$base_py" ] || die "python3 not found; cannot create backend/.venv"
    info "Creating backend/.venv with $base_py"
    "$base_py" -m venv "$BACKEND/.venv"
  fi
  # Only install when the app's imports are missing, so repeat starts stay fast.
  if ! "$VENV_PY" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
    info "Installing backend requirements"
    "$VENV_PY" -m pip install --quiet -r "$BACKEND/requirements.txt"
  fi
  if [ ! -f "$BACKEND/.env" ]; then
    info "backend/.env not found: using built-in defaults (replay mode, flags off)"
  fi
}

# --- frontend dependencies and build -----------------------------------------------------
ensure_frontend_deps() {
  # npm writes node_modules/.package-lock.json on every install, so a lockfile newer than it
  # (or a missing node_modules) means the dependencies are stale.
  if [ ! -d "$FRONTEND/node_modules" ] || [ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]; then
    info "Installing frontend dependencies (npm ci)"
    (cd "$FRONTEND" && npm ci)
  fi
}

build_frontend() {
  # Always rebuild by default, so the served app matches the source.
  info "Building the frontend"
  (cd "$FRONTEND" && npm run build)
}

# --- fresh start -------------------------------------------------------------------------
reset_database() {
  # DB_PATH (env var) overrides the default; a value in backend/.env is not read here.
  local db="${DB_PATH:-backend/shieldmate.db}"
  case "$db" in /*) ;; *) db="$ROOT/$db" ;; esac
  info "Removing database $db (and its -wal/-shm files)"
  rm -f "$db" "$db-wal" "$db-shm"
  if [ "$CLEAN_SLATE" -eq 1 ]; then wipe_event_log "$db"; fi
}

# --clean-slate: the event log (kept by --fresh and by Reset) and the restore sandbox too.
# Paths follow config.py: EVENTS_DB_PATH, else "<db name>-events.db" beside the DB.
wipe_event_log() {
  local db="$1" events sandbox
  events="${EVENTS_DB_PATH:-${db%.db}-events.db}"
  case "$events" in /*) ;; *) events="$ROOT/$events" ;; esac
  info "Removing event log $events (and its -wal/-shm files)"
  rm -f "$events" "$events-wal" "$events-shm"
  sandbox="${RESTORE_SANDBOX_DIR:-backend/restore_sandbox}"
  case "$sandbox" in /*) ;; *) sandbox="$ROOT/$sandbox" ;; esac
  if [ -d "$sandbox" ]; then
    info "Emptying restore sandbox $sandbox"
    find "$sandbox" -mindepth 1 -delete
  fi
}

# --- banner ------------------------------------------------------------------------------
lan_ip() {
  # The address a phone on the same hotspot/Wi-Fi would use. Empty if none is found.
  local ip=""
  if command -v ipconfig >/dev/null 2>&1; then
    ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  elif command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  printf '%s' "$ip"
}

print_banner() {
  local port="$1" ip
  ip="$(lan_ip)"
  echo
  info "ShieldMate is starting in $MODE mode"
  echo "    This computer : http://localhost:$port"
  if [ -n "$ip" ]; then
    echo "    Phones (same network) : http://$ip:$port"
  fi
  echo "    Pages         : /  (pick a person)   /owner   /it   /mission   /backstage"
  echo "    Backend health: http://localhost:$BACKEND_PORT/api/status"
  echo "    Reset demo    : make reset"
  echo
}

# --- serve mode --------------------------------------------------------------------------
run_serve() {
  check_port_free "$BACKEND_PORT" "backend + built frontend"
  ensure_backend_env
  ensure_frontend_deps
  if [ "$FRESH" -eq 1 ]; then reset_database; fi
  if [ "$BUILD" -eq 1 ]; then
    build_frontend
  elif [ ! -f "$FRONTEND/dist/index.html" ]; then
    die "--no-build was given but frontend/dist does not exist; run without --no-build"
  fi
  print_banner "$BACKEND_PORT"
  # One worker and no --reload: the background loops (action timeouts, Wazuh polling) must run
  # exactly once. exec hands the terminal to uvicorn so Ctrl-C reaches it directly.
  cd "$BACKEND"
  exec "$VENV_PY" -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT"
}

# --- dev mode ----------------------------------------------------------------------------
BACK_PID=""
FRONT_PID=""

# Kill a process and everything it started (npm -> sh -> node would otherwise be left behind).
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT
  local pid
  for pid in $FRONT_PID $BACK_PID; do
    kill_tree "$pid"
    wait "$pid" 2>/dev/null || true
  done
}

# Block until the backend answers, so Vite never opens against a dead proxy target.
wait_for_backend() {
  local i
  for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/status" >/dev/null 2>&1; then
      return 0
    fi
    kill -0 "$BACK_PID" 2>/dev/null || die "the backend exited during start-up (see its output above)"
    sleep 0.5
  done
  die "the backend did not answer /api/status within 15 seconds"
}

run_dev() {
  check_port_free "$BACKEND_PORT" "backend"
  check_port_free "$FRONTEND_PORT" "Vite dev server"
  ensure_backend_env
  ensure_frontend_deps
  if [ "$FRESH" -eq 1 ]; then reset_database; fi

  # From here on, make sure both children die when this script does (Ctrl-C, error or kill).
  trap cleanup EXIT
  trap 'exit 130' INT TERM

  info "Starting the backend on :$BACKEND_PORT"
  (cd "$BACKEND" && exec "$VENV_PY" -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT") &
  BACK_PID=$!
  wait_for_backend

  info "Starting the Vite dev server on :$FRONTEND_PORT"
  # --strictPort: fail instead of silently picking another port (the preflight already checked).
  (cd "$FRONTEND" && exec npm run dev -- --strictPort) &
  FRONT_PID=$!

  print_banner "$FRONTEND_PORT"

  # Stay in the foreground until either server stops. Polling keeps this bash 3.2-compatible.
  while kill -0 "$BACK_PID" 2>/dev/null && kill -0 "$FRONT_PID" 2>/dev/null; do
    sleep 1
  done
  if ! kill -0 "$BACK_PID" 2>/dev/null; then
    die "the backend stopped unexpectedly"
  fi
  die "the Vite dev server stopped unexpectedly"
}

check_tools
case "$MODE" in
  serve) run_serve ;;
  dev)   run_dev ;;
esac

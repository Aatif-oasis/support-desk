#!/usr/bin/env bash
# Oasis Chatbot — one-command setup for Mac/Linux.
#
#   chmod +x setup.sh && ./setup.sh
#
# Creates the virtualenv, installs both stacks, sets up .env files,
# runs migrations and loads demo data. Safe to re-run.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

step() { printf "\n=== %s ===\n" "$1"; }
ok()   { printf "  OK  %s\n" "$1"; }
warn() { printf "  !!  %s\n" "$1"; }

step "Checking prerequisites"
for cmd in python3 npm; do
  command -v "$cmd" >/dev/null || { echo "$cmd not found. Install it and re-run."; exit 1; }
  ok "$cmd found"
done

# Postgres and Redis may live in Docker or on another host, so a missing
# local binary is a warning, not a failure.
command -v pg_isready >/dev/null && pg_isready -q 2>/dev/null \
  && ok "PostgreSQL reachable" \
  || warn "PostgreSQL not detected — make sure a database is reachable"

command -v redis-cli >/dev/null && redis-cli ping >/dev/null 2>&1 \
  && ok "Redis reachable" \
  || warn "Redis not detected — real-time chat will not work without it"

step "Setting up environment files"
if [ -f "$ROOT/backend/.env" ]; then
  ok ".env already exists (leaving it alone)"
else
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  # A random JWT secret per install — nobody should ship the placeholder.
  python3 - "$ROOT/backend/.env" "$SECRET" <<'PY'
import sys, pathlib
path, secret = pathlib.Path(sys.argv[1]), sys.argv[2]
path.write_text(path.read_text().replace("CHANGE_ME_TO_A_LONG_RANDOM_STRING", secret))
PY
  ok "Created backend/.env with a generated JWT secret"
  warn "Now open backend/.env and set your real database password in DATABASE_URL"
fi

[ -f "$ROOT/dashboard/.env.local" ] || {
  cp "$ROOT/dashboard/.env.local.example" "$ROOT/dashboard/.env.local"
  ok "Created dashboard/.env.local"
}

step "Installing backend dependencies"
cd "$ROOT/backend"
[ -d venv ] || { python3 -m venv venv; ok "Created virtualenv"; }
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt
ok "Python packages installed"

step "Preparing the database"
./venv/bin/alembic upgrade head
ok "Tables created"
./venv/bin/python -m app.seed
./venv/bin/python -m app.seed_demo

step "Installing dashboard dependencies"
cd "$ROOT/dashboard"
npm install --silent
ok "Node packages installed"

cat <<'EOF'

Setup complete.

Start the backend (terminal 1):
    cd backend && source venv/bin/activate && uvicorn app.main:app --reload

Start the dashboard (terminal 2):
    cd dashboard && npm run dev

Then open http://localhost:3000/login
    admin@demo.com / DemoPass123

Widget demo: open widget/demo.html in a browser.

EOF

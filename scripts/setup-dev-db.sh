#!/usr/bin/env bash
# One-time setup: install native PostgreSQL 16 + pgvector for development on WSL2.
# Run via: make setup-dev-db
#
# After this runs, make db-up is a fast pg_isready check (no containers).
# PostgreSQL auto-starts with WSL2 (systemd service, enabled by this script).

set -euo pipefail

DEV_PORT=5433
DEV_USER=newsbrief
DEV_PASS=newsbrief_dev
DEV_DB=newsbrief

echo "=== NewsBrief dev database setup (WSL2 native PostgreSQL) ==="
echo ""

# ── 1. Add PGDG apt repository ───────────────────────────────────────────────
if ! grep -r "apt.postgresql.org" /etc/apt/sources.list* /etc/apt/sources.list.d/ >/dev/null 2>&1; then
    echo "→ Adding PostgreSQL PGDG apt repository..."
    sudo apt-get install -y --no-install-recommends curl ca-certificates gnupg lsb-release
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
    echo "deb https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        | sudo tee /etc/apt/sources.list.d/pgdg.list
    sudo apt-get update -qq
else
    echo "→ PGDG repository already configured."
fi

# ── 2. Install PostgreSQL 16 + pgvector ──────────────────────────────────────
echo "→ Installing postgresql-16 and postgresql-16-pgvector..."
sudo apt-get install -y postgresql-16 postgresql-16-pgvector

# ── 3. Configure port 5433 ───────────────────────────────────────────────────
PG_CONF="/etc/postgresql/16/main/postgresql.conf"
CURRENT_PORT=$(sudo grep -E "^port\s*=" "$PG_CONF" 2>/dev/null | awk -F= '{print $2}' | tr -d ' ' || echo "5432")

if [ "$CURRENT_PORT" != "$DEV_PORT" ]; then
    echo "→ Setting PostgreSQL port to $DEV_PORT in $PG_CONF..."
    sudo sed -i "s/^#\?port\s*=.*/port = $DEV_PORT/" "$PG_CONF"
    # Verify the change landed
    if ! sudo grep -qE "^port\s*=\s*$DEV_PORT" "$PG_CONF"; then
        echo "  (port line not found; appending)"
        echo "port = $DEV_PORT" | sudo tee -a "$PG_CONF" >/dev/null
    fi
else
    echo "→ PostgreSQL already configured on port $DEV_PORT."
fi

# ── 4. Enable + start PostgreSQL ─────────────────────────────────────────────
echo "→ Enabling PostgreSQL auto-start..."
sudo systemctl enable postgresql 2>/dev/null || sudo update-rc.d postgresql enable 2>/dev/null || true

echo "→ Starting PostgreSQL..."
sudo service postgresql restart

# Wait for it to be ready
for i in $(seq 1 15); do
    pg_isready -h localhost -p "$DEV_PORT" -U "$DEV_USER" -d "$DEV_DB" >/dev/null 2>&1 && break
    sleep 1
done

if ! pg_isready -h localhost -p "$DEV_PORT" >/dev/null 2>&1; then
    echo "❌ PostgreSQL did not start on port $DEV_PORT. Check: sudo service postgresql status"
    exit 1
fi

# ── 5. Create user, database, extensions ─────────────────────────────────────
echo "→ Creating database user '$DEV_USER'..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DEV_USER'" \
    | grep -q 1 \
    || sudo -u postgres psql -c "CREATE USER $DEV_USER WITH PASSWORD '$DEV_PASS';"

echo "→ Creating database '$DEV_DB'..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DEV_DB'" \
    | grep -q 1 \
    || sudo -u postgres createdb -O "$DEV_USER" "$DEV_DB"

echo "→ Enabling pgvector extension..."
sudo -u postgres psql -d "$DEV_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"

# ── 6. Done ──────────────────────────────────────────────────────────────────
echo ""
echo "✅ Dev database ready"
echo "   Host:       localhost:$DEV_PORT"
echo "   User:       $DEV_USER"
echo "   Database:   $DEV_DB"
echo "   Connection: postgresql://$DEV_USER:$DEV_PASS@localhost:$DEV_PORT/$DEV_DB"
echo ""
echo "Next steps:"
echo "   make migrate-dev   # apply schema migrations"
echo "   make dev-full      # start the app"

#!/usr/bin/env bash
# Ghosts of Wikipedia: one-shot setup for a fresh Hostinger VPS (Ubuntu 24.04), run as root:
#
#   curl -fsSL https://raw.githubusercontent.com/salomeshioshvili/ghosts_of_wikipedia/main/deploy/hostinger_setup.sh -o setup.sh
#   FEATHERLESS_API_KEY=... CONTEXT_DEV_API_KEY=... bash setup.sh
#
# Optional: DOMAIN=ghosts.example.com (HTTPS via Caddy), EMBED_URL=..., REPO_URL=... (private repo:
# https://<token>@github.com/...), BRANCH=main.
#
# What it does (about 10-15 min to a live site; the data keeps loading in the background):
#   1. MariaDB 12.3 (11.8 if 12.3 isn't offered), Python, Node 22, Caddy
#   2. clone the repo to /opt/ghosts, .env, Python venv, build the website
#   3. start the API as a service behind Caddy on port 80 (and 443 with DOMAIN)
#   4. in the background: download dataset M, load revisions, process the demo articles first
#      (Civil War 1150, Winter War 1256, Mannerheim 6021), then the 50 hero articles, moves,
#      stats, coordination scores and English translations. Log: /var/log/ghosts-prepare.log
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/salomeshioshvili/ghosts_of_wikipedia.git}"
BRANCH="${BRANCH:-main}"
APP=/opt/ghosts
# Re-running keeps the existing database password (it lives in $APP/.env), else the API would lose its database.
if [ -z "${DB_PASS:-}" ] && [ -f "$APP/.env" ]; then
  DB_PASS="$(sed -n 's|^DB_URL=mysql://ghosts:\([^@]*\)@.*|\1|p' "$APP/.env")"
fi
DB_PASS="${DB_PASS:-$(openssl rand -hex 12)}"
LOG=/var/log/ghosts-prepare.log
say() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }

[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
export DEBIAN_FRONTEND=noninteractive

say "1/6 system packages"
apt-get update -y
apt-get install -y curl ca-certificates git python3 python3-venv python3-pip build-essential caddy ufw openssl
if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

say "2/6 MariaDB"
if ! command -v mariadb >/dev/null; then
  curl -LsS https://r.mariadb.com/downloads/mariadb_repo_setup -o /tmp/mariadb_repo_setup
  bash /tmp/mariadb_repo_setup --mariadb-server-version="mariadb-12.3" \
    || bash /tmp/mariadb_repo_setup --mariadb-server-version="mariadb-11.8"
  apt-get update -y
  apt-get install -y mariadb-server mariadb-client
fi
cat > /etc/mysql/mariadb.conf.d/99-ghosts.cnf <<'EOF'
[mysqld]
character-set-server = utf8mb4
collation-server     = utf8mb4_unicode_ci
max_allowed_packet   = 64M
innodb_buffer_pool_size = 1G
bind-address         = 127.0.0.1
EOF
systemctl enable --now mariadb
systemctl restart mariadb
mariadb -e "SELECT VERSION();"
mariadb <<EOF
CREATE DATABASE IF NOT EXISTS ghosts CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'ghosts'@'localhost' IDENTIFIED BY '${DB_PASS}';
CREATE USER IF NOT EXISTS 'ghosts'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
ALTER USER 'ghosts'@'localhost' IDENTIFIED BY '${DB_PASS}';
ALTER USER 'ghosts'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON ghosts.* TO 'ghosts'@'localhost';
GRANT ALL PRIVILEGES ON ghosts.* TO 'ghosts'@'127.0.0.1';
FLUSH PRIVILEGES;
EOF

say "3/6 code"
id ghosts >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash ghosts
if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch -q origin "$BRANCH" && git -C "$APP" reset -q --hard "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$APP"
fi
if [ ! -f "$APP/.env" ]; then
  cat > "$APP/.env" <<EOF
DB_URL=mysql://ghosts:${DB_PASS}@127.0.0.1:3306/ghosts
FEATHERLESS_API_KEY=${FEATHERLESS_API_KEY:-}
EMBED_URL=${EMBED_URL:-}
CONTEXT_DEV_API_KEY=${CONTEXT_DEV_API_KEY:-}
EOF
fi
chmod 600 "$APP/.env"
chown -R ghosts:ghosts "$APP"

say "4/6 Python packages and website build"
sudo -u ghosts bash -c "cd $APP && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt"
sudo -u ghosts bash -c "cd $APP/web && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund) && npm run build"

say "5/6 API service + Caddy"
cat > /etc/systemd/system/ghosts.service <<EOF
[Unit]
Description=Ghosts of Wikipedia API + website
After=network.target mariadb.service
Requires=mariadb.service

[Service]
User=ghosts
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --timeout-keep-alive 120
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ghosts
systemctl restart ghosts

SITE="${DOMAIN:-:80}"
cat > /etc/caddy/Caddyfile <<EOF
$SITE {
    encode gzip
    reverse_proxy 127.0.0.1:8000 {
        transport http {
            read_timeout 300s
        }
    }
}
EOF
systemctl enable --now caddy
systemctl reload caddy || systemctl restart caddy
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

say "6/6 data, in the background (log: $LOG)"
mkdir -p "$APP/deploy"
cat > "$APP/deploy/prepare_server.sh" <<'EOF'
#!/usr/bin/env bash
# Runs as the ghosts user from the repo root. Each step is timed; a failing step doesn't stop the rest.
cd /opt/ghosts
PY=.venv/bin/python
step() { local name="$1"; shift; local t0=$(date +%s); echo "=== $(date +%H:%M:%S) $name"; "$PY" "$@"; \
         echo "=== $name: $? (exit) in $(( $(date +%s) - t0 )) s"; echo "$name $(( $(date +%s) - t0 ))s" >> data/timings_server.txt; }
mkdir -p data
CPUS=$(nproc)
step "download dataset M"                   pipeline/download.py
step "revisions"                            pipeline/revisions.py
step "demo articles 1150 1256 6021"         pipeline/lives.py --pages 1150 1256 6021
step "moves"                                pipeline/moves.py
step "50 hero articles"                     pipeline/lives.py --heroes --workers "$CPUS"
step "moves (heroes)"                       pipeline/moves.py
step "stats"                                pipeline/stats.py
step "coordination scores"                  ai/coordination.py --db
if grep -q '^FEATHERLESS_API_KEY=.' .env; then
  for p in 1150 1256 6021; do
    step "English living $p"                ai/translate.py --db --page "$p" --living
    step "English ghosts $p"                ai/translate.py --db --page "$p" --ghosts
  done
fi
echo "=== ALL DONE $(date +%H:%M:%S)"
EOF
chmod +x "$APP/deploy/prepare_server.sh"
chown ghosts:ghosts "$APP/deploy/prepare_server.sh"
touch "$LOG"; chown ghosts:ghosts "$LOG"
sudo -u ghosts nohup "$APP/deploy/prepare_server.sh" >> "$LOG" 2>&1 &

IP=$(curl -fsS -4 https://ifconfig.me || hostname -I | awk '{print $1}')
say "Done. The site is up; the data is loading."
cat <<EOF

  Site:            http://${DOMAIN:-$IP}/          (Civil War: /article/1150, languages: /languages)
  Data progress:   tail -f $LOG                    (Civil War is ready after "demo articles")
  API status:      systemctl status ghosts         logs: journalctl -u ghosts -f
  Update code:     cd $APP && sudo -u ghosts git pull && sudo -u ghosts bash -c 'cd web && npm run build' && systemctl restart ghosts
  DB password:     in $APP/.env (only on this server)

  Until "demo articles" finishes, opening an article processes it on demand (slower).
EOF

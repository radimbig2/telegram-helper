#!/usr/bin/env bash
# One-command deploy: ./deploy.sh
# Copies the code to /srv/telegramHelper, uploads .env on the first run, rebuilds and restarts the container.
# The database and media (./data on the server) are left untouched.
set -euo pipefail

cd "$(dirname "$0")"

# Server address lives in .deploy.env (git-ignored), see .deploy.env.example.
if [[ -f .deploy.env ]]; then
  # shellcheck disable=SC1091
  source <(tr -d '\r' < .deploy.env)
fi
HOST="${DEPLOY_HOST:?Set DEPLOY_HOST in .deploy.env, e.g. DEPLOY_HOST=user@1.2.3.4}"
DIR="${DEPLOY_DIR:-/srv/telegramHelper}"

echo "-> Copying code to $HOST:$DIR"
ssh "$HOST" "sudo mkdir -p '$DIR/data' && sudo chown \$(id -u):\$(id -g) '$DIR' && sudo chown 1000:1000 '$DIR/data'"
tar czf - app requirements.txt Dockerfile docker-compose.yml .dockerignore .env.example \
  | ssh "$HOST" "cd '$DIR' && rm -rf app && tar xzf -"

if ! ssh "$HOST" "test -f '$DIR/.env'"; then
  echo "-> No .env on the server, uploading the local one"
  # Strip CRLF so Windows line endings don't end up inside the values.
  tr -d '\r' < .env | ssh "$HOST" "umask 077 && cat > '$DIR/.env'"
fi

echo "-> Building and starting"
ssh "$HOST" "cd '$DIR' && docker compose up -d --build && docker compose ps"

echo "-> Cleaning up old images and build cache older than a week"
ssh "$HOST" "docker image prune -f >/dev/null && docker builder prune -f --filter until=168h 2>/dev/null | tail -1"

echo "Done. Logs: ssh $HOST 'cd $DIR && docker compose logs -f'"

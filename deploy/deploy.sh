#!/usr/bin/env bash
# Build and (re)deploy the API (and, with a bot token, the Discord Gateway) of one environment on dellpromaxgb10.
#   deploy/deploy.sh <main|develop> [git-sha]
# Runs on the self-hosted runner `dellpromaxgb10` (on the host itself).
# Needs the platform (meritum-infra: onprem/dellpromaxgb10/platform/setup.sh):
# network `meritum`, meritum-postgres, volume meritum-files-<env>, ~/meritum/gcp/ (WIF) and ~/meritum/envs/api-<env>.env.
# Env: CORE_KEY_FILE, a read-only deploy key of meritum-core (BuildKit --ssh);
#      SECRETS_JSON, VARS_JSON: repo secrets and variables; container_env.sh picks
#      the ones the container gets.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=deploy/container_env.sh
source "$repo/deploy/container_env.sh"
branch=${1:?usage: deploy.sh <main|develop> [sha]}
sha=${2:-$(git -C "$repo" rev-parse HEAD)}
case "$branch" in main) env=prd ;; develop) env=dev ;; *) echo "only main and develop deploy" >&2; exit 1 ;; esac
state=${M_STATE:-$HOME/meritum}
envfile="$state/envs/api-$env.env"
container="meritum-api-$env"
image="meritum-api:$env-${sha:0:12}"
log() { printf '[meritum-api] %s\n' "$*" >&2; }

[ -f "$envfile" ] || { echo "::error::$envfile missing: run the platform workflow in meritum-infra"; exit 1; }

labels=(--label meritum.managed=true --label meritum.role=api --label meritum.env="$env" --label meritum.sha="$sha")
docker build -q --ssh default="${CORE_KEY_FILE:?}" -t "$image" "${labels[@]}" "$repo" >/dev/null
log "built $image"

exec 9>"$state/deploy.lock"
flock 9  # one change at a time on this host (shared with the platform and other repos)
docker rm -f "$container" >/dev/null 2>&1 || true
container_env "$env"
files_mount "$envfile"
[ ${#mount_args[@]} -gt 0 ] || echo "::warning title=No files volume::$envfile has no MERITUM_FILES_VOLUME/DIR: run the platform workflow in meritum-infra"
gcp_mounts "$envfile"
[ ${#gcp_args[@]} -gt 0 ] || echo "::warning title=No GCP credentials::no MERITUM_GCP_MOUNTS in $envfile: container starts without GCP credentials"
docker run -d --name "$container" --network meritum --restart unless-stopped \
  "${labels[@]}" --env-file "$envfile" "${env_args[@]}" "${mount_args[@]}" "${gcp_args[@]}" "$image" >/dev/null
log "started $container"

# Discord Gateway (#39): the same image, its own process, only when the env has a bot token.
gateway="meritum-discord-$env"
docker rm -f "$gateway" >/dev/null 2>&1 || true
if [ -n "${MERITUM_DISCORD_BOT_TOKEN:-}" ]; then
  docker run -d --name "$gateway" --network meritum --restart unless-stopped --no-healthcheck \
    --label meritum.managed=true --label meritum.role=discord --label meritum.env="$env" --label meritum.sha="$sha" \
    --env-file "$envfile" "${env_args[@]}" "${mount_args[@]}" "${gcp_args[@]}" "$image" \
    python -m meritum_backend.discord.gateway >/dev/null
  log "started $gateway"
else
  log "no MERITUM_DISCORD_BOT_TOKEN: $gateway not started"
fi

get() { docker exec "$container" python -c "import sys, urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000$1', timeout=5).read().decode())"; }
post() { docker exec "$container" python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000$1', data=b'', method='POST'), timeout=5).read().decode())"; }

for i in $(seq 30); do
  if get /api/v1/health/live >/dev/null 2>&1; then break; fi
  [ "$i" = 30 ] && { log "liveness check failed"; docker logs --tail 50 "$container" >&2; exit 1; }
  sleep 2
done
# Discord commands (#102): the API container registers its own COMMANDS, so a new option
# or command reaches Discord with the deploy. The app id is a repo variable; no id or
# token, or a refused call, only warns (the deploy does not depend on Discord).
app_id=$(jq -rn --arg k "DISCORD_APPLICATION_ID_$(printf '%s' "$env" | tr '[:lower:]' '[:upper:]')" \
  '(env.VARS_JSON // "{}" | fromjson)[$k] // empty')
if [ -n "$app_id" ] && [ -n "${MERITUM_DISCORD_BOT_TOKEN:-}" ]; then
  if registered=$(docker exec -e DISCORD_APPLICATION_ID="$app_id" "$container" python -c "
import json, os, urllib.request
from meritum_backend.discord.constants import COMMANDS
request = urllib.request.Request(
    'https://discord.com/api/v10/applications/' + os.environ['DISCORD_APPLICATION_ID'] + '/commands',
    data=json.dumps(COMMANDS).encode(), method='PUT',
    headers={'Authorization': 'Bot ' + os.environ['MERITUM_DISCORD_BOT_TOKEN'],
             'Content-Type': 'application/json',
             'User-Agent': 'DiscordBot (https://github.com/Meritum-HackNation2026, 0.1)'})
print(', '.join(c['name'] for c in json.load(urllib.request.urlopen(request, timeout=30))))" 2>&1); then
    log "registered Discord commands: $registered"
  else
    echo "::warning title=Discord commands not registered::$registered"
  fi
else
  log "no DISCORD_APPLICATION_ID_$env or bot token: Discord commands not registered"
fi

# Health returns 200 even when optional providers are down. Retry failures while
# required dependencies come up, then stop the deploy if health still fails.
for i in $(seq 30); do
  if readiness=$(docker exec "$container" python -c "import urllib.error, urllib.request
try: print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=10).read().decode())
except urllib.error.HTTPError as e:
    print(e.read().decode())
    raise SystemExit(1)" 2>&1); then
    break
  fi
  if [ "$i" = 30 ]; then
    log "health check failed: $readiness"
    docker logs --tail 50 "$container" >&2
    exit 1
  fi
  sleep 2
done
case "$readiness" in
  *'"status":"ok"'*) log "ready: $readiness" ;;
  *) echo "::warning title=API degraded::$readiness" ;;
esac

# Smoke test through the worker of the same env (skipped while it is not deployed yet).
if [ "$(docker inspect -f '{{.State.Running}}' "meritum-worker-$env" 2>/dev/null || true)" = true ]; then
  id=$(post /api/v1/jobs/ping | jq -r .workflow_id)
  status=""
  for _ in $(seq 30); do
    status=$(get "/api/v1/jobs/$id" | jq -r .status)
    case "$status" in SUCCESS | ERROR | CANCELLED | MAX_RECOVERY_ATTEMPTS_EXCEEDED) break ;; esac
    sleep 2
  done
  [ "$status" = SUCCESS ] || { log "smoke test FAILED: ping $id is '$status'"; exit 1; }
  log "smoke test passed (ping $id)"
else
  echo "::warning title=Smoke test skipped::meritum-worker-$env is not running"
fi

docker image ls meritum-api --filter "label=meritum.env=$env" --format '{{.Repository}}:{{.Tag}}' \
  | grep -vx "$image" | xargs -r docker rmi >/dev/null 2>&1 || true

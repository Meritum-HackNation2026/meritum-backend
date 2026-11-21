#!/usr/bin/env bash
# Repo secrets and variables that reach the API container; the only list of them.
# Sourced by deploy.sh. `container_env <dev|prd>` reads SECRETS_JSON and VARS_JSON
# (toJSON(secrets) / toJSON(vars) from the deploy job), exports each NAME found as
# <REPO_NAME>_DEV or _PRD and fills env_args with `-e NAME` (no value on the command
# line). A missing one is skipped: the readiness check of the API reports it.
set -euo pipefail
#
# container variable         repo name (+ _DEV/_PRD)    used by
container_vars=(
  "MERITUM_DISCORD_PUBLIC_KEY  DISCORD_PUBLIC_KEY"        # Discord interactions (repo variable)
  "MERITUM_CHANNEL_HASH_SALT   MERITUM_CHANNEL_HASH_SALT" # #24 channel user id hash salt
)

container_env() {
  local suffix name repo value
  suffix=$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')
  env_args=()
  for entry in "${container_vars[@]}"; do
    read -r name repo <<<"$entry"
    value=$(jq -rn --arg k "${repo}_$suffix" \
      '(env.SECRETS_JSON // "{}" | fromjson)[$k] // (env.VARS_JSON // "{}" | fromjson)[$k] // empty')
    [ -n "$value" ] || continue
    export "$name=$value"
    env_args+=(-e "$name")
  done
}

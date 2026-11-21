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
  "MERITUM_SESSION_SECRET           MERITUM_SESSION_SECRET"           # #15 signs the session cookie
  "MERITUM_GOOGLE_CLIENT_ID         GOOGLE_CLIENT_ID"                 # #15 Google login (repo variable)
  "MERITUM_GOOGLE_CLIENT_SECRET     GOOGLE_CLIENT_SECRET"             # #15 Google login
  "MERITUM_MICROSOFT_CLIENT_ID      MICROSOFT_CLIENT_ID"              # #15 Microsoft login (repo variable)
  "MERITUM_MICROSOFT_CLIENT_SECRET  MICROSOFT_CLIENT_SECRET"          # #15 Microsoft login
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

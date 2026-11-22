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
  "MERITUM_CHANNEL_HASH_SALT   MERITUM_CHANNEL_HASH_SALT" # #24 channel user id hash, #66 rate counter keys
  "MERITUM_DISCORD_BOT_TOKEN   DISCORD_BOT_TOKEN"         # #19 readiness: Discord bot token
  "MERITUM_SESSION_SECRET           MERITUM_SESSION_SECRET"           # #15 signs the session cookie
  "MERITUM_GOOGLE_CLIENT_ID         GOOGLE_CLIENT_ID"                 # #15 Google login (repo variable)
  "MERITUM_GOOGLE_CLIENT_SECRET     GOOGLE_CLIENT_SECRET"             # #15 Google login
  "MERITUM_MICROSOFT_CLIENT_ID      MICROSOFT_CLIENT_ID"              # #15 Microsoft login (repo variable)
  "MERITUM_MICROSOFT_CLIENT_SECRET  MICROSOFT_CLIENT_SECRET"          # #15 Microsoft login
  "MERITUM_ADMIN_EMAILS             MERITUM_ADMIN_EMAILS"             # #22 first panel administrators
  "MERITUM_SMS_GATEWAY_USERNAME     SMS_GATEWAY_USERNAME"             # #29 sms-gate.app Basic Auth
  "MERITUM_SMS_GATEWAY_PASSWORD     SMS_GATEWAY_PASSWORD"             # #29 sms-gate.app Basic Auth
  "MERITUM_SMS_GATEWAY_WEBHOOK_SIGNING_KEY  SMS_GATEWAY_WEBHOOK_SIGNING_KEY" # #29 webhook HMAC key
  "MERITUM_SMS_GATEWAY_NUMBER       SMS_GATEWAY_NUMBER"               # #29 the gateway's own number
  "MERITUM_EMAIL_WORKER_URL         EMAIL_WORKER_URL"                 # #34 e-mail Worker address (repo variable)
  "MERITUM_EMAIL_WORKER_SIGNING_SECRET  MERITUM_EMAIL_WORKER_SIGNING_SECRET" # #34 HMAC secret of the e-mail Worker
  "MERITUM_MCP_API_KEYS             MERITUM_MCP_API_KEYS"             # #43, #44 MCP clients: label=key,label2=key2
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

# `files_mount <envfile>` fills mount_args with `-v MERITUM_FILES_VOLUME:MERITUM_FILES_DIR`
# (ADR-31: uploaded files on a volume shared with the worker of the env); empty when
# the platform did not write them. The env file is read, never sourced.
files_mount() {
  local volume dir
  volume=$(sed -n 's/^MERITUM_FILES_VOLUME=//p' "$1" | tail -n 1)
  dir=$(sed -n 's/^MERITUM_FILES_DIR=//p' "$1" | tail -n 1)
  mount_args=()
  [ -n "$volume" ] && [ -n "$dir" ] || return 0
  mount_args+=(-v "$volume:$dir")
}

# `gcp_mounts <envfile>` fills gcp_args with `-v <entry>` per space-separated entry of
# MERITUM_GCP_MOUNTS (`host:container:ro`, written by the platform, infra#28): the
# Workload Identity Federation files GOOGLE_APPLICATION_CREDENTIALS points to. Empty
# when the platform did not write it. Only paths are read, never the credentials.
gcp_mounts() {
  local entry entries
  gcp_args=()
  read -ra entries <<<"$(sed -n 's/^MERITUM_GCP_MOUNTS=//p' "$1" | tail -n 1)"
  for entry in "${entries[@]}"; do
    # credentials are never mounted writable
    [[ $entry == *:ro ]] || { echo "::warning title=GCP mount skipped::$entry is not :ro" >&2; continue; }
    gcp_args+=(-v "$entry")
  done
}

#!/usr/bin/env bash
# Manual provisioning runbook for GitHub issue #41 (Qdrant Cloud vectorstore).
#
# This script is NOT meant to be run unattended or by an agent — read
# docs/runbooks/qdrant-cloud-provisioning.md first, do the manual console
# steps there (Qdrant Cloud's free tier has no API for creating a brand-new
# cluster — it's console-only), then come back and run this script yourself.
# All this script does is verify the cluster you created is reachable and
# store its credentials in SSM Parameter Store. Re-running is safe: it will
# just overwrite the SSM values with whatever you paste in.
#
# Prerequisites:
#   - A Qdrant Cloud free-tier cluster already created via the console (see
#     the runbook), with an API key generated and the cluster's REST URL
#     copied.
#   - AWS CLI v2 installed and configured (`aws configure` / `aws sso login`)
#     against the target account, with permission to write SSM parameters in
#     eu-central-1.
#   - `curl` on PATH (used to verify the cluster responds before storing
#     anything).
#
# Input: reads QDRANT_CLOUD_URL / QDRANT_CLOUD_API_KEY from a local .env file
# (ENV_FILE below, default ./.env) instead of prompting interactively. These
# are deliberately NOT named QDRANT_URL/QDRANT_API_KEY — those two are your
# app's runtime config and, per docs/decisions.md, point at a local Docker
# container for local dev. QDRANT_CLOUD_* only exist to hand the console
# values to this script; delete them from .env once this has been run.

set -euo pipefail

REGION="eu-central-1"
SSM_PREFIX="/langchain-rag/prod/qdrant"
ENV_FILE="${ENV_FILE:-.env}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---- 1. Read connection details out of .env --------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
  log "ERROR: $ENV_FILE not found. Copy .env.example to .env, then add"
  log "QDRANT_CLOUD_URL and QDRANT_CLOUD_API_KEY (values from the Qdrant"
  log "Cloud console — see docs/runbooks/qdrant-cloud-provisioning.md)."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

QDRANT_URL="${QDRANT_CLOUD_URL:-}"
QDRANT_API_KEY="${QDRANT_CLOUD_API_KEY:-}"

if [[ -z "$QDRANT_URL" || -z "$QDRANT_API_KEY" ]]; then
  log "ERROR: QDRANT_CLOUD_URL and/or QDRANT_CLOUD_API_KEY missing or empty in $ENV_FILE."
  exit 1
fi

# ---- 2. Verify the cluster is actually reachable before storing anything --
log "Verifying connectivity to $QDRANT_URL ..."
HTTP_STATUS=$(curl -s -o /dev/null -w '%{http_code}' \
  --max-time 10 \
  -H "api-key: $QDRANT_API_KEY" \
  "$QDRANT_URL/collections")

if [[ "$HTTP_STATUS" != "200" ]]; then
  log "ERROR: got HTTP $HTTP_STATUS from $QDRANT_URL/collections — check the URL/key and try again."
  exit 1
fi
log "Connected OK (collections endpoint returned 200; an empty list is expected before ingestion)."

# ---- 3. Store credentials in SSM Parameter Store (SecureString) -----------
put_param() {
  local name="$1" value="$2"
  aws ssm put-parameter --region "$REGION" \
    --name "$SSM_PREFIX/$name" \
    --type SecureString \
    --value "$value" \
    --overwrite >/dev/null
  log "Stored $SSM_PREFIX/$name"
}

log "Writing credentials to SSM Parameter Store under $SSM_PREFIX/*..."
put_param "url" "$QDRANT_URL"
put_param "api_key" "$QDRANT_API_KEY"

log "Done. Parameters written under $SSM_PREFIX/ (values not printed)."
log "You can now remove QDRANT_CLOUD_URL/QDRANT_CLOUD_API_KEY from $ENV_FILE —"
log "they were only needed for this run."
log ""
log "Local dev does NOT use these values — per docs/decisions.md, local"
log "development points at a local Qdrant Docker container instead, to avoid"
log "network round trips and the free tier's auto-suspend-after-inactivity"
log "during iteration. In your local .env:"
log "  QDRANT_URL=http://localhost:6333"
log "  QDRANT_API_KEY=local-dev-unused"
log "  QDRANT_COLLECTION=rag_documents"
log "and start the container with:"
log "  docker run -p 6333:6333 -v \$(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant"
log ""
log "Next: wire src/retrieval/vectorstore.py to read QDRANT_URL/QDRANT_API_KEY (issue #42)."

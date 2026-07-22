#!/usr/bin/env bash
# Manual provisioning runbook for GitHub issue #39 (RDS Postgres chat memory).
#
# This script is NOT meant to be run unattended or by an agent — it creates
# real AWS resources. Read it, adjust the variables below if needed, then run
# it yourself after `aws configure` / `aws sso login` against the target
# account. Re-running is safe: every step checks for an existing resource
# before creating one.
#
# Prerequisites:
#   - AWS CLI v2 installed and configured with credentials that can create
#     EC2 security groups, RDS instances, and SSM parameters in eu-central-1.
#   - `openssl` available (for password generation).
#
# What this does, in order:
#   1. Looks up the default VPC in eu-central-1 (override VPC_ID below if you
#      use a non-default VPC).
#   2. Creates a placeholder security group for the future ECS Fargate backend
#      (docs/specs/backend-ecs-fargate-deploy.md, issue #57-59) if it doesn't
#      exist yet — the RDS security group needs something to reference, and
#      the ECS service itself isn't provisioned until later in the ticket
#      order (docs/ticket-order.md lists #39 before #57-59 on purpose).
#   3. Creates the RDS security group, allowing inbound Postgres (5432) only
#      from the ECS backend security group above — never 0.0.0.0/0.
#   4. Generates a random master password locally (never printed, never
#      written to disk).
#   5. Creates the RDS instance: smallest free-tier-eligible class, single-AZ,
#      not publicly accessible, eu-central-1.
#   6. Waits for the instance to become available and reads back its endpoint.
#   7. Writes host/port/db name/username/password (and a composed
#      DATABASE_URL) to SSM Parameter Store as SecureString, under
#      /langchain-rag/prod/db/*.
#
# Nothing here is committed to the repo, and no credential is ever echoed to
# stdout in plaintext except the final SSM parameter names (not values).

set -euo pipefail

# ---- Variables (edit if your setup differs from the project defaults) -----
REGION="eu-central-1"
ECS_SG_NAME="langchain-rag-ecs-backend-sg"
RDS_SG_NAME="langchain-rag-rds-sg"
DB_INSTANCE_ID="langchain-rag-chat-memory"
DB_INSTANCE_CLASS="db.t4g.micro"   # free-tier eligible, single-AZ
DB_ALLOCATED_STORAGE=20            # GB, within free-tier
DB_ENGINE="postgres"
DB_NAME="ragchat"
DB_USERNAME="raguser"
SSM_PREFIX="/langchain-rag/prod/db"
VPC_ID="${VPC_ID:-}"               # leave empty to auto-detect the default VPC

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---- 1. Resolve VPC ---------------------------------------------------------
if [[ -z "$VPC_ID" ]]; then
  log "Looking up default VPC in $REGION..."
  VPC_ID=$(aws ec2 describe-vpcs \
    --region "$REGION" \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' --output text)
  if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
    log "ERROR: no default VPC found in $REGION. Set VPC_ID explicitly and re-run."
    exit 1
  fi
fi
log "Using VPC: $VPC_ID"

# ---- 2. ECS backend placeholder security group -----------------------------
ECS_SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters "Name=group-name,Values=$ECS_SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)

if [[ -z "$ECS_SG_ID" || "$ECS_SG_ID" == "None" ]]; then
  log "Creating placeholder ECS backend security group ($ECS_SG_NAME)..."
  ECS_SG_ID=$(aws ec2 create-security-group \
    --region "$REGION" \
    --group-name "$ECS_SG_NAME" \
    --description "Placeholder SG for the ECS Fargate backend (langchain-pdf-rag, issue #57-59) so RDS ingress can reference it" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' --output text)
  log "Created ECS backend SG: $ECS_SG_ID"
else
  log "Found existing ECS backend SG: $ECS_SG_ID"
fi

# ---- 3. RDS security group ---------------------------------------------------
RDS_SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters "Name=group-name,Values=$RDS_SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)

if [[ -z "$RDS_SG_ID" || "$RDS_SG_ID" == "None" ]]; then
  log "Creating RDS security group ($RDS_SG_NAME)..."
  RDS_SG_ID=$(aws ec2 create-security-group \
    --region "$REGION" \
    --group-name "$RDS_SG_NAME" \
    --description "SG for RDS Postgres chat memory (langchain-pdf-rag, issue #39) - inbound restricted to ECS backend SG" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' --output text)
  log "Created RDS SG: $RDS_SG_ID"
else
  log "Found existing RDS SG: $RDS_SG_ID"
fi

log "Ensuring inbound rule: 5432 from $ECS_SG_ID only..."
aws ec2 authorize-security-group-ingress \
  --region "$REGION" \
  --group-id "$RDS_SG_ID" \
  --protocol tcp --port 5432 \
  --source-group "$ECS_SG_ID" \
  2>/dev/null && log "Ingress rule added." || log "Ingress rule already present, skipping."

# ---- 4. Generate master password locally -------------------------------------
if aws rds describe-db-instances --region "$REGION" --db-instance-identifier "$DB_INSTANCE_ID" >/dev/null 2>&1; then
  log "RDS instance $DB_INSTANCE_ID already exists, skipping creation (password not regenerated)."
  SKIP_CREATE=1
else
  SKIP_CREATE=0
  log "Generating a random master password locally..."
  DB_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-32)"
fi

# ---- 5. Create RDS instance ---------------------------------------------------
if [[ "$SKIP_CREATE" -eq 0 ]]; then
  log "Creating RDS instance $DB_INSTANCE_ID ($DB_INSTANCE_CLASS, single-AZ, not publicly accessible)..."
  aws rds create-db-instance \
    --region "$REGION" \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --db-instance-class "$DB_INSTANCE_CLASS" \
    --engine "$DB_ENGINE" \
    --master-username "$DB_USERNAME" \
    --master-user-password "$DB_PASSWORD" \
    --allocated-storage "$DB_ALLOCATED_STORAGE" \
    --db-name "$DB_NAME" \
    --vpc-security-group-ids "$RDS_SG_ID" \
    --no-multi-az \
    --no-publicly-accessible \
    --backup-retention-period 1 \
    --tags Key=Project,Value=langchain-pdf-rag Key=Phase,Value=2 Key=Issue,Value=39 \
    >/dev/null
  log "Create request submitted. Waiting for instance to become available (this takes several minutes)..."
  aws rds wait db-instance-available --region "$REGION" --db-instance-identifier "$DB_INSTANCE_ID"
  log "RDS instance is available."
fi

# ---- 6. Read back endpoint ------------------------------------------------------
log "Fetching endpoint..."
read -r DB_HOST DB_PORT < <(aws rds describe-db-instances \
  --region "$REGION" \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --query 'DBInstances[0].Endpoint.[Address,Port]' --output text)
log "Endpoint: $DB_HOST:$DB_PORT"

if [[ "$SKIP_CREATE" -eq 1 ]]; then
  log "WARNING: instance already existed, so no new password was generated in this run."
  log "If SSM params below are missing/stale, you'll need the original password to fill DB_PASSWORD manually."
  DB_PASSWORD="${DB_PASSWORD:-}"
fi

# ---- 7. Store credentials in SSM Parameter Store (SecureString) -----------------
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
put_param "host" "$DB_HOST"
put_param "port" "$DB_PORT"
put_param "name" "$DB_NAME"
put_param "username" "$DB_USERNAME"
if [[ -n "$DB_PASSWORD" ]]; then
  put_param "password" "$DB_PASSWORD"
  DATABASE_URL="postgresql+psycopg://${DB_USERNAME}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
  put_param "url" "$DATABASE_URL"
else
  log "Skipping password/url params — no password available this run (instance pre-existed)."
fi

log "Done. Parameters written under $SSM_PREFIX/ (values not printed)."
log "Next: wire src/config.py / src/agent/memory.py to read from these (issue #35), per docs/specs/postgres-chat-memory-migration.md."

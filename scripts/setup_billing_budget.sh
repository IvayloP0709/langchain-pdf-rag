#!/usr/bin/env bash
# One-time safety net: creates an AWS Budgets cost alert that emails you if
# spend crosses a threshold. Analogy: like a spending-limit text alert on a
# credit card — it doesn't block anything or spend money itself, it just
# notifies you the same day instead of finding out at month's end.
#
# This is account-wide, not tied to this project's specific resources, so it
# lives here as a standalone script rather than folded into
# provision_rds_postgres.sh. Run it once per account, yourself, after
# reviewing it — same manual-provisioning rule as the RDS script.
#
# Usage:
#   NOTIFY_EMAIL=you@example.com ./scripts/setup_billing_budget.sh
#   NOTIFY_EMAIL=you@example.com BUDGET_LIMIT_USD=10 ./scripts/setup_billing_budget.sh

set -euo pipefail

BUDGET_NAME="langchain-rag-monthly-safety-net"
BUDGET_LIMIT_USD="${BUDGET_LIMIT_USD:-5}"
NOTIFY_EMAIL="${NOTIFY_EMAIL:?Set NOTIFY_EMAIL, e.g. NOTIFY_EMAIL=you@example.com ./scripts/setup_billing_budget.sh}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# AWS Budgets' API only exists at the us-east-1 endpoint, regardless of which
# region your actual resources (RDS, etc.) live in — same kind of
# region-is-fixed-for-this-one-service quirk as the CloudFront ACM cert
# requirement noted in CLAUDE.md.
BUDGETS_REGION="us-east-1"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log "Account: $ACCOUNT_ID"

if aws budgets describe-budget --region "$BUDGETS_REGION" \
    --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" >/dev/null 2>&1; then
  log "Budget '$BUDGET_NAME' already exists, skipping creation."
  exit 0
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

cat > "$TMPDIR/budget.json" <<EOF
{
  "BudgetName": "$BUDGET_NAME",
  "BudgetLimit": {"Amount": "$BUDGET_LIMIT_USD", "Unit": "USD"},
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
EOF

cat > "$TMPDIR/notifications.json" <<EOF
[
  {
    "Notification": {
      "NotificationType": "ACTUAL",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 80,
      "ThresholdType": "PERCENTAGE"
    },
    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "$NOTIFY_EMAIL"}]
  },
  {
    "Notification": {
      "NotificationType": "FORECASTED",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 100,
      "ThresholdType": "PERCENTAGE"
    },
    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "$NOTIFY_EMAIL"}]
  }
]
EOF

log "Creating budget '$BUDGET_NAME' (\$$BUDGET_LIMIT_USD/month cap, alerts to $NOTIFY_EMAIL)..."
aws budgets create-budget \
  --region "$BUDGETS_REGION" \
  --account-id "$ACCOUNT_ID" \
  --budget "file://$TMPDIR/budget.json" \
  --notifications-with-subscribers "file://$TMPDIR/notifications.json"

log "Done. Two alerts are now live:"
log "  - email when ACTUAL spend crosses 80% of \$$BUDGET_LIMIT_USD this month"
log "  - email when AWS FORECASTS you'll exceed \$$BUDGET_LIMIT_USD this month (an early warning, before it actually happens)"

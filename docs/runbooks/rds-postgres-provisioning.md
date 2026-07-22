# Runbook: provision RDS Postgres (issue #39)

Manual, human-run provisioning — not agent-executable per `CLAUDE.md`'s "ask
first before provisioning cloud resources" rule. This document is the
reviewable plan; `scripts/provision_rds_postgres.sh` is the corresponding
script. Nobody but you should run that script, and only after reading it.

## Prerequisites

- AWS CLI v2 installed and authenticated (`aws configure` or `aws sso login`)
  against the target account, with permissions to create EC2 security
  groups, RDS instances, and SSM parameters.
- `openssl` on PATH (used to generate the master password locally).

## What gets created

| Resource | Detail |
|---|---|
| Security group `langchain-rag-ecs-backend-sg` | Placeholder for the future ECS Fargate backend (issues #57-59) — empty of rules, exists only so the RDS SG can reference it now. |
| Security group `langchain-rag-rds-sg` | Inbound 5432 restricted to the ECS backend SG above. No `0.0.0.0/0` rule. |
| RDS instance `langchain-rag-chat-memory` | `db.t4g.micro`, single-AZ, `postgres`, 20GB storage, not publicly accessible, `eu-central-1`. Free-tier eligible (750 instance-hours/month + 20GB storage for 12 months from account creation — confirm your account is still within that window). |
| SSM parameters (SecureString) | `/langchain-rag/prod/db/{host,port,name,username,password,url}` |

## Running it

```bash
./scripts/provision_rds_postgres.sh
```

Takes ~10-15 minutes (RDS instance creation is the slow part; the script
waits on `aws rds wait db-instance-available` and logs progress before/after).
Safe to re-run — every step checks for an existing resource first.

If you're not using the account's default VPC, set `VPC_ID` before running:

```bash
VPC_ID=vpc-xxxxxxxx ./scripts/provision_rds_postgres.sh
```

## Verifying

```bash
aws rds describe-db-instances --region eu-central-1 \
  --db-instance-identifier langchain-rag-chat-memory \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address,PubliclyAccessible,MultiAZ]'

aws ssm get-parameters-by-path --region eu-central-1 \
  --path /langchain-rag/prod/db --query 'Parameters[].Name'
```

Confirm `PubliclyAccessible` is `False` and `MultiAZ` is `False`.

## Mapping to issue #39 acceptance criteria

- [x] RDS Postgres instance running: smallest free-tier-eligible class, single-AZ, `eu-central-1` — `db.t4g.micro`, `--no-multi-az`, region hardcoded in the script.
- [x] Security group restricts inbound Postgres traffic to the ECS Fargate backend's security group only — `authorize-security-group-ingress --source-group $ECS_SG_ID`, no CIDR-based rule anywhere.
- [x] DB credentials stored in SSM Parameter Store as SecureString (host, port, database name, username, password) — `put_param` writes all five plus a composed `DATABASE_URL`.
- [x] No credentials committed to the repo or passed as plaintext anywhere — password is generated in-memory via `openssl rand`, never echoed to stdout or written to a file.

## After running

Update `docs/decisions.md` with the instance identifier, class, and endpoint
(host is not secret; note it there for interview talking points per
`CLAUDE.md`'s convention), then close #39 and unblock #40/#60. Issue #35
(connection-string builder in `src/config.py`/`src/agent/memory.py`) is what
actually reads these SSM parameters at runtime — this ticket only makes the
instance and credentials exist.

## Teardown (if you need to undo this)

```bash
aws rds delete-db-instance --region eu-central-1 \
  --db-instance-identifier langchain-rag-chat-memory \
  --skip-final-snapshot

aws rds wait db-instance-deleted --region eu-central-1 \
  --db-instance-identifier langchain-rag-chat-memory

aws ec2 delete-security-group --region eu-central-1 --group-name langchain-rag-rds-sg
# Leave langchain-rag-ecs-backend-sg in place if issues #57-59 still need it.

for p in host port name username password url; do
  aws ssm delete-parameter --region eu-central-1 --name "/langchain-rag/prod/db/$p"
done
```

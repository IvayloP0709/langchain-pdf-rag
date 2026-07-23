# Runbook: provision Qdrant Cloud (issue #41)

Manual, human-run provisioning — not agent-executable per `CLAUDE.md`'s "ask
first before provisioning cloud resources" rule, and doubly so here: Qdrant
Cloud's free tier has no API for creating a brand-new cluster, only a web
console, so this step *cannot* be scripted end-to-end the way RDS was.
This document is the reviewable plan; `scripts/provision_qdrant_cloud.sh`
handles the part that can be automated (verifying the cluster and storing
credentials). Nobody but you should run that script, and only after doing
the console steps below.

## Prerequisites

- A free Qdrant Cloud account: sign up at https://cloud.qdrant.io.
- AWS CLI v2 installed and authenticated (`aws configure` or `aws sso login`)
  against the target account, with permission to write SSM parameters.
- `curl` on PATH.

## Step 1 — create the cluster (console, manual)

1. Log into https://cloud.qdrant.io and open the **Clusters** section.
2. Click **+ Create**, choose cluster type **Free**.
3. Pick the region closest to `eu-central-1` (Frankfurt) that the free tier
   offers you. Free-tier region choice is limited and not listed in
   Qdrant's docs ahead of time — in the console, prefer an AWS or GCP
   **EU** region (e.g. anything labelled `eu-central`/`europe-west`) over
   any US/Asia option, to keep latency down for the `eu-central-1` ECS
   backend later.
4. Accept the default free-tier config — it can't be customized: 1GB RAM,
   0.5 vCPU, 4GB disk, 1 node. That's enough for the project's 20-paper
   corpus (see the vector-size math in `docs/decisions.md`).
5. Wait for the cluster status to show **Healthy**.

## Step 2 — generate an API key (console, manual)

1. Open the new cluster, go to **Data Access Control** (or **API Keys**).
2. Generate a new key and **copy it immediately** — Qdrant only shows it
   once.
3. Copy the cluster's REST endpoint URL too (shown on the cluster's
   overview page, looks like
   `https://xxxx-xxxx.eu-central.aws.cloud.qdrant.io:6333`).

## Step 3 — verify + store credentials (scripted)

In your local `.env` (copy from `.env.example` if you don't have one yet),
paste the values from Step 2 into the two provisioning-only variables:

```bash
QDRANT_CLOUD_URL=https://xxxx-xxxx.eu-central.aws.cloud.qdrant.io:6333
QDRANT_CLOUD_API_KEY=<the key you copied>
```

These are deliberately separate from `QDRANT_URL`/`QDRANT_API_KEY` — those
are the app's runtime config and point at your local Docker container for
local dev (see `docs/decisions.md`). `QDRANT_CLOUD_*` only exists to hand
the console values to the script below.

Then run:

```bash
./scripts/provision_qdrant_cloud.sh
```

It reads `QDRANT_CLOUD_URL`/`QDRANT_CLOUD_API_KEY` out of `.env`, makes one
`curl` call to confirm the cluster actually responds, then writes both
values to SSM Parameter Store as SecureString. Nothing is echoed to stdout
in plaintext except the parameter names. Once it succeeds, delete the two
`QDRANT_CLOUD_*` lines from `.env` — they've done their job.

## What gets created

| Resource | Detail |
|---|---|
| Qdrant Cloud cluster | Free tier, 1 node, region closest to `eu-central-1` (console-created, not scriptable). |
| API key | Console-generated, full access to the cluster. |
| SSM parameters (SecureString) | `/langchain-rag/prod/qdrant/{url,api_key}` |

## Verifying

```bash
aws ssm get-parameters-by-path --region eu-central-1 \
  --path /langchain-rag/prod/qdrant --query 'Parameters[].Name'
```

Should list `/langchain-rag/prod/qdrant/url` and `/langchain-rag/prod/qdrant/api_key`.

## Mapping to issue #41 acceptance criteria

- [ ] Qdrant Cloud free-tier cluster created via console in the region closest to `eu-central-1` — Step 1 above (you do this by hand; confirm "Healthy" status in the console).
- [ ] API key generated and stored in SSM Parameter Store (SecureString) — Step 2 (console) + Step 3 (`put_param "api_key" ...` in the script).
- [ ] Vector size/distance metric decision recorded for the collection to be created in a later ticket — recorded in `docs/decisions.md`: 1536 dimensions / Cosine distance, matching `text-embedding-3-small`.
- [ ] Local-dev connectivity approach decided and documented — recorded in `docs/decisions.md`: local Qdrant Docker container, not the cloud cluster directly.

## After running

Update `docs/decisions.md`'s "Result" line with the cluster's region and ID
(not secret — fine to note for interview talking points), then close #41.
Issue #42 (vectorstore seam swap) is what actually reads
`QDRANT_URL`/`QDRANT_API_KEY` at runtime — this ticket only makes the
cluster and credentials exist.

## Teardown (if you need to undo this)

```bash
# Delete the cluster from the Qdrant Cloud console (Clusters -> ... -> Delete)
# — there's no CLI for this on the free tier.

aws ssm delete-parameter --region eu-central-1 --name /langchain-rag/prod/qdrant/url
aws ssm delete-parameter --region eu-central-1 --name /langchain-rag/prod/qdrant/api_key
```

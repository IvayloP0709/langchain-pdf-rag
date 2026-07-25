# langchain-pdf-rag

Research-paper RAG assistant built with LangChain + LangGraph.

The project lets you:
- download papers from arXiv,
- ingest PDFs and optional Markdown into Chroma,
- ask one-off questions from the CLI,
- run interactive chat with persistent session memory.

## 5-Minute Quickstart

From repository root:

1. Create and activate a virtual environment.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

2. Install dependencies.

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If you want local embeddings or Markdown ingestion, also install the optional extras:

```bash
pip install -r requirements-optional.txt
```

3. Create `.env` from template and set your OpenAI key.

```bash
cp .env.example .env
```

Required minimum in `.env`:

```env
OPENAI_API_KEY=sk-...
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

4. Add PDFs to `data/papers` (or download from arXiv):

```bash
python scripts/download_arxiv_pdfs.py \
    --query "cat:cs.AI AND (all:retrieval OR all:RAG OR all:agents)" \
    --max-results 20 \
    --out-dir data/papers \
    --metadata data/papers/metadata.csv \
    --skip-existing
```

5. Build the vectorstore and ask a question.

```bash
python -m src.main ingest
python -m src.main ask "What is RAG?"
```

6. Start interactive chat.

```bash
python -m src.main chat --session-id demo
```

## Current Project Capabilities

- CLI entrypoint with `ingest`, `ask`, and `chat` commands.
- Configurable embeddings provider:
    - OpenAI embeddings (`EMBEDDING_PROVIDER=openai`)
    - Local Hugging Face embeddings (`EMBEDDING_PROVIDER=local`)
- Retrieval tool with configurable `RETRIEVAL_K` and `DOC_PREVIEW_CHARS`.
- Persistent chat memory via SQLite session history.
- arXiv bulk PDF downloader script with metadata CSV export.

## Repository Layout

- `src/main.py`: CLI commands (`ingest`, `ask`, `chat`)
- `populate_vectorstore.py`: ingestion pipeline entry
- `src/ingestion/*`: loaders, chunking, embedding model selection
- `src/retrieval/*`: vectorstore creation/loading and retrieval helpers
- `src/agent/*`: LangGraph nodes, router, tools, memory
- `src/eval/*`: eval set generation, retrieval metrics, LLM-as-judge, run reporting
- `scripts/download_arxiv_pdfs.py`: arXiv query + PDF downloader
- `scripts/generate_eval_set.py`: generates an eval set from ingested documents
- `scripts/evaluate.py`: runs the eval set against the agent and writes a run report
- `data/papers`: local PDF corpus
- `data/eval`: eval set and run reports
- `tests/test_memory.py`: memory persistence regression test

## Prerequisites

- Python 3.8+
- pip
- Internet access for OpenAI/Hugging Face/arXiv usage

## Setup

### 1) Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Git Bash on Windows:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) Configure environment variables

Copy the template and edit values:

```bash
cp .env.example .env
```

Windows PowerShell alternative:

```powershell
Copy-Item .env.example .env
```

At minimum, set:
- `OPENAI_API_KEY`
- `EMBEDDING_PROVIDER` (`openai` or `local`)

## Download Papers from arXiv

Use the included script to fetch PDFs and metadata into `data/papers`.

Example:

```bash
python scripts/download_arxiv_pdfs.py \
    --query "cat:cs.AI AND (all:retrieval OR all:RAG OR all:agents)" \
    --max-results 30 \
    --out-dir data/papers \
    --metadata data/papers/metadata.csv \
    --skip-existing
```

Common useful flags:
- `--query` (repeatable): add multiple topic pulls
- `--sort-by relevance|lastUpdatedDate|submittedDate`
- `--sort-order ascending|descending`
- `--delay-seconds 1.5`: polite throttling between downloads
- `--cafile <path>`: custom CA bundle
- `--insecure`: disable SSL verification (troubleshooting only)

## Build the Vector Store

After adding PDFs (and optional Markdown), ingest once:

```bash
python -m src.main ingest
```

Whenever you add, remove, or change documents afterward, re-run ingestion with
`--clean` so the vectorstore is rebuilt from scratch instead of appending to what's
already there (without `--clean`, re-ingesting duplicates every chunk that was
already indexed):

```bash
python -m src.main ingest --clean
```

Optional custom paths:

```bash
python -m src.main ingest \
    --pdf-directory data/papers \
    --md-directory docs \
    --persist-directory ./chroma_db \
    --clean
```

## Ask a Single Question

```bash
python -m src.main ask "What is RAG?"
```

You will see timing breakdown output:
- `pre-ask`, `imports`, `init`, `graph`, `agent`, `ask-total`

## Run Interactive Chat

```bash
python -m src.main chat --session-id my_session
```

Notes:
- Type `exit` or `quit` to end chat.
- Session memory is stored in `chat_history.db` (SQLite).

## Embeddings Configuration

### OpenAI embeddings (recommended for faster startup)

In `.env`:

```env
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

### Local embeddings (no embedding API cost)

In `.env`:

```env
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
HF_QUIET=true
```

Install the optional dependency set first:

```bash
pip install -r requirements-optional.txt
```

Optional for higher Hugging Face rate limits:

```env
HF_TOKEN=hf_...
```

Important: if you switch embedding providers/models, rebuild `chroma_db`.

## Retrieval Tuning

Adjust in `.env`:

```env
RETRIEVAL_K=3
DOC_PREVIEW_CHARS=800
```

- Lower values reduce prompt size and latency.
- Higher values may increase context coverage at the cost of speed.

## Evaluation

The project includes an eval harness that measures retrieval quality, answer quality,
latency, and cost against a known set of questions — a baseline to compare future
pipeline changes (e.g. a fine-tuned reranker) against.

1. Build a real corpus and ingest it (see "Download Papers from arXiv" and "Build the
   Vector Store" above).
2. Generate an eval set from the ingested documents:

```bash
python scripts/generate_eval_set.py \
    --persist-directory ./chroma_db \
    --output data/eval/eval_set.jsonl \
    --questions-per-doc 2
```

This uses an LLM to write a question + reference answer per sampled chunk, grounded
in the actual ingested content, and writes them to `data/eval/eval_set.jsonl`.

3. Run the eval:

```bash
python -m src.main eval
```

Useful flags:
- `--limit N`: only run the first N examples (good for a quick sanity check).
- `--skip-judge`: skip LLM-as-judge answer scoring, retrieval metrics only (no extra API cost).
- `--k`, `--search-type`: tune the direct-retrieval comparison.

Each run computes:
- **Retrieval metrics** (hit rate, MRR, precision@k), both for a direct retriever call
  and for what the agent actually retrieved end-to-end.
- **Answer quality**, via LLM-as-judge scoring of faithfulness/relevance/correctness.
- **Latency and cost per query**.

Results are written to `data/eval/runs/<timestamp>/` (`results.jsonl` + `summary.json` +
`summary.csv`), with a row appended to `data/eval/runs/history.csv` so runs can be
diffed over time (e.g. before/after adding a reranker).

## Run Tests

```bash
pytest -q
```

Current test coverage includes persistent memory behavior in `tests/test_memory.py`.

## Migrations (Alembic)

Alembic scaffolding (`alembic.ini`, `alembic/env.py`, `alembic/versions/`) is set up ahead of
any schema it needs to own — `SQLChatMessageHistory` (`src/agent/memory.py`) already manages its
own `message_store` table automatically, so the first migration is a no-op that just documents
that table's shape (`alembic/versions/bf40fc10c929_*.py`). This establishes the migrations
workflow now, so the next real schema need (session metadata, document metadata) has it ready
rather than retrofitting it under time pressure. See issue #36.

`alembic/env.py` builds its connection string via `build_connection_string()`
(`src/config.py`, added in #35) — `DATABASE_URL`, or the discrete
`DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` vars — the same helper `src/agent/memory.py`
is intended to be wired to (a separate, still-pending ticket), so there's exactly one place
connection details are assembled rather than two. `alembic.ini`'s `sqlalchemy.url` is deliberately
left unset.

Not part of the default `pytest` run (needs a live Postgres), runnable on demand as a manual
smoke test:

```bash
docker run --rm -d --name alembic-smoke-test \
  -e POSTGRES_PASSWORD=postgres -p 5433:5432 postgres:16

# Postgres takes a few seconds to accept connections after the container starts
until docker exec alembic-smoke-test pg_isready -U postgres -q; do sleep 1; done

DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/postgres \
  alembic upgrade head

# expect: "Running upgrade -> bf40fc10c929, document sql chat message history table"
# with no errors, and no `message_store` table created (the migration is a no-op).

docker stop alembic-smoke-test
```

## Troubleshooting

### Error: Vectorstore not found

Run:

```bash
python -m src.main ingest
```

### OpenAI quota or authentication errors

Verify:
- `OPENAI_API_KEY` is valid
- billing/quota is available

### Chat appears idle

The first startup can take longer due to initialization. Once prompt appears:

```text
You:
```

type your question and press Enter.

### SSL issues when downloading arXiv PDFs

Try one of:
- provide `--cafile <path>`
- install/update `certifi`
- use `--insecure` only for local troubleshooting

## Security

- Never commit `.env`.
- Rotate keys if they were ever exposed.
- Keep API keys scoped to least privilege where possible.

## Engineering Notes

Built iteratively, one capability per commit (ingestion → retriever → LangGraph
agent → persistent memory → FastAPI → Streamlit UI), each followed by a test
before moving on. AI coding assistants (Claude Code) were used throughout for
implementation and review, with every change run through `pytest`, `ruff`,
and `black` via pre-commit before being accepted.

### Autonomous issue implementation ("Ralph loop")

Larger feature work (e.g. the reranker in `docs/specs/fine-tuned-reranker.md`) is broken into
GitHub issues with explicit acceptance criteria and native blocking dependencies between them.
`scripts/ralph/ralph.sh` drives Claude Code headlessly and repeatedly — the "Ralph Wiggum" pattern
(one-shot, non-interactive invocations in a loop, checked against a completion sigil) — inside a
disposable Docker container (`scripts/ralph/ralph.Dockerfile`), so each run:

1. Finds the lowest-numbered open, unblocked, unassigned `ready-for-agent` issue via `gh`.
2. Claims it, implements it, and runs the full test suite/typecheck.
3. Stops for human review — it does not commit or close the issue itself.

Authentication uses a long-lived token from `claude setup-token`, tied to an existing Claude
subscription rather than metered API credits. Running inside a container means a bad iteration's
blast radius is contained to a disposable filesystem rather than the host, aside from the one
bind-mounted checkout it's deliberately allowed to change. Full instructions live in
`scripts/ralph/ralph-prompt.md`.

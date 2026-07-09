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

Optional custom paths:

```bash
python -m src.main ingest \
    --pdf-directory data/papers \
    --md-directory docs \
    --persist-directory ./chroma_db
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

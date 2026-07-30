# Lexara

A collaborative AI workspace for legal teams, in the mould of [Legora](https://legora.com):
upload a matter's documents, review them side by side in a grid, ask questions across the
whole set with citations, and measure contracts against your negotiation playbook.

Built on Flask + SQLite + the Anthropic API, with a dependency-free vanilla-JS front end.

---

## The four surfaces

### Vault
Drag in PDFs, Word files, markdown or plain text. Each upload is text-extracted, split into
overlapping paragraph-aligned chunks, and indexed. Page markers survive extraction, so every
downstream citation can point at a page. Scanned PDFs are detected and flagged as needing OCR
rather than silently landing as empty documents. There's a lexical search across the whole
matter, and a one-click AI catalogue (type, parties, effective date, governing law).

### Tabular review
The signature workflow. Documents run down the side, your questions run across the top, and
every cell is a separate grounded model call. Each answer carries:

- the extracted value, formatted for the column type (text / yes-no / date / number / currency / list)
- a **verbatim quote** and page number backing it
- a **confidence** rating, and the reasoning behind the answer

Cells run concurrently on a bounded thread pool and stream into the grid as they land. A failed
cell is recorded as failed and the rest of the run continues. You can override any answer by hand
— overrides are flagged in the UI and in the CSV export. `Suggest columns` asks the model which
questions this document set actually calls for; `Draft memo` turns the finished grid into a
partner-ready summary.

### Assistant
Matter-scoped chat. Questions are answered only from retrieved passages, streamed over SSE with
inline `[n]` markers that open the source excerpt and jump to the highlighted passage in the full
document. Scope a thread to a subset of documents when you only care about part of the matter.

### Playbook review
A playbook is the set of positions you take into a negotiation. Lexara checks a document against
every rule and returns, per rule: a status (compliant / deviation / missing / unclear), a severity,
the clause and page at issue, the verbatim language, an analysis, and **drafting-ready replacement
language**. Three playbooks ship built in (mutual NDA, SaaS agreement, employment agreement); you
can also paste your own rules. Results export as a markdown review memo.

---

## Running it

```bash
cd lexara
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

export ANTHROPIC_API_KEY=sk-ant-...
python wsgi.py                      # http://localhost:5050
```

Without an API key the app still runs — the vault, search, grid, exports and navigation all work,
and the model-backed actions return a clear "not configured" message instead of failing obscurely.

```bash
pytest                              # 81 tests, no network calls
```

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | — | Required for review, assistant, playbooks and suggestions |
| `LEXARA_MODEL` | `claude-opus-5` | Model used for every call |
| `LEXARA_EFFORT` | `high` | Reasoning effort for chat, memos and playbook reviews |
| `LEXARA_CELL_EFFORT` | `medium` | Reasoning effort per review-grid cell |
| `LEXARA_DATA_DIR` | `lexara/data` | SQLite database and uploaded files |
| `LEXARA_REVIEW_WORKERS` | `6` | Concurrent review cells in flight |
| `LEXARA_MAX_UPLOAD_MB` | `25` | Per-file upload limit |
| `LEXARA_MAX_DOC_CHARS` | `400000` | Characters retained per document |
| `LEXARA_CELL_CONTEXT_CHARS` | `120000` | Document budget handed to one review cell |

### Deploying

`lexara/Procfile` runs gunicorn with threaded workers (`gunicorn wsgi:app`), which the review pool
needs. Note that the repository root already contains a separate Flask app (the Ikigai coach) with
its own `Procfile`; **the root deployment config was left untouched**, so pointing a host at this
app means either deploying from the `lexara/` subdirectory or updating the root config yourself.

State lives in SQLite plus files on disk. On an ephemeral host, mount `LEXARA_DATA_DIR` on a volume
or the matter disappears on restart.

---

## How it works

```
app/
  config.py      environment-driven settings
  db.py          SQLite schema + short-lived connections (WAL, safe from worker threads)
  extract.py     PDF / DOCX / text → plain text with [[page N]] markers
  retrieval.py   paragraph-aligned chunking, BM25, query-centred snippets
  llm.py         Anthropic wrapper: retries, streaming, tool-use structured output
  prompts.py     system prompts + JSON schemas for each feature
  playbooks.py   the built-in negotiation playbooks
  services.py    ingest, the review worker pool, playbook runs
  routes/        workspaces · documents · review · assistant · playbooks
static/
  index.html, css/app.css, js/{api,ui,state,main}.js, js/views/*.js
```

**Retrieval is lexical, not vector.** BM25 over lightly stemmed tokens needs no second API
round-trip, is deterministic — so a citation reproduces — and legal questions tend to share
vocabulary with the clauses that answer them. Swapping in embeddings later means replacing
`retrieval.search` alone.

**Structured output goes through tool use**, not "reply with JSON". The API validates the shape,
which matters when hundreds of review cells run unattended. `llm.parse_json` is the fallback for a
model that answers in prose anyway.

**Depth is tuned with `effort`, not sampling parameters.** Current models reject
`temperature`/`top_p`/`top_k` outright and think by default, so `llm._tuning` sends
`output_config.effort` instead and every `max_tokens` budget leaves room for thinking as well as the
answer. Grid cells run at `medium` — many small, well-scoped extractions — while chat, memos and
playbook reviews run at the default `high`.

**Grounding is enforced in the prompt and visible in the UI.** Every extraction returns a quote or
says "Not addressed"; confidence is surfaced on the cell; the source panel highlights the quoted
passage inside the original text. The point is that a reviewer can check any answer in two clicks.

---

## Caveats

- Answers are model output. Every surface says so, and every claim is traceable to a quote, but
  this does not produce legal advice and nothing here removes the need for attorney review.
- Single-tenant: there is no authentication, no per-user access control, and no audit log. Anyone
  who can reach the server can read every matter.
- Scanned PDFs are flagged, not OCR'd.
- Long documents are truncated head-and-tail to fit the per-cell context budget.

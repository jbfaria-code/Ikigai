"""Work that outlives a single request: ingest, review runs, playbook runs."""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config, db, extract, llm, playbooks as playbook_registry, prompts, retrieval

log = logging.getLogger("lexara.services")

# One pool per process. Review runs are I/O-bound on the API, so threads are the
# right shape, and a bounded pool keeps us inside rate limits.
_pool = ThreadPoolExecutor(max_workers=config.REVIEW_WORKERS, thread_name_prefix="lexara")

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    name = Path(name or "document").name
    cleaned = SAFE_NAME_RE.sub("_", name).strip("._") or "document"
    return cleaned[:120]


def title_from_filename(name: str) -> str:
    stem = Path(name or "").stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    if not stem:
        return "Untitled document"
    # Only title-case names that arrived all-lowercase; leave real casing alone.
    return (stem.title() if stem.islower() else stem)[:120]


# --------------------------------------------------------------------------
# Document ingest
# --------------------------------------------------------------------------

def ingest_document(workspace_id: str, filename: str, raw: bytes) -> dict:
    """Persist an uploaded file, extract its text, and index it for search."""
    suffix = Path(filename).suffix.lower()
    if suffix not in config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{suffix or filename}'. Allowed: {allowed}")

    doc_id = db.new_id("doc")
    config.ensure_dirs()
    stored = config.UPLOAD_DIR / f"{doc_id}{suffix}"
    stored.write_bytes(raw)

    status, error, result = "ready", "", None
    try:
        result = extract.extract(stored, config.MAX_DOC_CHARS)
        if not result.text.strip():
            status = "needs_ocr" if suffix == ".pdf" else "empty"
            error = (result.warnings or ["No text could be extracted."])[0]
    except Exception as exc:  # noqa: BLE001 - surfaced to the user on the card
        log.exception("extraction failed for %s", filename)
        status, error = "failed", str(exc)

    record = {
        "id": doc_id,
        "workspace_id": workspace_id,
        "title": title_from_filename(filename),
        "filename": safe_filename(filename),
        "stored_path": str(stored),
        "kind": result.kind if result else (suffix.lstrip(".") or "unknown"),
        "size_bytes": len(raw),
        "pages": result.pages if result else 0,
        "words": result.words if result else 0,
        "text": result.text if result else "",
        "status": status,
        "error": error,
        "created_at": db.now(),
    }
    db.execute(
        """INSERT INTO documents
           (id, workspace_id, title, filename, stored_path, kind, size_bytes,
            pages, words, text, status, error, created_at)
           VALUES (:id, :workspace_id, :title, :filename, :stored_path, :kind,
                   :size_bytes, :pages, :words, :text, :status, :error, :created_at)""",
        record,
    )

    if record["text"]:
        chunks = retrieval.chunk_text(record["text"])
        db.execute_many(
            "INSERT INTO chunks (id, document_id, ordinal, page, text) VALUES (?, ?, ?, ?, ?)",
            [(db.new_id("chk"), doc_id, c.ordinal, c.page, c.text) for c in chunks],
        )

    record.pop("text")
    record.pop("stored_path")
    return record


def delete_document(document_id: str) -> None:
    row = db.query_one("SELECT stored_path FROM documents WHERE id = ?", (document_id,))
    if row:
        _unlink(row["stored_path"])
    db.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def delete_workspace_files(workspace_id: str) -> None:
    for row in db.query(
        "SELECT stored_path FROM documents WHERE workspace_id = ?", (workspace_id,)
    ):
        _unlink(row["stored_path"])


def _unlink(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not remove %s: %s", path, exc)


def document_context(document_id: str, limit: int | None = None) -> tuple[str, str]:
    """Return ``(title, text)`` for a document, trimmed to the cell budget."""
    row = db.query_one("SELECT title, text FROM documents WHERE id = ?", (document_id,))
    if not row:
        raise ValueError("Document not found.")
    text = row["text"]
    budget = limit or config.CELL_CONTEXT_CHARS
    if len(text) > budget:
        # Keep the front (parties, recitals, key terms) and the back
        # (governing law, signature blocks, schedules).
        head = int(budget * 0.7)
        tail = budget - head
        text = f"{text[:head]}\n\n[... document truncated for length ...]\n\n{text[-tail:]}"
    return row["title"], text


# --------------------------------------------------------------------------
# Tabular review
# --------------------------------------------------------------------------

_EMPTY_CELL = {
    "value": "",
    "quote": "",
    "page": 0,
    "reasoning": "",
    "confidence": "",
}


def run_cell(table_id: str, column: dict, document_id: str) -> dict:
    """Answer one column's question for one document and persist the result."""
    _write_cell(table_id, column["id"], document_id, _EMPTY_CELL | {"status": "running"})
    try:
        title, text = document_context(document_id)
        if not text.strip():
            raise ValueError("No extracted text for this document.")

        answer = llm.complete_structured(
            system=prompts.REVIEW_CELL_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": prompts.review_cell_user(
                        title, text, column["header"], column["prompt"], column["kind"]
                    ),
                }
            ],
            tool_name="extract_answer",
            description="Record the extracted answer, its supporting quote, and your confidence.",
            schema=prompts.REVIEW_CELL_SCHEMA,
            max_tokens=1024,
        )
        cell = {
            "status": "done",
            "value": str(answer.get("value", "")).strip(),
            "quote": str(answer.get("quote", "")).strip(),
            "page": int(answer.get("page") or 0),
            "reasoning": str(answer.get("reasoning", "")).strip(),
            "confidence": str(answer.get("confidence", "")).strip().lower(),
        }
    except Exception as exc:  # noqa: BLE001 - one bad cell must not stop the run
        log.warning("cell failed (%s / %s): %s", column["header"], document_id, exc)
        cell = _EMPTY_CELL | {"status": "error", "reasoning": str(exc)[:300]}

    _write_cell(table_id, column["id"], document_id, cell)
    return cell


def _write_cell(table_id: str, column_id: str, document_id: str, cell: dict) -> None:
    db.execute(
        """INSERT INTO review_cells
             (id, table_id, column_id, document_id, status, value, reasoning,
              quote, page, confidence, edited, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
           ON CONFLICT(column_id, document_id) DO UPDATE SET
             status = excluded.status, value = excluded.value,
             reasoning = excluded.reasoning, quote = excluded.quote,
             page = excluded.page, confidence = excluded.confidence,
             edited = 0, updated_at = excluded.updated_at""",
        (
            db.new_id("cell"), table_id, column_id, document_id,
            cell.get("status", "done"), cell.get("value", ""), cell.get("reasoning", ""),
            cell.get("quote", ""), int(cell.get("page") or 0), cell.get("confidence", ""),
            db.now(),
        ),
    )


def queue_cells(table_id: str, columns: list[dict], document_ids: list[str]) -> int:
    """Mark cells queued and hand them to the worker pool. Returns cell count."""
    pending = [(c, d) for c in columns for d in document_ids]
    for column, document_id in pending:
        _write_cell(table_id, column["id"], document_id, _EMPTY_CELL | {"status": "queued"})
    for column, document_id in pending:
        _pool.submit(run_cell, table_id, column, document_id)
    return len(pending)


# --------------------------------------------------------------------------
# Playbook review
# --------------------------------------------------------------------------

def run_playbook(run_id: str, document_id: str, playbook: dict) -> None:
    try:
        title, text = document_context(document_id)
        if not text.strip():
            raise ValueError("No extracted text for this document.")

        result = llm.complete_structured(
            system=prompts.PLAYBOOK_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": prompts.playbook_user(
                        title, text, playbook["name"], playbook["perspective"],
                        playbook["rules"],
                    ),
                }
            ],
            tool_name="record_review",
            description="Record the playbook review: one finding per rule, plus an overall summary.",
            schema=prompts.PLAYBOOK_SCHEMA,
            max_tokens=8192,
        )
        db.execute(
            "UPDATE playbook_runs SET status = 'done', result = ? WHERE id = ?",
            (json.dumps(result), run_id),
        )
    except Exception as exc:  # noqa: BLE001 - reported on the run record
        log.exception("playbook run failed")
        db.execute(
            "UPDATE playbook_runs SET status = 'error', error = ? WHERE id = ?",
            (str(exc)[:500], run_id),
        )


def queue_playbook(run_id: str, document_id: str, playbook: dict) -> None:
    _pool.submit(run_playbook, run_id, document_id, playbook)


def resolve_playbook(payload: dict) -> dict | None:
    """Accept either a built-in key or a fully custom playbook body."""
    key = (payload.get("playbook_key") or "").strip()
    if key:
        return playbook_registry.get(key)

    custom = payload.get("playbook") or {}
    rules = [
        {"title": str(r.get("title", "")).strip(), "standard": str(r.get("standard", "")).strip()}
        for r in custom.get("rules", [])
        if str(r.get("title", "")).strip()
    ]
    if not rules:
        return None
    return {
        "key": "custom",
        "name": (custom.get("name") or "Custom playbook").strip()[:120],
        "perspective": (custom.get("perspective") or "client").strip()[:80],
        "description": "",
        "rules": rules[:40],
    }


def shutdown() -> None:
    _pool.shutdown(wait=False)

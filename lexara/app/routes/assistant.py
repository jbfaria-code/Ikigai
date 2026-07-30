"""The assistant — grounded chat over a matter's documents, with citations."""
import json
import logging
import re

from flask import Blueprint, Response, jsonify, request, stream_with_context

from .. import db, llm, prompts, retrieval

log = logging.getLogger("lexara.assistant")

bp = Blueprint("assistant", __name__, url_prefix="/api")

MAX_HISTORY_MESSAGES = 12
MAX_EXCERPTS = 10


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@bp.get("/workspaces/<workspace_id>/threads")
def list_threads(workspace_id: str):
    threads = db.query(
        "SELECT * FROM threads WHERE workspace_id = ? ORDER BY created_at DESC",
        (workspace_id,),
    )
    return jsonify({"threads": threads})


@bp.post("/workspaces/<workspace_id>/threads")
def create_thread(workspace_id: str):
    if not db.query_one("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)):
        return jsonify({"error": "Matter not found."}), 404
    payload = request.get_json(silent=True) or {}
    thread = {
        "id": db.new_id("thr"),
        "workspace_id": workspace_id,
        "title": (payload.get("title") or "New thread").strip()[:120],
        "created_at": db.now(),
    }
    db.execute(
        "INSERT INTO threads (id, workspace_id, title, created_at) VALUES (?, ?, ?, ?)",
        (thread["id"], workspace_id, thread["title"], thread["created_at"]),
    )
    return jsonify(thread), 201


@bp.get("/threads/<thread_id>")
def get_thread(thread_id: str):
    thread = db.query_one("SELECT * FROM threads WHERE id = ?", (thread_id,))
    if not thread:
        return jsonify({"error": "Thread not found."}), 404
    messages = db.query(
        "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at, rowid", (thread_id,)
    )
    for message in messages:
        message["citations"] = db.loads(message["citations"], [])
    return jsonify({"thread": thread, "messages": messages})


@bp.delete("/threads/<thread_id>")
def delete_thread(thread_id: str):
    if not db.query_one("SELECT id FROM threads WHERE id = ?", (thread_id,)):
        return jsonify({"error": "Thread not found."}), 404
    db.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
    return jsonify({"deleted": thread_id})


def gather_excerpts(workspace_id: str, question: str, document_ids: list[str] | None) -> list[dict]:
    """Rank the matter's indexed chunks against the question."""
    sql = """SELECT c.text, c.page, c.document_id, d.title
               FROM chunks c JOIN documents d ON d.id = c.document_id
              WHERE d.workspace_id = ?"""
    params: list = [workspace_id]
    if document_ids:
        sql += f" AND c.document_id IN ({','.join('?' * len(document_ids))})"
        params.extend(document_ids)

    records = db.query(sql, tuple(params))
    hits = retrieval.search(records, question, limit=MAX_EXCERPTS)

    # Give every in-scope document at least one shot at being cited, so a
    # question that only one document answers doesn't get crowded out.
    seen = {h["document_id"] for h in hits}
    for record in records:
        if len(hits) >= MAX_EXCERPTS:
            break
        if record["document_id"] not in seen:
            hits.append(dict(record, score=0.0))
            seen.add(record["document_id"])
    return hits


def _save_message(thread_id: str, role: str, content: str, citations: list) -> str:
    message_id = db.new_id("msg")
    db.execute(
        "INSERT INTO messages (id, thread_id, role, content, citations, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, thread_id, role, content, json.dumps(citations), db.now()),
    )
    return message_id


@bp.post("/threads/<thread_id>/messages")
def send_message(thread_id: str):
    thread = db.query_one("SELECT * FROM threads WHERE id = ?", (thread_id,))
    if not thread:
        return jsonify({"error": "Thread not found."}), 404

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify({"error": "A message is required."}), 400
    if not llm.available():
        raise llm.NotConfigured("ANTHROPIC_API_KEY is not set, so the assistant is offline.")

    document_ids = payload.get("document_ids") or None
    excerpts = gather_excerpts(thread["workspace_id"], content, document_ids)
    sources = [
        {
            "n": i,
            "document_id": ex["document_id"],
            "title": ex["title"],
            "page": ex["page"],
            "snippet": retrieval.snippet(ex["text"], content, 600),
        }
        for i, ex in enumerate(excerpts, start=1)
    ]

    history = db.query(
        "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY created_at, rowid",
        (thread_id,),
    )[-MAX_HISTORY_MESSAGES:]

    _save_message(thread_id, "user", content, [])
    if thread["title"] == "New thread":
        title = content[:70] + ("…" if len(content) > 70 else "")
        db.execute("UPDATE threads SET title = ? WHERE id = ?", (title, thread_id))

    messages = [{"role": h["role"], "content": h["content"]} for h in history]
    messages.append(
        {"role": "user", "content": f"{prompts.assistant_context(excerpts)}\n\nQuestion: {content}"}
    )

    @stream_with_context
    def generate():
        yield _sse({"type": "sources", "sources": sources})
        parts: list[str] = []
        try:
            for delta in llm.stream(prompts.ASSISTANT_SYSTEM, messages, max_tokens=8000):
                parts.append(delta)
                yield _sse({"type": "delta", "text": delta})
        except Exception as exc:  # noqa: BLE001 - reported into the stream
            log.exception("assistant stream failed")
            yield _sse({"type": "error", "error": str(exc)})

        answer = "".join(parts).strip()
        if answer:
            cited = sorted({int(n) for n in _cited_numbers(answer) if 1 <= n <= len(sources)})
            used = [s for s in sources if s["n"] in cited] or sources[:3]
            message_id = _save_message(thread_id, "assistant", answer, used)
            yield _sse({"type": "done", "message_id": message_id, "citations": used})
        else:
            yield _sse({"type": "done", "message_id": None, "citations": []})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def _cited_numbers(text: str) -> list[int]:
    return [int(m) for m in CITATION_RE.findall(text)]

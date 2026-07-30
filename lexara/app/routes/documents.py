"""The vault — upload, list, read and delete matter documents."""
from flask import Blueprint, jsonify, request, send_file

from .. import config, db, extract, llm, prompts, retrieval, services

bp = Blueprint("documents", __name__, url_prefix="/api")

DOC_FIELDS = (
    "id, workspace_id, title, filename, kind, size_bytes, pages, words, "
    "status, error, created_at"
)


@bp.get("/workspaces/<workspace_id>/documents")
def list_documents(workspace_id: str):
    rows = db.query(
        f"SELECT {DOC_FIELDS} FROM documents WHERE workspace_id = ? ORDER BY created_at",
        (workspace_id,),
    )
    return jsonify({"documents": rows})


@bp.post("/workspaces/<workspace_id>/documents")
def upload_documents(workspace_id: str):
    if not db.query_one("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)):
        return jsonify({"error": "Matter not found."}), 404

    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return jsonify({"error": "No files were uploaded."}), 400

    uploaded, rejected = [], []
    for storage in files:
        raw = storage.read()
        if not raw:
            rejected.append({"filename": storage.filename, "error": "File is empty."})
            continue
        try:
            uploaded.append(services.ingest_document(workspace_id, storage.filename, raw))
        except ValueError as exc:
            rejected.append({"filename": storage.filename, "error": str(exc)})

    status = 201 if uploaded else 400
    return jsonify({"documents": uploaded, "rejected": rejected}), status


@bp.get("/documents/<document_id>")
def get_document(document_id: str):
    row = db.query_one(f"SELECT {DOC_FIELDS} FROM documents WHERE id = ?", (document_id,))
    if not row:
        return jsonify({"error": "Document not found."}), 404
    return jsonify(row)


@bp.get("/documents/<document_id>/text")
def get_document_text(document_id: str):
    row = db.query_one("SELECT title, text FROM documents WHERE id = ?", (document_id,))
    if not row:
        return jsonify({"error": "Document not found."}), 404
    return jsonify({"title": row["title"], "text": extract.strip_markers(row["text"])})


@bp.get("/documents/<document_id>/file")
def download_document(document_id: str):
    row = db.query_one(
        "SELECT stored_path, filename FROM documents WHERE id = ?", (document_id,)
    )
    if not row:
        return jsonify({"error": "Document not found."}), 404
    return send_file(row["stored_path"], as_attachment=True, download_name=row["filename"])


@bp.patch("/documents/<document_id>")
def rename_document(document_id: str):
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()[:120]
    if not title:
        return jsonify({"error": "A title is required."}), 400
    if not db.query_one("SELECT id FROM documents WHERE id = ?", (document_id,)):
        return jsonify({"error": "Document not found."}), 404
    db.execute("UPDATE documents SET title = ? WHERE id = ?", (title, document_id))
    return jsonify({"id": document_id, "title": title})


@bp.delete("/documents/<document_id>")
def delete_document(document_id: str):
    if not db.query_one("SELECT id FROM documents WHERE id = ?", (document_id,)):
        return jsonify({"error": "Document not found."}), 404
    services.delete_document(document_id)
    return jsonify({"deleted": document_id})


@bp.post("/documents/<document_id>/intake")
def intake(document_id: str):
    """Catalogue a document: type, parties, effective date, governing law."""
    row = db.query_one("SELECT title, text FROM documents WHERE id = ?", (document_id,))
    if not row:
        return jsonify({"error": "Document not found."}), 404
    if not row["text"].strip():
        return jsonify({"error": "This document has no extracted text."}), 400

    head = row["text"][:20000]
    result = llm.complete_structured(
        system=prompts.INTAKE_SYSTEM,
        messages=[{"role": "user", "content": f"<document title=\"{row['title']}\">\n{head}\n</document>"}],
        tool_name="catalogue_document",
        description="Record the document's catalogue metadata.",
        schema=prompts.INTAKE_SCHEMA,
        max_tokens=4096,
        effort=config.CELL_EFFORT,
    )
    return jsonify(result)


@bp.post("/workspaces/<workspace_id>/search")
def search_workspace(workspace_id: str):
    """Lexical search across every indexed chunk in the matter."""
    payload = request.get_json(silent=True) or {}
    question = (payload.get("query") or "").strip()
    if not question:
        return jsonify({"error": "A query is required."}), 400

    limit = min(int(payload.get("limit") or 20), 50)
    records = db.query(
        """SELECT c.id, c.text, c.page, c.document_id, d.title
             FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE d.workspace_id = ?""",
        (workspace_id,),
    )
    hits = retrieval.search(records, question, limit=limit)
    for hit in hits:
        hit["preview"] = retrieval.snippet(hit.pop("text"), question)
    return jsonify({"query": question, "results": hits})

"""Tabular review — documents down the side, questions across the top."""
import csv
import io

from flask import Blueprint, Response, jsonify, request

from .. import db, llm, prompts, services

bp = Blueprint("review", __name__, url_prefix="/api")

COLUMN_KINDS = {"text", "yes_no", "date", "number", "currency", "list"}


def _table_or_404(table_id: str):
    return db.query_one("SELECT * FROM review_tables WHERE id = ?", (table_id,))


def _columns(table_id: str) -> list[dict]:
    return db.query(
        "SELECT * FROM review_columns WHERE table_id = ? ORDER BY ordinal", (table_id,)
    )


def _rows(table_id: str) -> list[dict]:
    return db.query(
        """SELECT r.document_id, r.ordinal, d.title, d.pages, d.words, d.status, d.kind
             FROM review_rows r JOIN documents d ON d.id = r.document_id
            WHERE r.table_id = ? ORDER BY r.ordinal""",
        (table_id,),
    )


def _cells(table_id: str) -> dict[str, dict]:
    cells = db.query("SELECT * FROM review_cells WHERE table_id = ?", (table_id,))
    return {f"{c['column_id']}:{c['document_id']}": c for c in cells}


def _snapshot(table: dict) -> dict:
    columns, rows, cells = _columns(table["id"]), _rows(table["id"]), _cells(table["id"])
    statuses = [c["status"] for c in cells.values()]
    total = len(columns) * len(rows)
    return {
        "table": table,
        "columns": columns,
        "rows": rows,
        "cells": cells,
        "progress": {
            "total": total,
            "done": sum(1 for s in statuses if s == "done"),
            "error": sum(1 for s in statuses if s == "error"),
            "pending": sum(1 for s in statuses if s in {"queued", "running"}),
            "running": any(s in {"queued", "running"} for s in statuses),
        },
    }


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

@bp.get("/workspaces/<workspace_id>/tables")
def list_tables(workspace_id: str):
    tables = db.query(
        "SELECT * FROM review_tables WHERE workspace_id = ? ORDER BY created_at DESC",
        (workspace_id,),
    )
    for table in tables:
        table["column_count"] = len(_columns(table["id"]))
        table["row_count"] = len(_rows(table["id"]))
    return jsonify({"tables": tables})


@bp.post("/workspaces/<workspace_id>/tables")
def create_table(workspace_id: str):
    if not db.query_one("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)):
        return jsonify({"error": "Matter not found."}), 404

    payload = request.get_json(silent=True) or {}
    table = {
        "id": db.new_id("tbl"),
        "workspace_id": workspace_id,
        "name": (payload.get("name") or "Untitled review").strip()[:120],
        "created_at": db.now(),
    }
    db.execute(
        "INSERT INTO review_tables (id, workspace_id, name, created_at) VALUES (?, ?, ?, ?)",
        (table["id"], workspace_id, table["name"], table["created_at"]),
    )

    document_ids = payload.get("document_ids")
    if document_ids is None:
        document_ids = [
            r["id"]
            for r in db.query(
                "SELECT id FROM documents WHERE workspace_id = ? AND status = 'ready' ORDER BY created_at",
                (workspace_id,),
            )
        ]
    _set_rows(table["id"], document_ids)

    for spec in payload.get("columns") or []:
        _insert_column(table["id"], spec)

    return jsonify(_snapshot(table)), 201


@bp.get("/tables/<table_id>")
def get_table(table_id: str):
    table = _table_or_404(table_id)
    if not table:
        return jsonify({"error": "Review table not found."}), 404
    return jsonify(_snapshot(table))


@bp.patch("/tables/<table_id>")
def update_table(table_id: str):
    table = _table_or_404(table_id)
    if not table:
        return jsonify({"error": "Review table not found."}), 404
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or table["name"]).strip()[:120]
    db.execute("UPDATE review_tables SET name = ? WHERE id = ?", (name, table_id))
    return jsonify({"id": table_id, "name": name})


@bp.delete("/tables/<table_id>")
def delete_table(table_id: str):
    if not _table_or_404(table_id):
        return jsonify({"error": "Review table not found."}), 404
    db.execute("DELETE FROM review_tables WHERE id = ?", (table_id,))
    return jsonify({"deleted": table_id})


# --------------------------------------------------------------------------
# Rows and columns
# --------------------------------------------------------------------------

def _set_rows(table_id: str, document_ids: list[str]) -> None:
    db.execute("DELETE FROM review_rows WHERE table_id = ?", (table_id,))
    seen, entries = set(), []
    for ordinal, document_id in enumerate(document_ids):
        if document_id in seen:
            continue
        seen.add(document_id)
        entries.append((db.new_id("row"), table_id, document_id, ordinal))
    if entries:
        db.execute_many(
            "INSERT INTO review_rows (id, table_id, document_id, ordinal) VALUES (?, ?, ?, ?)",
            entries,
        )
    # Cells for documents no longer in the table are meaningless.
    if seen:
        placeholders = ",".join("?" * len(seen))
        db.execute(
            f"DELETE FROM review_cells WHERE table_id = ? AND document_id NOT IN ({placeholders})",
            (table_id, *seen),
        )
    else:
        db.execute("DELETE FROM review_cells WHERE table_id = ?", (table_id,))


def _insert_column(table_id: str, spec: dict) -> dict | None:
    header = (spec.get("header") or "").strip()[:80]
    prompt = (spec.get("prompt") or "").strip()[:2000] or header
    if not header:
        return None
    kind = (spec.get("kind") or "text").strip()
    if kind not in COLUMN_KINDS:
        kind = "text"

    highest = db.query_one(
        "SELECT MAX(ordinal) AS m FROM review_columns WHERE table_id = ?", (table_id,)
    )
    column = {
        "id": db.new_id("col"),
        "table_id": table_id,
        "ordinal": (highest["m"] + 1) if highest and highest["m"] is not None else 0,
        "header": header,
        "prompt": prompt,
        "kind": kind,
        "created_at": db.now(),
    }
    db.execute(
        """INSERT INTO review_columns (id, table_id, ordinal, header, prompt, kind, created_at)
           VALUES (:id, :table_id, :ordinal, :header, :prompt, :kind, :created_at)""",
        column,
    )
    return column


@bp.put("/tables/<table_id>/rows")
def set_rows(table_id: str):
    if not _table_or_404(table_id):
        return jsonify({"error": "Review table not found."}), 404
    payload = request.get_json(silent=True) or {}
    _set_rows(table_id, payload.get("document_ids") or [])
    return jsonify({"rows": _rows(table_id)})


@bp.post("/tables/<table_id>/columns")
def add_column(table_id: str):
    table = _table_or_404(table_id)
    if not table:
        return jsonify({"error": "Review table not found."}), 404

    payload = request.get_json(silent=True) or {}
    specs = payload.get("columns") or [payload]
    created = [c for c in (_insert_column(table_id, s) for s in specs) if c]
    if not created:
        return jsonify({"error": "Each column needs a header."}), 400

    if payload.get("run", True) and llm.available():
        document_ids = [r["document_id"] for r in _rows(table_id)]
        if document_ids:
            services.queue_cells(table_id, created, document_ids)

    return jsonify({"columns": created, "snapshot": _snapshot(table)}), 201


@bp.patch("/columns/<column_id>")
def update_column(column_id: str):
    column = db.query_one("SELECT * FROM review_columns WHERE id = ?", (column_id,))
    if not column:
        return jsonify({"error": "Column not found."}), 404

    payload = request.get_json(silent=True) or {}
    header = (payload.get("header") or column["header"]).strip()[:80]
    prompt = (payload.get("prompt") or column["prompt"]).strip()[:2000]
    kind = payload.get("kind") or column["kind"]
    if kind not in COLUMN_KINDS:
        kind = column["kind"]
    db.execute(
        "UPDATE review_columns SET header = ?, prompt = ?, kind = ? WHERE id = ?",
        (header, prompt, kind, column_id),
    )
    return jsonify({"id": column_id, "header": header, "prompt": prompt, "kind": kind})


@bp.delete("/columns/<column_id>")
def delete_column(column_id: str):
    if not db.query_one("SELECT id FROM review_columns WHERE id = ?", (column_id,)):
        return jsonify({"error": "Column not found."}), 404
    db.execute("DELETE FROM review_columns WHERE id = ?", (column_id,))
    return jsonify({"deleted": column_id})


@bp.post("/tables/<table_id>/suggest-columns")
def suggest_columns(table_id: str):
    """Ask the model which columns this document set calls for."""
    table = _table_or_404(table_id)
    if not table:
        return jsonify({"error": "Review table not found."}), 404

    rows = _rows(table_id)
    if not rows:
        return jsonify({"error": "Add documents to the table first."}), 400

    previews = []
    for row in rows[:8]:
        doc = db.query_one("SELECT title, text FROM documents WHERE id = ?", (row["document_id"],))
        previews.append(f"<document title=\"{doc['title']}\">\n{doc['text'][:3000]}\n</document>")

    existing = [c["header"] for c in _columns(table_id)]
    instruction = (
        "Propose 6 to 10 review columns for this document set."
        + (f" Do not repeat these existing columns: {', '.join(existing)}." if existing else "")
    )
    result = llm.complete_structured(
        system=prompts.COLUMN_SUGGEST_SYSTEM,
        messages=[{"role": "user", "content": "\n\n".join(previews) + "\n\n" + instruction}],
        tool_name="propose_columns",
        description="Propose the review columns for this document set.",
        schema=prompts.COLUMN_SUGGEST_SCHEMA,
        max_tokens=4096,
    )
    return jsonify({"columns": result.get("columns", [])})


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------

@bp.post("/tables/<table_id>/run")
def run_table(table_id: str):
    """Queue cells for extraction. Scope with column_ids / document_ids."""
    table = _table_or_404(table_id)
    if not table:
        return jsonify({"error": "Review table not found."}), 404
    if not llm.available():
        raise llm.NotConfigured(
            "ANTHROPIC_API_KEY is not set, so the review cannot run."
        )

    payload = request.get_json(silent=True) or {}
    columns = _columns(table_id)
    rows = _rows(table_id)
    if not columns or not rows:
        return jsonify({"error": "The table needs at least one document and one column."}), 400

    wanted_columns = set(payload.get("column_ids") or [])
    wanted_docs = set(payload.get("document_ids") or [])
    if wanted_columns:
        columns = [c for c in columns if c["id"] in wanted_columns]
    document_ids = [r["document_id"] for r in rows if not wanted_docs or r["document_id"] in wanted_docs]

    if payload.get("only_empty"):
        cells = _cells(table_id)
        pairs = [
            (c, d)
            for c in columns
            for d in document_ids
            if cells.get(f"{c['id']}:{d}", {}).get("status") not in {"done", "running", "queued"}
        ]
        queued = 0
        for column, document_id in pairs:
            queued += services.queue_cells(table_id, [column], [document_id])
    else:
        queued = services.queue_cells(table_id, columns, document_ids)

    return jsonify({"queued": queued, "snapshot": _snapshot(table)})


@bp.get("/tables/<table_id>/progress")
def progress(table_id: str):
    table = _table_or_404(table_id)
    if not table:
        return jsonify({"error": "Review table not found."}), 404
    snapshot = _snapshot(table)
    return jsonify({"progress": snapshot["progress"], "cells": snapshot["cells"]})


@bp.patch("/tables/<table_id>/cells/<column_id>/<document_id>")
def edit_cell(table_id: str, column_id: str, document_id: str):
    """Lawyer overrides the model's answer; the edit is flagged in exports."""
    payload = request.get_json(silent=True) or {}
    value = (payload.get("value") or "").strip()
    db.execute(
        """INSERT INTO review_cells
             (id, table_id, column_id, document_id, status, value, reasoning,
              quote, page, confidence, edited, updated_at)
           VALUES (?, ?, ?, ?, 'done', ?, '', '', 0, 'high', 1, ?)
           ON CONFLICT(column_id, document_id) DO UPDATE SET
             status = 'done', value = excluded.value, edited = 1,
             updated_at = excluded.updated_at""",
        (db.new_id("cell"), table_id, column_id, document_id, value, db.now()),
    )
    cell = db.query_one(
        "SELECT * FROM review_cells WHERE column_id = ? AND document_id = ?",
        (column_id, document_id),
    )
    return jsonify(cell)


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

def build_csv(table_id: str, include_sources: bool = True) -> str:
    columns, rows, cells = _columns(table_id), _rows(table_id), _cells(table_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    header = ["Document"]
    for column in columns:
        header.append(column["header"])
        if include_sources:
            header.append(f"{column['header']} — source")
    writer.writerow(header)

    for row in rows:
        line = [row["title"]]
        for column in columns:
            cell = cells.get(f"{column['id']}:{row['document_id']}", {})
            line.append(cell.get("value", ""))
            if include_sources:
                quote = cell.get("quote", "")
                page = cell.get("page") or 0
                source = f"p.{page}: {quote}" if page and quote else quote
                if cell.get("edited"):
                    source = "[edited by reviewer] " + source
                line.append(source)
        writer.writerow(line)

    return buffer.getvalue()


@bp.get("/tables/<table_id>/export.csv")
def export_csv(table_id: str):
    table = _table_or_404(table_id)
    if not table:
        return jsonify({"error": "Review table not found."}), 404
    include_sources = request.args.get("sources", "1") != "0"
    filename = (table["name"] or "review").replace('"', "").replace("/", "-")
    return Response(
        build_csv(table_id, include_sources),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


def build_grid_markdown(table_id: str) -> str:
    columns, rows, cells = _columns(table_id), _rows(table_id), _cells(table_id)
    lines = []
    for row in rows:
        lines.append(f"### {row['title']}")
        for column in columns:
            cell = cells.get(f"{column['id']}:{row['document_id']}", {})
            value = cell.get("value") or "(not run)"
            confidence = cell.get("confidence") or "n/a"
            quote = (cell.get("quote") or "").replace("\n", " ")[:240]
            lines.append(f"- **{column['header']}**: {value}  _(confidence: {confidence})_")
            if quote:
                lines.append(f"  - source: \"{quote}\"")
        lines.append("")
    return "\n".join(lines)


@bp.post("/tables/<table_id>/memo")
def memo(table_id: str):
    """Draft the summary memo that accompanies the completed grid."""
    table = _table_or_404(table_id)
    if not table:
        return jsonify({"error": "Review table not found."}), 404

    answered = any(cell["status"] == "done" for cell in _cells(table_id).values())
    if not answered:
        return jsonify({"error": "Run the review before drafting a memo."}), 400
    grid = build_grid_markdown(table_id)

    payload = request.get_json(silent=True) or {}
    focus = (payload.get("focus") or "").strip()
    instruction = f"\n\nThe partner specifically wants: {focus}" if focus else ""
    text = llm.complete(
        system=prompts.MEMO_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Review: {table['name']}\n\n{grid}{instruction}",
            }
        ],
        max_tokens=8000,
    )
    return jsonify({"memo": text})

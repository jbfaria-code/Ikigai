"""Matters (workspaces) — the top-level container for documents and work."""
from flask import Blueprint, jsonify, request

from .. import db

bp = Blueprint("workspaces", __name__, url_prefix="/api/workspaces")


def counts_for(workspace_id: str) -> dict:
    docs = db.query_one(
        "SELECT COUNT(*) AS n FROM documents WHERE workspace_id = ?", (workspace_id,)
    )
    tables = db.query_one(
        "SELECT COUNT(*) AS n FROM review_tables WHERE workspace_id = ?", (workspace_id,)
    )
    return {"documents": docs["n"], "tables": tables["n"]}


@bp.get("")
def list_workspaces():
    rows = db.query("SELECT * FROM workspaces ORDER BY created_at DESC")
    for row in rows:
        row["counts"] = counts_for(row["id"])
    return jsonify({"workspaces": rows})


@bp.post("")
def create_workspace():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "A matter name is required."}), 400

    workspace = {
        "id": db.new_id("ws"),
        "name": name[:120],
        "client": (payload.get("client") or "").strip()[:120],
        "created_at": db.now(),
    }
    db.execute(
        "INSERT INTO workspaces (id, name, client, created_at) VALUES (?, ?, ?, ?)",
        (workspace["id"], workspace["name"], workspace["client"], workspace["created_at"]),
    )
    workspace["counts"] = {"documents": 0, "tables": 0}
    return jsonify(workspace), 201


@bp.get("/<workspace_id>")
def get_workspace(workspace_id: str):
    row = db.query_one("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
    if not row:
        return jsonify({"error": "Matter not found."}), 404
    row["counts"] = counts_for(workspace_id)
    return jsonify(row)


@bp.patch("/<workspace_id>")
def rename_workspace(workspace_id: str):
    payload = request.get_json(silent=True) or {}
    row = db.query_one("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
    if not row:
        return jsonify({"error": "Matter not found."}), 404

    name = (payload.get("name") or row["name"]).strip()[:120]
    client = payload.get("client")
    client = row["client"] if client is None else client.strip()[:120]
    db.execute(
        "UPDATE workspaces SET name = ?, client = ? WHERE id = ?",
        (name, client, workspace_id),
    )
    return jsonify({"id": workspace_id, "name": name, "client": client})


@bp.delete("/<workspace_id>")
def delete_workspace(workspace_id: str):
    from ..services import delete_workspace_files

    if not db.query_one("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)):
        return jsonify({"error": "Matter not found."}), 404
    delete_workspace_files(workspace_id)
    db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    return jsonify({"deleted": workspace_id})

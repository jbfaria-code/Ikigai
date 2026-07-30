"""Playbook review — measure a document against a set of negotiation positions."""
from flask import Blueprint, Response, jsonify, request

from .. import db, llm, playbooks as registry, services

bp = Blueprint("playbooks", __name__, url_prefix="/api")

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}
STATUS_LABEL = {
    "deviation": "Deviation",
    "missing": "Missing",
    "unclear": "Unclear",
    "compliant": "Compliant",
}


@bp.get("/playbooks")
def list_playbooks():
    return jsonify({"playbooks": registry.list_playbooks()})


@bp.get("/playbooks/<key>")
def get_playbook(key: str):
    playbook = registry.get(key)
    if not playbook:
        return jsonify({"error": "Playbook not found."}), 404
    return jsonify(playbook)


@bp.get("/workspaces/<workspace_id>/reviews")
def list_runs(workspace_id: str):
    runs = db.query(
        """SELECT r.id, r.document_id, r.playbook_key, r.playbook_name, r.status,
                  r.error, r.created_at, d.title AS document_title
             FROM playbook_runs r JOIN documents d ON d.id = r.document_id
            WHERE r.workspace_id = ? ORDER BY r.created_at DESC""",
        (workspace_id,),
    )
    return jsonify({"reviews": runs})


@bp.post("/documents/<document_id>/review")
def start_review(document_id: str):
    document = db.query_one(
        "SELECT id, workspace_id, title, text FROM documents WHERE id = ?", (document_id,)
    )
    if not document:
        return jsonify({"error": "Document not found."}), 404
    if not document["text"].strip():
        return jsonify({"error": "This document has no extracted text to review."}), 400
    if not llm.available():
        raise llm.NotConfigured("ANTHROPIC_API_KEY is not set, so reviews cannot run.")

    payload = request.get_json(silent=True) or {}
    playbook = services.resolve_playbook(payload)
    if not playbook:
        return jsonify({"error": "Choose a playbook, or supply one with at least one rule."}), 400

    run = {
        "id": db.new_id("run"),
        "workspace_id": document["workspace_id"],
        "document_id": document_id,
        "playbook_key": playbook["key"],
        "playbook_name": playbook["name"],
        "created_at": db.now(),
    }
    db.execute(
        """INSERT INTO playbook_runs
             (id, workspace_id, document_id, playbook_key, playbook_name, status, result, error, created_at)
           VALUES (:id, :workspace_id, :document_id, :playbook_key, :playbook_name, 'running', '{}', '', :created_at)""",
        run,
    )
    services.queue_playbook(run["id"], document_id, playbook)
    return jsonify({**run, "status": "running", "document_title": document["title"]}), 202


def _load_run(run_id: str) -> dict | None:
    run = db.query_one(
        """SELECT r.*, d.title AS document_title
             FROM playbook_runs r JOIN documents d ON d.id = r.document_id
            WHERE r.id = ?""",
        (run_id,),
    )
    if not run:
        return None
    result = db.loads(run.pop("result"), {})
    findings = result.get("findings") or []
    findings.sort(key=lambda f: SEVERITY_ORDER.get(str(f.get("severity", "none")).lower(), 4))
    run["summary"] = result.get("summary", "")
    run["recommendation"] = result.get("recommendation", "")
    run["findings"] = findings
    run["counts"] = {
        key: sum(1 for f in findings if f.get("status") == key)
        for key in ("deviation", "missing", "unclear", "compliant")
    }
    return run


@bp.get("/reviews/<run_id>")
def get_run(run_id: str):
    run = _load_run(run_id)
    if not run:
        return jsonify({"error": "Review not found."}), 404
    return jsonify(run)


@bp.delete("/reviews/<run_id>")
def delete_run(run_id: str):
    if not db.query_one("SELECT id FROM playbook_runs WHERE id = ?", (run_id,)):
        return jsonify({"error": "Review not found."}), 404
    db.execute("DELETE FROM playbook_runs WHERE id = ?", (run_id,))
    return jsonify({"deleted": run_id})


def build_review_markdown(run: dict) -> str:
    lines = [
        f"# Contract review — {run['document_title']}",
        "",
        f"**Playbook:** {run['playbook_name']}  ",
        f"**Recommendation:** {(run['recommendation'] or 'n/a').title()}  ",
        f"**Reviewed:** {run['created_at']}",
        "",
        "## Summary",
        "",
        run["summary"] or "_No summary produced._",
        "",
        "## Findings",
        "",
    ]
    for finding in run["findings"]:
        status = STATUS_LABEL.get(finding.get("status", ""), finding.get("status", ""))
        severity = str(finding.get("severity", "none")).title()
        clause = finding.get("clause") or "—"
        page = finding.get("page") or 0
        location = f"{clause}" + (f", p.{page}" if page else "")
        lines += [
            f"### {finding.get('rule', 'Rule')}",
            "",
            f"- **Status:** {status}  ",
            f"- **Severity:** {severity}  ",
            f"- **Location:** {location}",
            "",
        ]
        if finding.get("quote"):
            quoted = "\n".join(f"> {line}" for line in finding["quote"].splitlines())
            lines += [quoted, ""]
        if finding.get("analysis"):
            lines += [finding["analysis"], ""]
        if finding.get("redline"):
            lines += ["**Proposed language**", "", "```", finding["redline"], "```", ""]

    lines += [
        "---",
        "",
        "_Generated by Lexara from an AI review. Verify against the source "
        "document before relying on it._",
    ]
    return "\n".join(lines)


@bp.get("/reviews/<run_id>/export.md")
def export_review(run_id: str):
    run = _load_run(run_id)
    if not run:
        return jsonify({"error": "Review not found."}), 404
    if run["status"] != "done":
        return jsonify({"error": "The review has not finished."}), 409

    filename = run["document_title"].replace('"', "").replace("/", "-")
    return Response(
        build_review_markdown(run),
        mimetype="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename} — review.md"'},
    )

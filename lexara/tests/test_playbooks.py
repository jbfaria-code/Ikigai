import time

import pytest

from app import llm, playbooks, services

RESULT = {
    "summary": "A short mutual NDA on broadly market terms, with one problem clause.",
    "recommendation": "negotiate",
    "findings": [
        {
            "rule": "Non-solicitation and exclusivity",
            "status": "deviation",
            "severity": "high",
            "clause": "Clause 4",
            "page": 1,
            "quote": "For twelve (12) months neither party shall solicit the employees of the other.",
            "analysis": "An NDA should not carry a non-solicit.",
            "redline": "Delete clause 4 in its entirety.",
        },
        {
            "rule": "Governing law and forum",
            "status": "compliant",
            "severity": "none",
            "clause": "Clause 3",
            "page": 1,
            "quote": "governed by the laws of England and Wales",
            "analysis": "Within our accepted jurisdictions.",
            "redline": "",
        },
    ],
}


def wait_for(client, run_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/reviews/{run_id}").get_json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    pytest.fail("playbook run did not finish within the timeout")


def test_built_in_playbooks_are_listed(client):
    listed = client.get("/api/playbooks").get_json()["playbooks"]
    keys = {p["key"] for p in listed}
    assert {"mutual_nda", "saas_msa", "employment"} <= keys
    assert all(p["rule_count"] > 0 for p in listed)


def test_every_playbook_rule_has_a_standard():
    for playbook in playbooks.PLAYBOOKS.values():
        assert playbook["perspective"]
        for rule in playbook["rules"]:
            assert rule["title"].strip()
            assert rule["standard"].strip()


def test_unknown_playbook_404s(client):
    assert client.get("/api/playbooks/nope").status_code == 404


def test_review_run_produces_sorted_findings(client, document, fake_llm):
    fake_llm.tool_result = RESULT
    started = client.post(f"/api/documents/{document}/review", json={"playbook_key": "mutual_nda"})
    assert started.status_code == 202

    run = wait_for(client, started.get_json()["id"])

    assert run["status"] == "done"
    assert run["recommendation"] == "negotiate"
    # high severity sorts to the top
    assert run["findings"][0]["severity"] == "high"
    assert run["counts"] == {"deviation": 1, "missing": 0, "unclear": 0, "compliant": 1}


def test_the_playbook_rules_reach_the_model(client, document, fake_llm):
    fake_llm.tool_result = RESULT
    started = client.post(f"/api/documents/{document}/review", json={"playbook_key": "mutual_nda"})
    wait_for(client, started.get_json()["id"])

    prompt = fake_llm.calls[-1]["messages"][0]["content"]
    assert "Non-solicitation and exclusivity" in prompt
    assert "We act for the receiving party." in prompt
    assert "MUTUAL NON-DISCLOSURE" in prompt


def test_custom_playbook_rules_are_accepted(client, document, fake_llm):
    fake_llm.tool_result = RESULT
    started = client.post(f"/api/documents/{document}/review", json={
        "playbook": {
            "name": "House rules",
            "perspective": "buyer",
            "rules": [{"title": "Audit rights", "standard": "Annual audit on notice."}],
        }
    })
    run = wait_for(client, started.get_json()["id"])

    assert run["playbook_name"] == "House rules"
    assert "Audit rights" in fake_llm.calls[-1]["messages"][0]["content"]


def test_a_playbook_without_rules_is_rejected(client, document, fake_llm):
    response = client.post(f"/api/documents/{document}/review", json={"playbook": {"rules": []}})
    assert response.status_code == 400


def test_a_failed_run_records_the_error(client, document, fake_llm):
    fake_llm.raise_with = RuntimeError("model unavailable")
    started = client.post(f"/api/documents/{document}/review", json={"playbook_key": "mutual_nda"})
    run = wait_for(client, started.get_json()["id"])

    assert run["status"] == "error"
    assert "model unavailable" in run["error"]


def test_review_needs_an_api_key(client, document):
    response = client.post(f"/api/documents/{document}/review", json={"playbook_key": "mutual_nda"})
    assert response.status_code == 503


def test_markdown_export_carries_findings_and_redlines(client, document, fake_llm):
    fake_llm.tool_result = RESULT
    started = client.post(f"/api/documents/{document}/review", json={"playbook_key": "mutual_nda"})
    run_id = started.get_json()["id"]
    wait_for(client, run_id)

    body = client.get(f"/api/reviews/{run_id}/export.md").get_data(as_text=True)
    assert "# Contract review — Nda Northwind" in body
    assert "**Recommendation:** Negotiate" in body
    assert "Delete clause 4 in its entirety." in body
    assert "requires attorney verification" not in body  # that line belongs to the memo
    assert "Verify against the source" in body


def test_export_before_the_run_finishes_is_a_conflict(client, document, fake_llm):
    from app import db

    started = client.post(f"/api/documents/{document}/review", json={"playbook_key": "mutual_nda"})
    run_id = started.get_json()["id"]
    wait_for(client, run_id)
    db.execute("UPDATE playbook_runs SET status = 'running' WHERE id = ?", (run_id,))

    assert client.get(f"/api/reviews/{run_id}/export.md").status_code == 409


def test_runs_are_listed_for_the_workspace(client, workspace, document, fake_llm):
    fake_llm.tool_result = RESULT
    started = client.post(f"/api/documents/{document}/review", json={"playbook_key": "mutual_nda"})
    wait_for(client, started.get_json()["id"])

    runs = client.get(f"/api/workspaces/{workspace}/reviews").get_json()["reviews"]
    assert len(runs) == 1
    assert runs[0]["document_title"] == "Nda Northwind"


def test_resolve_playbook_trims_and_caps_custom_rules():
    resolved = services.resolve_playbook({
        "playbook": {"rules": [{"title": f"Rule {i}", "standard": "s"} for i in range(60)]}
    })
    assert len(resolved["rules"]) == 40
    assert services.resolve_playbook({"playbook_key": "mutual_nda"})["key"] == "mutual_nda"
    assert services.resolve_playbook({}) is None

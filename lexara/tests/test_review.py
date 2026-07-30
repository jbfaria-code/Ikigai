import time

import pytest


def wait_until_idle(client, table_id, timeout=10.0):
    """Block until the worker pool has drained the table's queued cells."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        progress = client.get(f"/api/tables/{table_id}/progress").get_json()["progress"]
        if not progress["running"]:
            return progress
        time.sleep(0.05)
    pytest.fail("review did not finish within the timeout")


@pytest.fixture()
def table(client, workspace, document):
    return client.post(
        f"/api/workspaces/{workspace}/tables",
        json={"name": "NDA review", "document_ids": [document]},
    ).get_json()["table"]["id"]


def test_new_table_defaults_to_every_ready_document(client, workspace, document):
    snapshot = client.post(f"/api/workspaces/{workspace}/tables", json={}).get_json()
    assert [r["document_id"] for r in snapshot["rows"]] == [document]
    assert snapshot["progress"]["total"] == 0


def test_columns_are_added_in_order(client, table):
    client.post(f"/api/tables/{table}/columns", json={
        "columns": [
            {"header": "Governing law", "prompt": "What law governs?", "kind": "text"},
            {"header": "Term", "prompt": "How long does confidentiality last?", "kind": "text"},
        ],
        "run": False,
    })
    columns = client.get(f"/api/tables/{table}").get_json()["columns"]
    assert [c["header"] for c in columns] == ["Governing law", "Term"]
    assert [c["ordinal"] for c in columns] == [0, 1]


def test_column_requires_a_header(client, table):
    response = client.post(f"/api/tables/{table}/columns", json={"columns": [{"prompt": "x"}]})
    assert response.status_code == 400


def test_unknown_column_kind_falls_back_to_text(client, table):
    client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "Odd", "prompt": "?", "kind": "hologram"}], "run": False,
    })
    assert client.get(f"/api/tables/{table}").get_json()["columns"][0]["kind"] == "text"


def test_run_fills_cells_with_answers_and_sources(client, table, document, fake_llm):
    fake_llm.tool_result = {
        "value": "England and Wales",
        "quote": "This Agreement is governed by the laws of England and Wales",
        "page": 1,
        "reasoning": "Clause 3 states the governing law expressly.",
        "confidence": "high",
    }
    added = client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "Governing law", "prompt": "What law governs?", "kind": "text"}],
        "run": False,
    }).get_json()["columns"][0]

    client.post(f"/api/tables/{table}/run", json={})
    wait_until_idle(client, table)

    cells = client.get(f"/api/tables/{table}").get_json()["cells"]
    cell = cells[f"{added['id']}:{document}"]
    assert cell["status"] == "done"
    assert cell["value"] == "England and Wales"
    assert cell["confidence"] == "high"
    assert cell["page"] == 1
    assert cell["edited"] == 0


def test_the_document_text_reaches_the_model(client, table, fake_llm):
    fake_llm.tool_result = {"value": "x", "quote": "", "page": 0, "reasoning": "", "confidence": "low"}
    client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "Parties", "prompt": "Who are the parties?", "kind": "list"}],
        "run": False,
    })
    client.post(f"/api/tables/{table}/run", json={})
    wait_until_idle(client, table)

    prompt = fake_llm.calls[-1]["messages"][0]["content"]
    assert "Northwind Holdings Limited" in prompt
    assert "Who are the parties?" in prompt
    assert "<type>list</type>" in prompt


def test_a_failing_cell_is_recorded_without_stopping_the_run(client, table, document, fake_llm):
    fake_llm.raise_with = RuntimeError("upstream exploded")
    added = client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "Term", "prompt": "How long?", "kind": "text"}], "run": False,
    }).get_json()["columns"][0]

    client.post(f"/api/tables/{table}/run", json={})
    progress = wait_until_idle(client, table)

    assert progress["error"] == 1
    cell = client.get(f"/api/tables/{table}").get_json()["cells"][f"{added['id']}:{document}"]
    assert cell["status"] == "error"
    assert "upstream exploded" in cell["reasoning"]


def test_only_empty_skips_cells_that_already_have_answers(client, table, document, fake_llm):
    fake_llm.tool_result = {"value": "v", "quote": "", "page": 0, "reasoning": "", "confidence": "high"}
    client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "A", "prompt": "a?", "kind": "text"}], "run": False,
    })
    client.post(f"/api/tables/{table}/run", json={})
    wait_until_idle(client, table)
    calls_after_first_run = len(fake_llm.calls)

    queued = client.post(f"/api/tables/{table}/run", json={"only_empty": True}).get_json()["queued"]
    assert queued == 0
    assert len(fake_llm.calls) == calls_after_first_run


def test_run_can_be_scoped_to_one_column(client, table, fake_llm):
    fake_llm.tool_result = {"value": "v", "quote": "", "page": 0, "reasoning": "", "confidence": "high"}
    first = client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "A", "prompt": "a?"}, {"header": "B", "prompt": "b?"}], "run": False,
    }).get_json()["columns"][0]

    queued = client.post(f"/api/tables/{table}/run", json={"column_ids": [first["id"]]}).get_json()["queued"]
    wait_until_idle(client, table)
    assert queued == 1


def test_run_without_an_api_key_is_a_503(client, table):
    client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "A", "prompt": "a?"}], "run": False,
    })
    assert client.post(f"/api/tables/{table}/run", json={}).status_code == 503


def test_run_needs_columns_and_rows(client, table, fake_llm):
    assert client.post(f"/api/tables/{table}/run", json={}).status_code == 400


def test_manual_override_marks_the_cell_edited(client, table, document, fake_llm):
    fake_llm.tool_result = {"value": "wrong", "quote": "", "page": 0, "reasoning": "", "confidence": "low"}
    column = client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "A", "prompt": "a?"}], "run": False,
    }).get_json()["columns"][0]
    client.post(f"/api/tables/{table}/run", json={})
    wait_until_idle(client, table)

    cell = client.patch(
        f"/api/tables/{table}/cells/{column['id']}/{document}", json={"value": "corrected"}
    ).get_json()

    assert cell["value"] == "corrected"
    assert cell["edited"] == 1


def test_changing_rows_discards_orphaned_cells(client, workspace, table, document, fake_llm):
    fake_llm.tool_result = {"value": "v", "quote": "", "page": 0, "reasoning": "", "confidence": "high"}
    client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "A", "prompt": "a?"}], "run": False,
    })
    client.post(f"/api/tables/{table}/run", json={})
    wait_until_idle(client, table)
    assert client.get(f"/api/tables/{table}").get_json()["cells"]

    client.put(f"/api/tables/{table}/rows", json={"document_ids": []})
    snapshot = client.get(f"/api/tables/{table}").get_json()
    assert snapshot["rows"] == []
    assert snapshot["cells"] == {}


def test_csv_export_includes_values_and_sources(client, table, fake_llm):
    fake_llm.tool_result = {
        "value": "England and Wales",
        "quote": "governed by the laws of England and Wales",
        "page": 2,
        "reasoning": "",
        "confidence": "high",
    }
    client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "Governing law", "prompt": "What law governs?"}], "run": False,
    })
    client.post(f"/api/tables/{table}/run", json={})
    wait_until_idle(client, table)

    body = client.get(f"/api/tables/{table}/export.csv").get_data(as_text=True)
    assert "Document,Governing law,Governing law — source" in body
    assert "England and Wales" in body
    assert "p.2:" in body

    plain = client.get(f"/api/tables/{table}/export.csv?sources=0").get_data(as_text=True)
    assert "— source" not in plain


def test_column_suggestions_come_back_as_specs(client, table, fake_llm):
    fake_llm.tool_result = {"columns": [
        {"header": "Governing law", "prompt": "What law governs?", "kind": "text"},
    ]}
    data = client.post(f"/api/tables/{table}/suggest-columns", json={}).get_json()
    assert data["columns"][0]["header"] == "Governing law"


def test_suggestions_need_documents(client, workspace):
    empty = client.post(f"/api/workspaces/{workspace}/tables", json={"document_ids": []}).get_json()
    response = client.post(f"/api/tables/{empty['table']['id']}/suggest-columns", json={})
    assert response.status_code == 400


def test_memo_uses_the_completed_grid(client, table, fake_llm):
    fake_llm.tool_result = {
        "value": "England and Wales", "quote": "the laws of England and Wales",
        "page": 1, "reasoning": "", "confidence": "high",
    }
    fake_llm.text_result = "## Overview\n\nAll agreements are governed by English law."
    client.post(f"/api/tables/{table}/columns", json={
        "columns": [{"header": "Governing law", "prompt": "What law governs?"}], "run": False,
    })
    client.post(f"/api/tables/{table}/run", json={})
    wait_until_idle(client, table)

    memo = client.post(f"/api/tables/{table}/memo", json={"focus": "assignment"}).get_json()["memo"]
    assert "Overview" in memo

    sent = fake_llm.calls[-1]["messages"][0]["content"]
    assert "England and Wales" in sent
    assert "assignment" in sent


def test_memo_requires_a_run(client, table, fake_llm):
    assert client.post(f"/api/tables/{table}/memo", json={}).status_code == 400


def test_deleting_a_table_removes_it(client, workspace, table):
    client.delete(f"/api/tables/{table}")
    assert client.get(f"/api/tables/{table}").status_code == 404
    assert client.get(f"/api/workspaces/{workspace}/tables").get_json()["tables"] == []

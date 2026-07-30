import io


def test_health_reports_llm_state(client):
    data = client.get("/api/health").get_json()
    assert data["ok"] is True
    assert data["llm_configured"] is False


def test_workspace_lifecycle(client):
    created = client.post("/api/workspaces", json={"name": "Atlas", "client": "Northwind"}).get_json()
    assert created["name"] == "Atlas"

    listed = client.get("/api/workspaces").get_json()["workspaces"]
    assert [w["id"] for w in listed] == [created["id"]]
    assert listed[0]["counts"] == {"documents": 0, "tables": 0}

    client.patch(f"/api/workspaces/{created['id']}", json={"name": "Atlas II"})
    assert client.get(f"/api/workspaces/{created['id']}").get_json()["name"] == "Atlas II"

    client.delete(f"/api/workspaces/{created['id']}")
    assert client.get(f"/api/workspaces/{created['id']}").status_code == 404


def test_workspace_requires_a_name(client):
    assert client.post("/api/workspaces", json={"name": "  "}).status_code == 400


def test_upload_extracts_indexes_and_lists(client, workspace, document):
    documents = client.get(f"/api/workspaces/{workspace}/documents").get_json()["documents"]
    assert len(documents) == 1
    assert documents[0]["status"] == "ready"
    assert documents[0]["words"] > 20
    assert documents[0]["title"] == "Nda Northwind"

    text = client.get(f"/api/documents/{document}/text").get_json()["text"]
    assert "England and Wales" in text
    assert "[[page" not in text


def test_upload_rejects_unsupported_types(client, workspace):
    response = client.post(
        f"/api/workspaces/{workspace}/documents",
        data={"files": (io.BytesIO(b"binary"), "archive.zip")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.get_json()["rejected"][0]["error"]


def test_upload_to_missing_workspace_404s(client):
    response = client.post(
        "/api/workspaces/ws_nope/documents",
        data={"files": (io.BytesIO(b"hi"), "a.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 404


def test_rename_and_delete_document(client, document):
    client.patch(f"/api/documents/{document}", json={"title": "NDA — Northwind"})
    assert client.get(f"/api/documents/{document}").get_json()["title"] == "NDA — Northwind"

    client.delete(f"/api/documents/{document}")
    assert client.get(f"/api/documents/{document}").status_code == 404


def test_download_returns_the_original_bytes(client, document):
    response = client.get(f"/api/documents/{document}/file")
    assert response.status_code == 200
    assert b"MUTUAL NON-DISCLOSURE" in response.data


def test_search_finds_the_governing_law_passage(client, workspace, document):
    results = client.post(
        f"/api/workspaces/{workspace}/search", json={"query": "which law governs"}
    ).get_json()["results"]

    assert results
    assert results[0]["document_id"] == document
    assert "England and Wales" in results[0]["preview"]
    assert "text" not in results[0]


def test_search_requires_a_query(client, workspace):
    assert client.post(f"/api/workspaces/{workspace}/search", json={}).status_code == 400


def test_intake_is_unavailable_without_an_api_key(client, document):
    response = client.post(f"/api/documents/{document}/intake")
    assert response.status_code == 503
    assert response.get_json()["code"] == "llm_not_configured"


def test_intake_returns_catalogue_metadata(client, document, fake_llm):
    fake_llm.tool_result = {
        "doc_type": "Mutual NDA",
        "parties": ["Northwind Holdings Limited", "Acme Robotics Inc."],
        "effective_date": "2025-03-01",
        "governing_law": "England and Wales",
        "summary": "A two-way confidentiality agreement.",
    }
    data = client.post(f"/api/documents/{document}/intake").get_json()
    assert data["doc_type"] == "Mutual NDA"
    assert len(data["parties"]) == 2

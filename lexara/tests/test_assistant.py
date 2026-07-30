import json


def read_events(response):
    events = []
    for frame in response.get_data(as_text=True).split("\n\n"):
        line = next((l for l in frame.split("\n") if l.startswith("data: ")), None)
        if line:
            events.append(json.loads(line[6:]))
    return events


def test_threads_are_created_and_listed(client, workspace):
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()
    assert thread["title"] == "New thread"

    listed = client.get(f"/api/workspaces/{workspace}/threads").get_json()["threads"]
    assert [t["id"] for t in listed] == [thread["id"]]


def test_message_streams_sources_deltas_and_done(client, workspace, document, fake_llm):
    fake_llm.stream_chunks = ["The agreement is governed by ", "English law [1]."]
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()["id"]

    response = client.post(
        f"/api/threads/{thread}/messages", json={"content": "What law governs?"}
    )
    assert response.status_code == 200
    events = read_events(response)

    kinds = [e["type"] for e in events]
    assert kinds[0] == "sources"
    assert "delta" in kinds
    assert kinds[-1] == "done"

    sources = events[0]["sources"]
    assert sources[0]["document_id"] == document
    assert sources[0]["n"] == 1

    done = events[-1]
    assert done["message_id"]
    assert [c["n"] for c in done["citations"]] == [1]


def test_the_reply_is_persisted_with_its_citations(client, workspace, document, fake_llm):
    fake_llm.stream_chunks = ["English law governs [1]."]
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()["id"]
    # the generator only runs as the body is consumed
    client.post(f"/api/threads/{thread}/messages", json={"content": "What law governs?"}).get_data()

    data = client.get(f"/api/threads/{thread}").get_json()
    roles = [m["role"] for m in data["messages"]]
    assert roles == ["user", "assistant"]
    assert data["messages"][1]["citations"][0]["title"] == "Nda Northwind"
    # the first question renames the thread
    assert data["thread"]["title"].startswith("What law governs")


def test_excerpts_are_handed_to_the_model(client, workspace, document, fake_llm):
    fake_llm.stream_chunks = ["ok"]
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()["id"]
    client.post(f"/api/threads/{thread}/messages", json={"content": "governing law"}).get_data()

    prompt = fake_llm.calls[-1]["messages"][-1]["content"]
    assert "<excerpts>" in prompt
    assert "England and Wales" in prompt
    assert 'document="Nda Northwind"' in prompt


def test_scoping_to_a_document_excludes_the_others(client, workspace, document, fake_llm):
    import io

    other = client.post(
        f"/api/workspaces/{workspace}/documents",
        data={"files": (io.BytesIO(b"An unrelated lease for warehouse premises."), "lease.txt")},
        content_type="multipart/form-data",
    ).get_json()["documents"][0]["id"]

    fake_llm.stream_chunks = ["ok"]
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()["id"]
    response = client.post(
        f"/api/threads/{thread}/messages",
        json={"content": "warehouse", "document_ids": [document]},
    )

    sources = read_events(response)[0]["sources"]
    assert {s["document_id"] for s in sources} == {document}
    assert other not in {s["document_id"] for s in sources}


def test_a_mid_stream_failure_is_reported_in_the_stream(client, workspace, document, fake_llm):
    def explode(_kwargs):
        raise RuntimeError("connection reset")

    fake_llm.stream_chunks = explode
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()["id"]
    events = read_events(client.post(f"/api/threads/{thread}/messages", json={"content": "hi"}))

    assert any(e["type"] == "error" and "connection reset" in e["error"] for e in events)
    assert events[-1]["type"] == "done"


def test_empty_message_is_rejected(client, workspace, fake_llm):
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()["id"]
    assert client.post(f"/api/threads/{thread}/messages", json={"content": "  "}).status_code == 400


def test_assistant_is_offline_without_an_api_key(client, workspace, document):
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()["id"]
    assert client.post(f"/api/threads/{thread}/messages", json={"content": "hi"}).status_code == 503


def test_deleting_a_thread_removes_its_messages(client, workspace, document, fake_llm):
    fake_llm.stream_chunks = ["ok"]
    thread = client.post(f"/api/workspaces/{workspace}/threads", json={}).get_json()["id"]
    client.post(f"/api/threads/{thread}/messages", json={"content": "hello"}).get_data()

    client.delete(f"/api/threads/{thread}")
    assert client.get(f"/api/threads/{thread}").status_code == 404

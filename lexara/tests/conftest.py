import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# config reads the data directory at import time, so point it at a scratch dir
# before anything imports the app package.
_TMP = tempfile.mkdtemp(prefix="lexara-tests-")
os.environ["LEXARA_DATA_DIR"] = _TMP
os.environ.pop("ANTHROPIC_API_KEY", None)

from app import config, create_app, db, llm  # noqa: E402


class Block:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Response:
    def __init__(self, content):
        self.content = content


class StreamHandle:
    def __init__(self, chunks):
        self.text_stream = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeMessages:
    """Stands in for ``client.messages``. Scripted per test."""

    def __init__(self, owner):
        self.owner = owner

    def create(self, **kwargs):
        self.owner.calls.append(kwargs)
        if self.owner.raise_with:
            raise self.owner.raise_with

        if kwargs.get("tools"):
            payload = self.owner.tool_result
            if callable(payload):
                payload = payload(kwargs)
            return Response([
                Block(type="tool_use", name=kwargs["tools"][0]["name"], input=payload)
            ])

        text = self.owner.text_result
        if callable(text):
            text = text(kwargs)
        return Response([Block(type="text", text=text)])

    def stream(self, **kwargs):
        self.owner.calls.append(kwargs)
        chunks = self.owner.stream_chunks
        if callable(chunks):
            chunks = chunks(kwargs)
        return StreamHandle(chunks)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.tool_result = {}
        self.text_result = "ok"
        self.stream_chunks = ["ok"]
        self.raise_with = None
        self.messages = FakeMessages(self)


@pytest.fixture()
def fake_llm():
    client = FakeClient()
    llm.set_client(client)
    yield client
    llm.set_client(None)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "lexara.db")
    db.reset_for_tests()

    application = create_app()
    application.config.update(TESTING=True)
    yield application
    db.reset_for_tests()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def workspace(client):
    return client.post("/api/workspaces", json={"name": "Project Atlas"}).get_json()["id"]


NDA_TEXT = """MUTUAL NON-DISCLOSURE AGREEMENT

This Mutual Non-Disclosure Agreement is entered into as of 1 March 2025 between
Northwind Holdings Limited and Acme Robotics Inc.

1. CONFIDENTIAL INFORMATION
All information disclosed by either party is Confidential Information.

2. TERM
The obligations in this Agreement survive for three (3) years from disclosure.

3. GOVERNING LAW
This Agreement is governed by the laws of England and Wales, and the parties
submit to the exclusive jurisdiction of the courts of England and Wales.

4. NON-SOLICITATION
For twelve (12) months neither party shall solicit the employees of the other.
"""


@pytest.fixture()
def document(client, workspace):
    import io

    response = client.post(
        f"/api/workspaces/{workspace}/documents",
        data={"files": (io.BytesIO(NDA_TEXT.encode()), "nda_northwind.txt")},
        content_type="multipart/form-data",
    )
    return response.get_json()["documents"][0]["id"]

import pytest

from app import llm


def test_parse_json_handles_bare_objects_and_fences():
    assert llm.parse_json('{"a": 1}') == {"a": 1}
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}
    assert llm.parse_json("not json at all") is None
    assert llm.parse_json("") is None


def test_complete_returns_concatenated_text(fake_llm):
    fake_llm.text_result = "  the answer  "
    assert llm.complete("sys", [{"role": "user", "content": "q"}]) == "the answer"


def test_complete_structured_returns_tool_input(fake_llm):
    fake_llm.tool_result = {"value": "yes"}
    result = llm.complete_structured(
        "sys", [{"role": "user", "content": "q"}],
        tool_name="extract_answer", description="d",
        schema={"type": "object", "properties": {}},
    )
    assert result == {"value": "yes"}
    assert fake_llm.calls[-1]["tool_choice"] == {"type": "tool", "name": "extract_answer"}


def test_structured_call_falls_back_to_parsing_text(fake_llm):
    """A model that answers in prose instead of calling the tool still works."""
    class TextOnly:
        content = [type("B", (), {"type": "text", "text": '{"value": "fallback"}'})()]

    fake_llm.messages.create = lambda **kwargs: TextOnly()
    result = llm.complete_structured(
        "sys", [], tool_name="t", description="d", schema={"type": "object"}
    )
    assert result == {"value": "fallback"}


def test_structured_call_raises_when_nothing_is_parseable(fake_llm):
    class Junk:
        content = [type("B", (), {"type": "text", "text": "sorry, I cannot"})()]

    fake_llm.messages.create = lambda **kwargs: Junk()
    with pytest.raises(llm.LLMError):
        llm.complete_structured("sys", [], tool_name="t", description="d", schema={})


def test_non_retryable_errors_surface_immediately(fake_llm):
    fake_llm.raise_with = ValueError("bad request")
    with pytest.raises(llm.LLMError, match="bad request"):
        llm.complete("sys", [])
    assert len(fake_llm.calls) == 1


def test_retryable_errors_are_retried(fake_llm, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)

    class Overloaded(Exception):
        status_code = 503

    fake_llm.raise_with = Overloaded("overloaded")
    with pytest.raises(llm.LLMError):
        llm.complete("sys", [])
    assert len(fake_llm.calls) == 3


def test_missing_api_key_raises_not_configured():
    llm.set_client(None)
    with pytest.raises(llm.NotConfigured):
        llm.client()
    assert llm.available() is False


def test_available_is_true_with_an_injected_client(fake_llm):
    assert llm.available() is True

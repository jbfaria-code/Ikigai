from app import retrieval
from app.extract import PAGE_MARKER


def test_tokenize_drops_stopwords_and_folds_suffixes():
    tokens = retrieval.tokenize("The parties shall indemnify the indemnified parties")
    assert "the" not in tokens
    assert "shall" not in tokens
    # "parties" and "party" fold to the same stem
    assert retrieval.stem("parties") == retrieval.stem("party")


def test_stem_leaves_short_words_alone():
    assert retrieval.stem("les") == "les"
    assert retrieval.stem("fees") == "fee"


def test_chunk_text_attributes_pages_from_markers():
    text = "\n\n".join([
        f"{PAGE_MARKER.format(n=1)}\nFirst page body about termination.",
        f"{PAGE_MARKER.format(n=2)}\nSecond page body about liability caps.",
    ])
    chunks = retrieval.chunk_text(text, target_chars=60, overlap_chars=0)

    assert chunks, "expected at least one chunk"
    assert all("[[page" not in c.text for c in chunks)
    pages = {c.page for c in chunks}
    assert pages <= {1, 2}
    assert any(c.page == 2 for c in chunks)


def test_chunk_text_splits_oversized_paragraph():
    body = "clause " * 4000
    chunks = retrieval.chunk_text(body, target_chars=800, overlap_chars=100)
    assert len(chunks) > 1
    assert max(len(c.text) for c in chunks) < 2400


def test_chunk_text_handles_empty_input():
    assert retrieval.chunk_text("   ") == []


def test_bm25_ranks_the_relevant_passage_first():
    records = [
        {"id": "a", "text": "The Supplier shall maintain insurance at all times."},
        {"id": "b", "text": "This Agreement is governed by the laws of Delaware."},
        {"id": "c", "text": "Payment terms are net thirty days from invoice."},
    ]
    hits = retrieval.search(records, "which law governs the agreement?", limit=2)
    assert hits[0]["id"] == "b"
    assert hits[0]["score"] > 0


def test_search_without_usable_query_still_returns_candidates():
    records = [{"id": "a", "text": "Some clause"}, {"id": "b", "text": "Another clause"}]
    hits = retrieval.search(records, "the and of", limit=1)
    assert len(hits) == 1


def test_search_on_empty_corpus():
    assert retrieval.search([], "anything") == []


def test_snippet_centres_on_the_matching_term():
    text = "padding. " * 60 + "The governing law is Delaware. " + "tail. " * 60
    out = retrieval.snippet(text, "governing law", width=200)
    assert "governing law is Delaware" in out
    assert len(out) <= 210
    assert out.startswith("…")


def test_snippet_returns_short_text_untouched():
    assert retrieval.snippet("short clause", "clause") == "short clause"


def test_snippet_falls_back_to_the_head_when_nothing_matches():
    text = "alpha " * 200
    out = retrieval.snippet(text, "zebra", width=100)
    assert out.startswith("alpha")
    assert out.endswith("…")

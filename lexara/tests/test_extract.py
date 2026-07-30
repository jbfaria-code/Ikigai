from app import extract


def test_extract_text_file_adds_page_markers(tmp_path):
    path = tmp_path / "memo.txt"
    path.write_text("First paragraph.\n\nSecond paragraph.")

    result = extract.extract(path, max_chars=10_000)

    assert result.kind == "text"
    assert "[[page 1]]" in result.text
    assert result.pages == 1
    assert result.words > 0


def test_extract_paginates_long_text(tmp_path):
    path = tmp_path / "long.md"
    path.write_text("\n\n".join(["A paragraph of text." * 40 for _ in range(12)]))

    result = extract.extract(path, max_chars=100_000)

    assert result.kind == "markdown"
    assert result.pages > 1
    assert "[[page 2]]" in result.text


def test_extract_truncates_and_warns(tmp_path):
    path = tmp_path / "big.txt"
    path.write_text("word " * 5000)

    result = extract.extract(path, max_chars=500)

    assert len(result.text) <= 500
    assert any("truncated" in w for w in result.warnings)


def test_page_of_finds_the_enclosing_marker():
    text = "[[page 1]]\nalpha\n\n[[page 2]]\nbravo\n\n[[page 3]]\ncharlie"
    assert extract.page_of(text, text.index("alpha")) == 1
    assert extract.page_of(text, text.index("bravo")) == 2
    assert extract.page_of(text, text.index("charlie")) == 3
    # Text before the first marker has no page.
    assert extract.page_of("preamble\n\n[[page 1]]\nalpha", 0) == 0


def test_strip_markers_removes_page_annotations():
    assert "[[page" not in extract.strip_markers("[[page 4]]\nBody text")


def test_docx_extraction_round_trip(tmp_path):
    docx = __import__("docx")
    document = docx.Document()
    document.add_heading("Termination", level=2)
    document.add_paragraph("Either party may terminate on 30 days' notice.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Notice"
    table.rows[0].cells[1].text = "30 days"

    path = tmp_path / "contract.docx"
    document.save(path)

    result = extract.extract(path, max_chars=50_000)

    assert result.kind == "docx"
    assert "## Termination" in result.text
    assert "30 days' notice" in result.text
    assert "Notice | 30 days" in result.text

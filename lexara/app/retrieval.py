"""Chunking and lexical retrieval.

The assistant needs to pull the handful of passages that answer a question out
of a whole matter's worth of documents. We use BM25 over word stems rather than
embeddings: it needs no extra API round-trip, it is deterministic (which makes
citations reproducible), and legal questions tend to share vocabulary with the
clauses that answer them.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass

from .extract import PAGE_MARKER_RE, page_of

WORD_RE = re.compile(r"[a-z0-9][a-z0-9'\-]*")

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "of", "in", "on", "at", "to", "for", "with", "by", "from",
    "as", "is", "are", "was", "were", "be", "been", "being", "it", "its", "any",
    "all", "such", "shall", "will", "may", "can", "not", "no", "do", "does",
    "did", "has", "have", "had", "he", "she", "they", "we", "you", "i", "what",
    "which", "who", "whom", "when", "where", "how", "why", "there", "here",
}

# Legal drafting is full of near-synonyms; light suffix folding beats none.
SUFFIXES = ("ies", "ing", "ions", "ion", "ers", "er", "ed", "es", "s")


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in WORD_RE.findall(text.lower()):
        if raw in STOPWORDS or len(raw) < 2:
            continue
        tokens.append(stem(raw))
    return tokens


def stem(word: str) -> str:
    # "parties" → "party" so it folds together with the singular.
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    for suffix in SUFFIXES:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


@dataclass
class Chunk:
    ordinal: int
    page: int
    text: str


def chunk_text(text: str, target_chars: int = 1400, overlap_chars: int = 200) -> list[Chunk]:
    """Split marker-annotated text into overlapping, paragraph-aligned chunks."""
    if not text.strip():
        return []

    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[Chunk] = []
    buffer = ""
    buffer_start = 0
    cursor = 0

    def flush(end_offset: int) -> None:
        nonlocal buffer, buffer_start
        body = buffer.strip()
        if body:
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    page=page_of(text, buffer_start),
                    text=PAGE_MARKER_RE.sub("", body).strip(),
                )
            )
        buffer = ""
        buffer_start = end_offset

    for para in paragraphs:
        para_start = text.find(para, cursor)
        if para_start == -1:
            para_start = cursor
        cursor = para_start + len(para)

        if not buffer:
            buffer_start = para_start

        if buffer and len(buffer) + len(para) > target_chars:
            tail = buffer[-overlap_chars:] if overlap_chars else ""
            flush(para_start)
            buffer = f"{tail}\n\n{para}" if tail else para
            buffer_start = max(para_start - len(tail), 0)
        else:
            buffer = f"{buffer}\n\n{para}" if buffer else para

        # A single enormous paragraph still has to be broken up.
        while len(buffer) > target_chars * 2:
            head, buffer = buffer[:target_chars], buffer[target_chars - overlap_chars :]
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    page=page_of(text, buffer_start),
                    text=PAGE_MARKER_RE.sub("", head).strip(),
                )
            )
            buffer_start += target_chars - overlap_chars

    flush(cursor)
    return chunks


class BM25:
    """Okapi BM25 over a fixed corpus of documents."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self.doc_len = [len(d) for d in corpus]
        self.avg_len = (sum(self.doc_len) / len(corpus)) if corpus else 0.0
        self.freqs = [Counter(d) for d in corpus]
        df: Counter = Counter()
        for doc in corpus:
            df.update(set(doc))
        n = len(corpus)
        self.idf = {
            term: math.log(1 + (n - count + 0.5) / (count + 0.5))
            for term, count in df.items()
        }

    def score(self, query_tokens: list[str], index: int) -> float:
        freqs = self.freqs[index]
        length = self.doc_len[index] or 1
        total = 0.0
        for term in query_tokens:
            tf = freqs.get(term)
            if not tf:
                continue
            idf = self.idf.get(term, 0.0)
            denom = tf + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
            total += idf * tf * (self.k1 + 1) / denom
        return total

    def top_n(self, query_tokens: list[str], n: int) -> list[tuple[int, float]]:
        scored = [(i, self.score(query_tokens, i)) for i in range(len(self.corpus))]
        scored = [pair for pair in scored if pair[1] > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:n]


def search(records: list[dict], question: str, limit: int = 12) -> list[dict]:
    """Rank ``records`` (dicts with a ``text`` key) against ``question``.

    Returns copies of the matching records with a ``score`` key added.
    """
    if not records:
        return []
    query_tokens = tokenize(question)
    if not query_tokens:
        return [dict(r, score=0.0) for r in records[:limit]]

    index = BM25([tokenize(r["text"]) for r in records])
    hits = index.top_n(query_tokens, limit)
    return [dict(records[i], score=round(score, 4)) for i, score in hits]


def snippet(text: str, question: str, width: int = 400) -> str:
    """A window of ``text`` centred on the first query term that appears in it.

    Truncating from the top would routinely cut off the passage that made the
    chunk match in the first place.
    """
    if len(text) <= width:
        return text

    lowered = text.lower()
    best = -1
    for token in tokenize(question):
        for candidate in WORD_RE.finditer(lowered):
            if stem(candidate.group()) == token:
                best = candidate.start()
                break
        if best != -1:
            break

    if best == -1:
        return text[:width].rstrip() + "…"

    start = max(0, best - width // 3)
    end = min(len(text), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"

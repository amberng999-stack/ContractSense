"""
Lightweight keyword-based retrieval over the Malaysian law / company
policy reference databases.

Problem this fixes: llm_review.py and llm_chat.py used to blindly
truncate laws_text/policies_text to the first N characters before
putting them in the prompt. If the relevant statute (e.g. Employment
Act 1955) wasn't near the very start of the uploaded reference file,
the model never saw it — which is a direct cause of "the law citations
are inaccurate" complaints, independent of how good the LLM itself is.

This module chunks the reference text and keyword-scores chunks against
a query (the user's question, or the contract text itself), so the
prompt is built from passages that are actually relevant to what's
being reviewed/asked. Deliberately simple (no embeddings/vector DB) —
zero extra infra/cost, but removes the "always the first N chars"
failure mode. Can be swapped for embedding-based search later without
changing callers.
"""
from __future__ import annotations

import re

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "what", "when", "where",
    "which", "about", "into", "does", "should", "could", "would", "please", "contract",
    "clause", "agreement", "tell", "explain", "make", "sure", "shall", "will", "party",
    "parties", "under", "such", "have", "has", "are", "was", "were",
}


def extract_keywords(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text.lower())
        if word not in _STOPWORDS
    }


def chunk_text(text: str, chunk_chars: int = 1200) -> list[str]:
    """
    Splits reference text into chunks along blank-line/paragraph
    boundaries where possible, so keyword search operates on coherent
    passages instead of the whole document as one blob.
    """
    text = text.strip()
    if not text:
        return []

    raw_parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not raw_parts:
        raw_parts = [text]

    chunks: list[str] = []
    buffer = ""
    for part in raw_parts:
        if buffer and len(buffer) + len(part) + 1 > chunk_chars:
            chunks.append(buffer)
            buffer = ""

        if len(part) <= chunk_chars:
            buffer = f"{buffer}\n{part}".strip() if buffer else part
        else:
            # Hard-split an oversized paragraph (e.g. one giant clause dump).
            if buffer:
                chunks.append(buffer)
                buffer = ""
            for i in range(0, len(part), chunk_chars):
                chunks.append(part[i:i + chunk_chars])

    if buffer:
        chunks.append(buffer)
    return chunks


def top_matching_chunks(query_text: str, reference_text: str, *, top_k: int = 5, chunk_chars: int = 1200) -> list[str]:
    """
    Returns the top_k chunks of reference_text most relevant to
    query_text, by keyword overlap. Falls back to the first top_k
    chunks (document order) if the query has no usable keywords or
    nothing scores > 0, so callers still get representative context
    instead of nothing.
    """
    chunks = chunk_text(reference_text, chunk_chars=chunk_chars)
    if not chunks:
        return []

    query_words = extract_keywords(query_text)
    if not query_words:
        return chunks[:top_k]

    scored: list[tuple[int, int, str]] = []
    for order, chunk in enumerate(chunks):
        chunk_words = extract_keywords(chunk)
        score = sum(1 for w in query_words if w in chunk_words)
        scored.append((score, order, chunk))

    scored.sort(key=lambda item: (-item[0], item[1]))
    top = [c for score, _, c in scored[:top_k] if score > 0]
    return top if top else chunks[:top_k]


def build_reference_context(
    query_text: str,
    laws_text: str,
    policies_text: str,
    *,
    top_k: int = 5,
    chunk_chars: int = 1200,
) -> tuple[str, str]:
    """Convenience wrapper: returns (laws_context, policies_context) built
    from the most relevant chunks instead of a blind head-truncation."""
    laws_context = (
        "\n\n---\n\n".join(top_matching_chunks(query_text, laws_text, top_k=top_k, chunk_chars=chunk_chars))
        if laws_text.strip() else ""
    )
    policies_context = (
        "\n\n---\n\n".join(top_matching_chunks(query_text, policies_text, top_k=top_k, chunk_chars=chunk_chars))
        if policies_text.strip() else ""
    )
    return laws_context, policies_context

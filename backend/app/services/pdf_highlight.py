"""
Extracts both the full text AND per-word pixel coordinates from a PDF,
so flagged phrases can be highlighted in place on the real rendered PDF
instead of being displayed as reconstructed/fake HTML text.

This is the core of the PDF-native rendering pipeline:
  1. extract_pdf_with_coords() reads the PDF once, producing:
     - full_text: the complete text (for risk_rules.py to analyze, same as before)
     - pages: per-page word lists with x0/x1/top/bottom coordinates
     - char_to_word_map: lets us map a character offset in full_text back
       to the word(s) on the page that produced it
  2. match_excerpt_to_boxes() takes a flagged excerpt (from risk_rules.py)
     and finds where that text appears in the original PDF, returning a
     list of bounding boxes (possibly spanning multiple words/lines) to
     highlight on the rendered page.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO


@dataclass
class WordBox:
    text: str
    page: int       # 0-indexed
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass
class PdfExtraction:
    full_text: str          # all words joined with single spaces, in reading order
    words: list[WordBox]    # every word on every page, in reading order
    page_sizes: list[tuple[float, float]]  # (width, height) per page, 0-indexed
    pdf_bytes: bytes        # the original PDF, unmodified


def extract_pdf_with_coords(content: bytes) -> PdfExtraction:
    import pdfplumber

    words: list[WordBox] = []
    text_parts: list[str] = []
    page_sizes: list[tuple[float, float]] = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_sizes.append((float(page.width), float(page.height)))
            page_words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            for w in page_words:
                wb = WordBox(
                    text=w["text"],
                    page=page_idx,
                    x0=float(w["x0"]),
                    x1=float(w["x1"]),
                    top=float(w["top"]),
                    bottom=float(w["bottom"]),
                )
                words.append(wb)
                text_parts.append(w["text"])

    full_text = " ".join(text_parts)

    return PdfExtraction(
        full_text=full_text,
        words=words,
        page_sizes=page_sizes,
        pdf_bytes=content,
    )


@dataclass
class HighlightBox:
    page: int
    x0: float
    x1: float
    top: float
    bottom: float
    severity: str


def match_excerpt_to_boxes(
    extraction: PdfExtraction,
    excerpt: str,
    severity: str,
    max_words: int = 60,
) -> list[HighlightBox]:
    """
    Finds where `excerpt` (a flagged snippet of text, possibly with
    "..." truncation markers from risk_rules.py) appears among the
    extracted words, and returns bounding boxes to highlight.

    Strategy: normalise both the excerpt and the page's word stream to
    lowercase alphanumeric tokens, then find the longest contiguous run
    of matching tokens. This is robust to minor whitespace/punctuation
    differences between the excerpt and the original PDF text.
    """
    clean_excerpt = excerpt.strip().strip(".").replace("...", " ").strip()
    excerpt_tokens = _tokenize(clean_excerpt)
    if not excerpt_tokens:
        return []

    word_tokens = [_tokenize_single(w.text) for w in extraction.words]

    # Sliding window search for the best matching run of consecutive words
    best_start, best_len = _find_best_match(word_tokens, excerpt_tokens, max_words)
    if best_len == 0:
        return []

    matched_words = extraction.words[best_start: best_start + best_len]
    return _group_words_into_boxes(matched_words, severity)


def _tokenize(text: str) -> list[str]:
    """
    Splits text into words on whitespace (same granularity as PDF word
    extraction), then cleans each word the same way _tokenize_single does.
    This keeps excerpt tokens and PDF word tokens directly comparable —
    e.g. "1.1" stays as one token ("11") on both sides, instead of the
    excerpt splitting it into ["1", "1"] via a different regex strategy.
    """
    raw_words = text.split()
    tokens = [_tokenize_single(w) for w in raw_words]
    return [t for t in tokens if t]


def _tokenize_single(word: str) -> str:
    import re
    cleaned = re.sub(r"[^a-z0-9]", "", word.lower())
    return cleaned


def _find_best_match(word_tokens: list[str], excerpt_tokens: list[str], max_words: int) -> tuple[int, int]:
    """
    Finds the starting index in word_tokens where the longest prefix of
    excerpt_tokens matches consecutively (allowing empty-token words from
    punctuation to be skipped). Returns (start_index, run_length).
    """
    n = len(word_tokens)
    target = excerpt_tokens[0]

    best_start, best_len = -1, 0

    for i in range(n):
        if word_tokens[i] != target or not target:
            continue

        # Try to extend the match from this position
        wi, ei = i, 0
        matched = 0
        while wi < n and ei < len(excerpt_tokens) and (wi - i) < max_words:
            wt = word_tokens[wi]
            if not wt:
                wi += 1
                continue
            if wt == excerpt_tokens[ei]:
                matched += 1
                ei += 1
                wi += 1
            else:
                break

        if matched > best_len:
            best_len = matched
            best_start = i

        # Early exit if we matched the whole excerpt
        if ei >= len(excerpt_tokens):
            break

    if best_start == -1:
        return -1, 0

    # Compute the actual word-span length (including skipped punctuation words)
    wi, ei, matched = best_start, 0, 0
    span = 0
    while wi < len(word_tokens) and ei < len(excerpt_tokens) and span < max_words:
        wt = word_tokens[wi]
        if not wt:
            wi += 1
            span += 1
            continue
        if wt == excerpt_tokens[ei]:
            ei += 1
            wi += 1
            span += 1
        else:
            break

    return best_start, span


def _group_words_into_boxes(words: list[WordBox], severity: str) -> list[HighlightBox]:
    """
    Groups consecutive words into per-line bounding boxes (words on the
    same page with similar 'top' coordinates get merged into one wide
    highlight rectangle spanning that line, rather than one box per word).
    """
    if not words:
        return []

    boxes: list[HighlightBox] = []
    current_page = words[0].page
    current_top = words[0].top
    line_words = [words[0]]

    def flush(line: list[WordBox]) -> HighlightBox:
        return HighlightBox(
            page=line[0].page,
            x0=min(w.x0 for w in line),
            x1=max(w.x1 for w in line),
            top=min(w.top for w in line),
            bottom=max(w.bottom for w in line),
            severity=severity,
        )

    for w in words[1:]:
        same_line = (w.page == current_page) and (abs(w.top - current_top) < 3)
        if same_line:
            line_words.append(w)
        else:
            boxes.append(flush(line_words))
            line_words = [w]
            current_page = w.page
            current_top = w.top

    boxes.append(flush(line_words))
    return boxes

"""
Splits extracted contract text back into numbered clauses.

PDF text extraction often loses original line breaks, so a clause like:
  "1.1 Confidential Information means..."
  "1.2 The Receiving Party agrees..."
ends up as one continuous run-on string. This module re-splits that text
using the numbering pattern (e.g. "1.1", "2.3", "10.4") so the rest of the
pipeline can work clause-by-clause instead of treating the whole contract
as a single blob.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Matches clause numbers like "1.1", "2.3", "10.4" at a word boundary,
# followed by a space and then text. Also matches top-level section
# headers like "1. DEFINITION OF..." (no decimal).
_CLAUSE_PATTERN = re.compile(
    r"(?<![\d.])(?P<num>\d{1,2}\.\d{1,2})\.?\s+(?=[A-Z'])"
)

_SECTION_HEADER_PATTERN = re.compile(
    r"(?<![\d.])(?P<num>\d{1,2})\.\s+(?P<title>[A-Z][A-Z\s\-]{2,60}?)(?=\s+\d{1,2}\.\d{1,2}\s|\s+\d{1,2}\.\s|$)"
)

# Matches flat clause numbers like "1. ", "2. ", "10. " at a word boundary,
# followed by a space and then an uppercase letter or quote.
_FLAT_CLAUSE_PATTERN = re.compile(
    r"(?<![\d.])(?P<num>\d{1,2})\.\s+(?=[A-Z'])"
)


@dataclass
class Section:
    title: str
    clauses: list["Clause"]


@dataclass
class Clause:
    id: str
    text: str


def split_into_sections(text: str) -> list[Section]:
    """
    Splits raw contract text into sections (e.g. "1. DEFINITION OF...")
    each containing numbered sub-clauses (e.g. "1.1", "1.2").

    Falls back to trying flat-numbered list split (e.g. "1.", "2.")
    if no decimal matches exist, and finally falls back to a single
    section with the whole text as one clause if no structure is found.
    """
    text = " ".join(text.split())  # normalise whitespace/newlines

    header_matches = list(_SECTION_HEADER_PATTERN.finditer(text))
    clause_matches = list(_CLAUSE_PATTERN.finditer(text))

    # Determine if we have a valid decimal clause structure
    has_decimal_structure = clause_matches and _looks_like_real_clause_structure(text, clause_matches, header_matches)

    if not has_decimal_structure:
        # Try flat numbering (e.g., "1.", "2.") before falling back completely
        flat_matches = list(_FLAT_CLAUSE_PATTERN.finditer(text))
        if flat_matches and _looks_like_real_flat_structure(text, flat_matches):
            clause_matches = flat_matches
        else:
            return [Section(title="", clauses=[Clause(id="1", text=text)])]

    # Build a lookup of section number -> title from header matches
    titles: dict[str, str] = {}
    for h in header_matches:
        titles[h.group("num")] = h.group("title").strip().rstrip(".")

    sections: dict[str, list[Clause]] = {}
    section_order: list[str] = []

    for i, match in enumerate(clause_matches):
        clause_id = match.group("num")
        start = match.end()
        end = clause_matches[i + 1].start() if i + 1 < len(clause_matches) else len(text)
        clause_text = text[start:end].strip()

        if not clause_text:
            continue

        # Strip trailing section headers that belong to the next section but got captured at the end of this clause
        clause_text = re.sub(r"\s*(?<![\d.])\d{1,2}\.\s+[A-Za-z][A-Za-z\s\-]{2,60}?$", "", clause_text).strip()

        if not clause_text:
            continue

        section_num = clause_id.split(".")[0]

        if section_num not in sections:
            sections[section_num] = []
            section_order.append(section_num)

        sections[section_num].append(Clause(id=clause_id, text=clause_text))

    return [
        Section(
            title=f"{num}. {titles[num]}" if num in titles else "",
            clauses=sections[num],
        )
        for num in section_order
    ]


def _looks_like_real_clause_structure(text: str, clause_matches: list, header_matches: list) -> bool:
    """
    Heuristic sanity check to avoid treating non-contract documents
    (study notes, articles, reports with case citations / statute
    references) as if they were structured contracts.

    Requires:
    - At least one real section header (e.g. "1. DEFINITION OF...")
      Most genuine contracts have these; prose documents with stray
      numbers usually don't.
    - Section numbers in the detected clauses are mostly sequential and
      start near 1, rather than scattered/inconsistent (a strong signal
      of real clause numbering vs. coincidental number matches like
      "60A" or "14B" from statute citations).
    """
    if not header_matches:
        return False

    section_nums = []
    for m in clause_matches:
        try:
            section_nums.append(int(m.group("num").split(".")[0]))
        except ValueError:
            continue

    if not section_nums:
        return False

    # Real contracts rarely jump straight to large section numbers without
    # smaller ones appearing first/often. If the spread of distinct section
    # numbers is very large relative to how many clause matches there are,
    # it's more likely coincidental matches from an unstructured document.
    distinct_sections = set(section_nums)
    if len(distinct_sections) > len(clause_matches):
        return False

    if max(distinct_sections) > 25:
        return False

    return True


def _looks_like_real_flat_structure(text: str, flat_matches: list) -> bool:
    """
    Sanity check to make sure flat numbering looks like a sequential clause structure.
    """
    if len(flat_matches) < 2:
        return False

    nums = []
    for m in flat_matches:
        try:
            nums.append(int(m.group("num")))
        except ValueError:
            continue

    if not nums:
        return False

    # A flat structure should start near 1 or 2
    if min(nums) > 2:
        return False

    # Check if there is some sequential progression
    sequential_count = 0
    for i in range(1, len(nums)):
        if nums[i] == nums[i - 1] + 1 or nums[i] == nums[i - 1]:
            sequential_count += 1

    # If at least some numbers are sequential or consecutive, it looks like list items
    if sequential_count >= 1 or len(nums) >= 2:
        return True

    return False


def flatten_clauses(sections: list[Section]) -> list[Clause]:
    """Convenience helper: returns every clause across all sections as a flat list."""
    return [clause for section in sections for clause in section.clauses]

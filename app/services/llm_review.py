from __future__ import annotations

from app.models import ClauseFinding, LlmReview
from app.services.clause_splitter import split_into_sections, to_numbered_lines
from app.services.retrieval import build_reference_context

# Per-call contract-text budget. Long contracts are split into multiple
# batches instead of being silently truncated after the first ~12,000
# characters (the original bug: anything past that point was never
# reviewed, but nothing told the user or the model that).
REVIEW_BATCH_CHAR_BUDGET = 9000

REVIEW_TEMPERATURE = 0  # deterministic judgement task, not creative writing


async def review_with_llm(
    *,
    api_key: str,
    model: str,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-1.5-flash",
    contract_text: str,
    findings: list[ClauseFinding],
    jurisdiction: str | None,
    language: str | None,
    laws_text: str = "",
    policies_text: str = "",
) -> LlmReview | None:

    has_openai = bool(api_key)
    has_gemini = bool(gemini_api_key)

    if not has_openai and not has_gemini:
        return _offline_fallback_review(findings)

    try:
        from openai import AsyncOpenAI
    except ImportError:
        return _offline_fallback_review(findings)

    if has_openai:
        client = AsyncOpenAI(api_key=api_key)
        active_model = model
        provider = "openai"
    else:
        client = AsyncOpenAI(
            api_key=gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        active_model = gemini_model or "gemini-1.5-flash"
        provider = "gemini"

    finding_summary = "\n".join(
        f"- {finding.severity.upper()} {finding.title}: {finding.excerpt}" for finding in findings
    ) or "- No deterministic rule findings."

    # Retrieval instead of blind head-truncation: pull the law/policy
    # passages most relevant to THIS contract, not just whatever happens
    # to sit in the first N characters of the reference database.
    laws_context, policies_context = build_reference_context(
        contract_text, laws_text, policies_text, top_k=5
    )

    batches = _build_review_batches(contract_text, max_chars=REVIEW_BATCH_CHAR_BUDGET)

    try:
        if len(batches) <= 1:
            review_text = await _run_single_review(
                client,
                active_model,
                contract_section=batches[0] if batches else "(No readable contract text.)",
                finding_summary=finding_summary,
                laws_context=laws_context,
                policies_context=policies_context,
                jurisdiction=jurisdiction,
                language=language,
            )
        else:
            review_text = await _run_batched_review(
                client,
                active_model,
                batches,
                finding_summary=finding_summary,
                laws_context=laws_context,
                policies_context=policies_context,
                jurisdiction=jurisdiction,
                language=language,
            )
        return LlmReview(provider=provider, model=active_model, review=review_text)
    except Exception as exc:
        # If the AI call fails (bad key, rate limit, network, etc.),
        # don't crash the whole scan — fall back to rule-based findings only.
        return _offline_fallback_review(findings, exc)


def _build_review_batches(contract_text: str, *, max_chars: int) -> list[str]:
    """
    Splits the contract into numbered-clause batches, each within
    max_chars, so a long contract is fully reviewed across multiple
    calls instead of the tail being silently dropped.
    """
    sections = split_into_sections(contract_text)
    flat_lines = to_numbered_lines(sections)

    if not flat_lines:
        normalised = " ".join(contract_text.split())
        if not normalised:
            return []
        return [normalised[i:i + max_chars] for i in range(0, len(normalised), max_chars)] or [normalised]

    batches: list[str] = []
    buffer_lines: list[str] = []
    buffer_len = 0
    for line in flat_lines:
        line_len = len(line) + 1
        if buffer_lines and buffer_len + line_len > max_chars:
            batches.append("\n".join(buffer_lines))
            buffer_lines, buffer_len = [], 0
        buffer_lines.append(line)
        buffer_len += line_len
    if buffer_lines:
        batches.append("\n".join(buffer_lines))
    return batches


def _review_prompt(
    contract_section: str,
    finding_summary: str,
    laws_context: str,
    policies_context: str,
    jurisdiction: str | None,
    language: str | None,
    *,
    part_note: str = "",
) -> str:
    return f"""
You are an enterprise contract compliance screening assistant.
Your job is to identify hidden clauses, unusual enterprise risk, and review points.
Do not provide legal advice. Provide practical compliance review guidance.

Jurisdiction: {jurisdiction or "not specified"}
Preferred language: {language or "same as contract/user"}

Grounding rules (follow strictly):
- The contract below is numbered as [Clause X.Y]. Every specific issue you raise MUST cite the exact clause id(s) it comes from, e.g. "(Clause 4.2)". If a point is not tied to a specific clause, say so explicitly instead of inventing a clause number.
- Only use the "Reference Malaysian Laws" and "Reference Company Policy" excerpts below as your law/policy grounding. If something relevant is not covered by them, you may reference well-known Malaysian statute names, but must flag it as "not verified against the uploaded reference database".
- Do not state a fact about the contract that is not present in the text below.
{part_note}

Reference Malaysian Laws database (most relevant excerpts for this contract):
{laws_context or "No specific law database documents uploaded, or no relevant match found. Use general knowledge of Malaysian law and flag this clearly."}

Reference Company Policy rules & regulations (most relevant excerpts for this contract):
{policies_context or "No specific company policy documents uploaded, or no relevant match found."}

Deterministic rule-engine findings (already computed — cross-check these against your own read, don't just repeat them):
{finding_summary}

Numbered contract text:
{contract_section}

Return:
1. Executive summary
2. Hidden/risky clauses missed or confirmed — cite clause id for every point (especially contradictions with the reference Malaysian laws or Company Policy)
3. Questions for legal/compliance team
4. Recommended negotiation actions
""".strip()


async def _run_single_review(
    client,
    active_model: str,
    *,
    contract_section: str,
    finding_summary: str,
    laws_context: str,
    policies_context: str,
    jurisdiction: str | None,
    language: str | None,
) -> str:
    prompt = _review_prompt(
        contract_section, finding_summary, laws_context, policies_context, jurisdiction, language
    )
    response = await client.chat.completions.create(
        model=active_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=REVIEW_TEMPERATURE,
    )
    return response.choices[0].message.content or "No response from LLM."


async def _run_batched_review(
    client,
    active_model: str,
    batches: list[str],
    *,
    finding_summary: str,
    laws_context: str,
    policies_context: str,
    jurisdiction: str | None,
    language: str | None,
) -> str:
    """
    Map-reduce for long contracts: review each batch of clauses
    independently (so nothing gets silently dropped), then synthesize
    the partial reviews into one consolidated report.
    """
    total = len(batches)
    partial_reviews: list[str] = []

    for idx, batch in enumerate(batches, start=1):
        part_note = (
            f"- This is part {idx} of {total} of a long contract, split by clause. "
            "Only review the clauses shown in THIS part; do not comment on parts not shown."
        )
        prompt = _review_prompt(
            batch, finding_summary, laws_context, policies_context, jurisdiction, language, part_note=part_note
        )
        response = await client.chat.completions.create(
            model=active_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=REVIEW_TEMPERATURE,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            partial_reviews.append(f"--- Part {idx}/{total} ---\n{text}")

    if not partial_reviews:
        return "No response from LLM."

    synthesis_prompt = f"""
You are consolidating {total} partial compliance reviews of ONE long contract (each part covered different, non-overlapping clauses) into a single final review.

Grounding rules:
- Every specific issue must keep its original clause id citation from the partial reviews below.
- Do not invent new issues that are not present in the partial reviews.
- Merge duplicate/overlapping points instead of repeating them.

Partial reviews:
{chr(10).join(partial_reviews)}

Return ONE consolidated review with these sections:
1. Executive summary
2. Hidden/risky clauses missed or confirmed (with clause id citations)
3. Questions for legal/compliance team
4. Recommended negotiation actions
""".strip()

    response = await client.chat.completions.create(
        model=active_model,
        messages=[{"role": "user", "content": synthesis_prompt}],
        temperature=REVIEW_TEMPERATURE,
    )
    return (response.choices[0].message.content or "").strip() or "\n\n".join(partial_reviews)


def _offline_fallback_review(findings: list[ClauseFinding], exc: Exception | None = None) -> LlmReview:
    critical_count = sum(1 for f in findings if f.severity in ["critical", "high"])
    medium_count = sum(1 for f in findings if f.severity == "medium")

    error_msg = f" ({exc})" if exc else ""
    fallback_review = f"""
### ⚠️ Compliance Review Summary (Offline Fallback Mode)
*Note: AI cloud review is currently offline{error_msg}. Generating local deterministic rule review.*

#### 1. Executive Summary
We have completed a compliance scan of the uploaded contract. A total of {len(findings)} clause analyses were performed, flagging {critical_count} high/critical risk and {medium_count} medium risk items.

#### 2. Key Risk Flags Detected
"""
    flagged = [f for f in findings if f.severity != "low"]
    if flagged:
        for f in flagged[:5]:
            fallback_review += f"\n- **{f.title} ({f.severity.upper()})**: {f.explanation}\n  *Recommendation*: {f.recommendation}"
    else:
        fallback_review += "\n- No compliance flags or risks were detected in the contract."

    fallback_review += """

#### 3. General Malaysian Compliance Checklist
- **Employment Act 1955**: Verify that working hours do not exceed 45 hours/week, and overtime rates (1.5x / 2.0x / 3.0x) are statutory.
- **PDPA 2010**: Confirm there is a clear personal data consent and disclosure clause.
- **Companies Act 2016**: Check if director/entity authority is fully defined.
"""
    return LlmReview(
        provider="local-fallback",
        model="deterministic-heuristics",
        review=fallback_review.strip(),
    )

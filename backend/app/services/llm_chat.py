from __future__ import annotations

import re

from app.models import ClauseFinding


MAX_CONTRACT_CHARS = 14000
MAX_REFERENCE_CHARS = 9000
MAX_HISTORY_MESSAGES = 12


async def chat_with_llm(
    *,
    api_key: str,
    model: str,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-1.5-flash",
    message: str,
    contract_text: str,
    findings: list[ClauseFinding],
    laws_text: str,
    policies_text: str,
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    user_message = message.strip()
    if not user_message:
        return "Ask me a question about a contract, Malaysian law, or a clause you want to improve."

    has_openai = bool(api_key)
    has_gemini = bool(gemini_api_key)

    if not has_openai and not has_gemini:
        return offline_fallback_chat(
            message=user_message,
            contract_text=contract_text,
            findings=findings,
            laws_text=laws_text,
            policies_text=policies_text,
        )

    try:
        from openai import AsyncOpenAI
    except ImportError:
        return offline_fallback_chat(
            message=user_message,
            contract_text=contract_text,
            findings=findings,
            laws_text=laws_text,
            policies_text=policies_text,
            error=RuntimeError("OpenAI-compatible client library is not installed."),
        )

    if has_openai:
        client = AsyncOpenAI(api_key=api_key)
        active_model = model
        provider_name = "OpenAI"
    else:
        client = AsyncOpenAI(
            api_key=gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        active_model = gemini_model or "gemini-1.5-flash"
        provider_name = "Gemini"

    clipped_contract = contract_text[:MAX_CONTRACT_CHARS].strip()
    clipped_laws = laws_text[:MAX_REFERENCE_CHARS].strip()
    clipped_policies = policies_text[:MAX_REFERENCE_CHARS].strip()
    finding_summary = "\n".join(
        (
            f"- {finding.severity.upper()} | {finding.title}: {finding.excerpt}\n"
            f"  Reason: {finding.explanation}\n"
            f"  Recommended action: {finding.recommendation}"
        )
        for finding in findings
    ) or "- No deterministic rule findings."

    if clipped_contract:
        contract_context = f"""
Scanned contract text:
\"\"\"
{clipped_contract}
\"\"\"

Current scan findings:
{finding_summary}
""".strip()
    else:
        contract_context = (
            "No contract is currently attached to this chat. Answer general Malaysian "
            "contract and compliance questions directly, and suggest uploading a contract "
            "only when document-specific review is needed."
        )

    system_message = f"""
You are ContractSense AI, a practical contract compliance assistant for Malaysian SMEs, HR teams, and legal operations.

Core behavior:
- Answer like a functional AI chatbot, not a static FAQ.
- Use the scanned contract and findings when present.
- Use Malaysian context, especially Contracts Act 1950, Employment Act 1955, PDPA 2010, Companies Act 2016, and user-uploaded law/policy references.
- Give concrete next steps, clause rewrite suggestions, and negotiation points when useful.
- Be clear that this is compliance guidance, not formal legal advice.
- If information is missing, say what you can infer and what should be verified.
- Keep replies concise unless the user asks for detail.

Reference Malaysian laws database:
{clipped_laws or "No uploaded law reference text is available in this request."}

Reference company policy database:
{clipped_policies or "No uploaded company policy text is available in this request."}

{contract_context}
""".strip()

    messages = [{"role": "system", "content": system_message}]
    messages.extend(_clean_chat_history(chat_history or []))
    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model=active_model,
            messages=messages,
            temperature=0.25,
            max_tokens=900,
        )
        reply = response.choices[0].message.content
        return reply.strip() if reply else f"{provider_name} returned an empty response."
    except Exception as exc:
        return offline_fallback_chat(
            message=user_message,
            contract_text=contract_text,
            findings=findings,
            laws_text=laws_text,
            policies_text=policies_text,
            error=exc,
        )


def _clean_chat_history(chat_history: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in chat_history[-MAX_HISTORY_MESSAGES:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content[:3000]})
    return cleaned


def offline_fallback_chat(
    *,
    message: str,
    contract_text: str,
    findings: list[ClauseFinding],
    laws_text: str,
    policies_text: str,
    error: Exception | None = None,
) -> str:
    message_lower = message.lower()
    contract_text = contract_text or ""

    parts = ["### ContractSense AI"]
    if error:
        parts.append(
            "Cloud AI is unavailable right now, so I am using the local compliance assistant. "
            "I can still answer from the scanned contract, rule findings, and built-in Malaysian compliance checks."
        )

    if _asks_for_summary(message_lower):
        parts.append(_contract_summary(contract_text, findings))
        return "\n\n".join(parts)

    if _asks_for_rewrite(message_lower):
        parts.append(_rewrite_answer(message, contract_text, findings))
        return "\n\n".join(parts)

    related_findings = _related_findings(message_lower, findings)
    if related_findings:
        parts.append("Based on the scanned contract, these findings are most relevant:")
        for finding in related_findings[:4]:
            law_info = f" ({finding.law_section})" if finding.law_section else ""
            parts.append(
                f"#### {finding.title} ({finding.severity.upper()}){law_info}\n"
                f"- Issue: {finding.explanation}\n"
                f"- Recommendation: {finding.recommendation}"
            )
            if finding.rewrite:
                parts.append(f"Suggested rewrite:\n```text\n{finding.rewrite}\n```")

    topic_answer = _topic_answer(message_lower)
    if topic_answer:
        parts.append(topic_answer)

    reference_snippets = _reference_snippets(message, laws_text, policies_text)
    if reference_snippets:
        parts.append("Relevant uploaded reference snippets:")
        parts.extend(f"- {snippet}" for snippet in reference_snippets[:3])

    contract_snippets = _contract_snippets(message, contract_text)
    if contract_snippets:
        parts.append("Relevant contract text I found:")
        parts.extend(f"- \"{snippet}\"" for snippet in contract_snippets[:3])

    if len(parts) == 1:
        if contract_text.strip():
            parts.append(
                "I can help with this contract. Ask me to summarize it, explain a specific clause, "
                "compare it against Malaysian law, or rewrite a risky term. For example: "
                "`What are the top risks?` or `Rewrite the termination clause fairly.`"
            )
        else:
            parts.append(
                "I can answer general Malaysian contract, employment, privacy, and company compliance questions. "
                "For document-specific advice, scan or open a contract first."
            )

    parts.append("Note: This is practical compliance guidance, not formal legal advice.")
    return "\n\n".join(parts)


def _asks_for_summary(message_lower: str) -> bool:
    return any(word in message_lower for word in ("summary", "summarize", "summarise", "overview", "top risk", "main risk"))


def _asks_for_rewrite(message_lower: str) -> bool:
    return any(word in message_lower for word in ("rewrite", "revise", "redraft", "improve clause", "better clause", "suggest wording"))


def _contract_summary(contract_text: str, findings: list[ClauseFinding]) -> str:
    if not contract_text.strip() and not findings:
        return "No scanned contract is attached yet. Upload or open a contract and I can summarize the risks."

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    top_findings = sorted(findings, key=lambda f: severity_order.get(f.severity, 9))[:5]
    intro = "Here is a quick compliance summary of the scanned contract:"
    inferred_risks = _infer_text_risks(contract_text)

    if not top_findings:
        if inferred_risks:
            return "\n".join([intro, *inferred_risks])
        return (
            f"{intro}\n\n"
            "- No deterministic high-risk findings were detected.\n"
            "- Still verify governing law, payment, termination, confidentiality, PDPA, and authority-to-sign clauses."
        )

    lines = [intro]
    for finding in top_findings:
        lines.append(f"- {finding.severity.upper()}: {finding.title} - {finding.recommendation}")
    for risk in inferred_risks:
        if risk not in lines:
            lines.append(risk)
    return "\n".join(lines)


def _infer_text_risks(contract_text: str) -> list[str]:
    text = contract_text.lower()
    risks: list[str] = []

    hour_matches = [int(match) for match in re.findall(r"\b(\d{2,3})\s*(?:hours|hrs)\b", text)]
    if any(hours > 45 for hours in hour_matches):
        risks.append(
            "- HIGH: Working hours appear to exceed 45 hours per week. Check Employment Act 1955 compliance and overtime treatment."
        )

    if any(term in text for term in ("non-compete", "non compete", "restraint of trade", "cannot work for")):
        risks.append(
            "- HIGH: A non-compete or restraint wording may be unenforceable after employment under Section 28 of the Contracts Act 1950. Prefer confidentiality and non-solicitation wording."
        )

    if any(term in text for term in ("personal data", "sensitive data", "process data", "data transfer", "third party data")):
        risks.append(
            "- MEDIUM: Personal data wording appears in the contract. Confirm PDPA notice, consent, disclosure, security, retention, and processor obligations."
        )

    if any(term in text for term in ("unlimited liability", "liable for all", "all damages", "indemnify against any and all")):
        risks.append(
            "- HIGH: Liability or indemnity wording may be broad. Consider a liability cap and clear carve-outs."
        )

    if any(term in text for term in ("may change", "sole discretion", "without notice", "unilaterally")):
        risks.append(
            "- MEDIUM: One-sided amendment or discretion wording may be unfair. Require written notice and mutual consent for material changes."
        )

    return risks[:5]


def _rewrite_answer(message: str, contract_text: str, findings: list[ClauseFinding]) -> str:
    related = _related_findings(message.lower(), findings)
    target = related[0] if related else next((f for f in findings if f.rewrite), None)
    if target and target.rewrite:
        return (
            f"Here is a safer rewrite for **{target.title}**:\n\n"
            f"```text\n{target.rewrite}\n```\n\n"
            f"Why: {target.explanation}"
        )
    if target:
        return (
            f"For **{target.title}**, use this drafting direction:\n\n"
            f"```text\nThe parties shall perform this obligation in a reasonable, proportionate, and mutually documented manner, "
            f"subject to applicable Malaysian law and any mandatory statutory rights that cannot be waived.\n```\n\n"
            f"Reason: {target.explanation}"
        )
    if contract_text.strip():
        return "Tell me which clause to rewrite, or ask `rewrite the riskiest clause` after running a scan."
    return "Share or scan a clause first, then I can draft a safer Malaysian-compliance version."


def _related_findings(message_lower: str, findings: list[ClauseFinding]) -> list[ClauseFinding]:
    query_words = _keywords(message_lower)
    if not query_words:
        return []

    scored: list[tuple[int, ClauseFinding]] = []
    for finding in findings:
        haystack = " ".join(
            [
                finding.title,
                finding.category,
                finding.excerpt,
                finding.explanation,
                finding.recommendation,
                finding.law_section or "",
            ]
        ).lower()
        score = sum(1 for word in query_words if word in haystack)
        if score:
            scored.append((score, finding))
    scored.sort(key=lambda item: (-item[0], item[1].severity != "critical", item[1].severity != "high"))
    return [finding for _, finding in scored]


def _topic_answer(message_lower: str) -> str:
    if any(word in message_lower for word in ("non-compete", "restraint", "compete", "solicitation")):
        return (
            "#### Non-compete and restraint clauses in Malaysia\n"
            "- Post-employment non-compete clauses are generally void under Section 28 of the Contracts Act 1950.\n"
            "- Prefer confidentiality, non-solicitation, return-of-property, and trade-secret protection clauses.\n"
            "- Keep restrictions narrow, tied to legitimate confidential information, and avoid blocking a person from working."
        )

    if any(word in message_lower for word in ("employment", "employee", "overtime", "leave", "salary", "wages", "working hour", "notice")):
        return (
            "#### Employment Act 1955 checks\n"
            "- Check normal working hours, overtime rates, rest days, public holiday work, wage deductions, and termination notice.\n"
            "- Current common compliance check: normal hours should not exceed 45 hours per week unless a lawful exception applies.\n"
            "- Maternity, paternity, sick leave, annual leave, and termination protections should not be contracted out of."
        )

    if any(word in message_lower for word in ("pdpa", "privacy", "personal data", "data", "consent", "disclosure")):
        return (
            "#### PDPA 2010 checks\n"
            "- Make sure the contract states what personal data is processed, why, who receives it, and how long it is retained.\n"
            "- Include notice-and-choice, consent, security safeguards, access/correction rights, and processor obligations.\n"
            "- Cross-border disclosure should be explicit and limited to what is necessary."
        )

    if any(word in message_lower for word in ("director", "company", "board", "secretary", "signatory", "companies act")):
        return (
            "#### Companies Act 2016 checks\n"
            "- Confirm the signing party has authority to bind the company.\n"
            "- Check director duties, approvals, reserved matters, indemnities, and execution blocks.\n"
            "- For Malaysian companies, execution commonly involves authorized directors or a director plus company secretary."
        )

    if any(word in message_lower for word in ("liability", "damages", "penalty", "indemnity", "cap", "limitation")):
        return (
            "#### Liability and damages checks\n"
            "- Watch for unlimited liability, one-sided indemnities, exclusion of all remedies, or arbitrary penalty sums.\n"
            "- Liquidated damages should be connected to a genuine estimate of loss and reasonable compensation principles.\n"
            "- A fairer clause usually includes a liability cap, carve-outs for fraud/confidentiality/data breach, and proportional remedies."
        )

    return ""


def _contract_snippets(message: str, contract_text: str) -> list[str]:
    if not contract_text.strip():
        return []
    query_words = _keywords(message.lower())
    sentences = re.split(r"(?<=[.!?])\s+|\n+", contract_text)
    scored: list[tuple[int, str]] = []
    for sentence in sentences:
        clean = " ".join(sentence.split())
        if len(clean) < 30:
            continue
        score = sum(1 for word in query_words if word in clean.lower())
        if score:
            scored.append((score, clean[:350]))
    scored.sort(reverse=True)
    return [snippet for _, snippet in scored[:3]]


def _reference_snippets(message: str, laws_text: str, policies_text: str) -> list[str]:
    combined = "\n".join(part for part in (laws_text, policies_text) if part)
    if not combined.strip():
        return []
    return _contract_snippets(message, combined)


def _keywords(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "what", "when", "where",
        "which", "about", "into", "does", "should", "could", "would", "please", "contract",
        "clause", "agreement", "tell", "explain", "make", "sure",
    }
    return {
        word
        for word in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text.lower())
        if word not in stopwords
    }

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Literal

from app.models import ClauseFinding
from app.services.clause_splitter import Section, split_into_sections
from app.services.retrieval import chunk_text, extract_keywords

RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class RiskRule:
    id: str
    category: str
    title: str
    severity: RiskLevel
    patterns: tuple[str, ...]
    explanation: str
    recommendation: str
    law_section: str
    law_text: str
    rewrite: str


RISK_RULES: tuple[RiskRule, ...] = (
    RiskRule(
        id="material-term-changes",
        category="General",
        title="Material term changes",
        severity="medium",
        patterns=(r"material changes", r"substantial modifications"),
        explanation="The contract may allow significant changes to its terms.",
        recommendation="Require written notice, mutual consent, and a right to terminate if material terms change.",
        law_section="Contracts Act 1950 (Section 10)",
        law_text="10. (1) All agreements are contracts if they are made by the free consent of parties competent to contract, for a lawful consideration and with a lawful object, and are not hereby expressly declared to be void.",
        rewrite="Any changes to the material terms of this Agreement shall be in writing and mutually agreed upon by both Parties.",
    ),
    RiskRule(
        id="unilateral-change",
        category="General",
        title="Unilateral modification rights",
        severity="high",
        patterns=(
            r"change.*pricing.*sole discretion",
            r"modify.*terms.*any time without.*notice",
            r"unilateral.*modify",
            r"reserve the right to change",
        ),
        explanation="The contract allows one party to unilaterally modify terms or pricing without the other's consent.",
        recommendation="Require mutual written consent for all modifications and price changes.",
        law_section="Contracts Act 1950 (Section 10 & 13)",
        law_text="10. (1) All agreements are contracts if they are made by the free consent of parties competent to contract... 13. Two or more persons are said to consent when they agree upon the same thing in the same sense.",
        rewrite="No modification to this Agreement or adjustment to pricing shall be valid unless made in writing and signed by the authorized representatives of both Parties.",
    ),
    RiskRule(
        id="auto-renewal",
        category="Duration",
        title="Automatic renewal clause",
        severity="medium",
        patterns=(
            r"automatically renew",
            r"automatic renewal",
            r"renew automatically",
            r"renew unless.*notice",
        ),
        explanation="The agreement will automatically renew unless a party gives notice to terminate before the deadline.",
        recommendation="Ensure the notice period for non-renewal is reasonable (e.g., 30-90 days) and track the deadline.",
        law_section="Contracts Act 1950 (Section 6 & 7)",
        law_text="6. A proposal is revoked— (a) by the communication of notice of revocation... 7. In order to convert a proposal into a promise the acceptance must— (a) be absolute and unqualified...",
        rewrite="This Agreement shall not automatically renew. Any renewal must be mutually agreed in writing by both Parties at least 30 days prior to the expiration of the current term.",
    ),
    RiskRule(
        id="excessive-working-hours",
        category="Employment",
        title="Working hours may exceed statutory limit",
        severity="critical",
        patterns=(
            r"(?:work|working|normal hours).{0,60}(?:4[6-9]|[5-9]\d)\s*(?:hours|hrs)\s*(?:per|a)?\s*week",
            r"(?:4[6-9]|[5-9]\d)\s*(?:hours|hrs)\s*(?:per|a)?\s*week",
        ),
        explanation="The clause appears to require weekly working hours above the Malaysian statutory baseline.",
        recommendation="Keep normal working hours within 45 hours per week unless a lawful exception applies, and state overtime eligibility clearly.",
        law_section="Employment Act 1955 (Section 60A)",
        law_text="Section 60A regulates hours of work and was amended to reduce the normal weekly working-hours limit to 45 hours.",
        rewrite="The Employee's normal working hours shall not exceed forty-five (45) hours per week, excluding lawful overtime approved and paid in accordance with applicable Malaysian employment law.",
    ),
    RiskRule(
        id="post-employment-non-compete",
        category="Employment",
        title="Post-employment non-compete restriction",
        severity="high",
        patterns=(
            r"non[-\s]?compete",
            r"not\s+work\s+for\s+(?:a\s+)?competitor",
            r"restrain(?:ed)?\s+from\s+(?:working|employment|trade)",
            r"after\s+termination.{0,80}(?:compete|competitor|similar business)",
        ),
        explanation="Post-employment restraint of trade clauses are generally void in Malaysia unless a narrow statutory exception applies.",
        recommendation="Replace post-employment non-compete wording with focused confidentiality, non-solicitation, and return-of-property obligations.",
        law_section="Contracts Act 1950 (Section 28)",
        law_text="Section 28 provides that every agreement by which anyone is restrained from exercising a lawful profession, trade, or business is void to that extent, subject to narrow statutory exceptions.",
        rewrite="After termination, the Employee shall remain bound by confidentiality obligations and shall not misuse the Company's trade secrets or confidential information, but nothing in this Agreement prevents the Employee from lawful employment or business activity.",
    ),
    RiskRule(
        id="no-overtime-premium",
        category="Employment",
        title="Overtime premium missing",
        severity="critical",
        patterns=(
            r"overtime.{0,80}(?:standard|normal|ordinary)\s+(?:hourly\s+)?rate.{0,80}(?:no|without)\s+(?:additional\s+)?premium",
            r"overtime.{0,80}(?:no|without)\s+(?:additional\s+)?(?:premium|extra pay|overtime rate)",
        ),
        explanation="The clause appears to remove or reduce statutory overtime premium treatment.",
        recommendation="State that overtime will be paid at the applicable statutory overtime rate under Malaysian employment law.",
        law_section="Employment Act 1955 (Section 60A)",
        law_text="Section 60A regulates hours of work and overtime. Overtime should be paid at the applicable statutory rate rather than ordinary pay only.",
        rewrite="Overtime shall be compensated at the applicable statutory overtime rate in accordance with Section 60A of the Employment Act 1955 and related regulations.",
    ),
    RiskRule(
        id="public-holiday-no-pay",
        category="Employment",
        title="Public holiday work without statutory pay",
        severity="critical",
        patterns=(
            r"public holidays?.{0,80}(?:without|no)\s+(?:additional\s+)?(?:compensation|pay|payment)",
            r"work on public holidays?.{0,80}(?:standard|normal|ordinary)\s+rate",
        ),
        explanation="The clause appears to require work on public holidays without the statutory additional compensation.",
        recommendation="Provide public holiday pay in accordance with Malaysian statutory requirements.",
        law_section="Employment Act 1955 (Section 60D)",
        law_text="Section 60D regulates holidays and work on holidays, including payment treatment for employees required to work on a holiday.",
        rewrite="If the Employee is required to work on a public holiday, the Employee shall be paid in accordance with Section 60D of the Employment Act 1955.",
    ),
    RiskRule(
        id="unlawful-short-termination-notice",
        category="Employment",
        title="Termination notice may be below statutory minimum",
        severity="high",
        patterns=(
            r"terminate.{0,80}(?:24|twenty[-\s]?four)\s+hours?\s+(?:written\s+)?notice",
            r"(?:one|1)\s+day(?:'s)?\s+(?:written\s+)?notice.{0,60}terminat",
            r"terminat.{0,80}(?:one|1)\s+day(?:'s)?\s+(?:written\s+)?notice",
        ),
        explanation="The clause appears to permit termination on extremely short notice, which may be inconsistent with Malaysian statutory notice requirements for employees.",
        recommendation="Use the statutory minimum notice period under the Employment Act 1955 or a longer contractual notice period.",
        law_section="Employment Act 1955 (Section 12)",
        law_text="Section 12 prescribes minimum notice periods for termination of contracts of service unless a lawful exception applies.",
        rewrite="Either party may terminate this Agreement by giving not less than the statutory minimum notice required under Section 12 of the Employment Act 1955, or any longer notice period stated in this Agreement.",
    ),
    RiskRule(
        id="summary-dismissal-without-due-inquiry",
        category="Employment",
        title="Immediate dismissal without due inquiry",
        severity="critical",
        patterns=(
            r"terminate.{0,80}immediately.{0,80}without\s+notice.{0,80}(?:any reason|deemed sufficient|sole discretion)",
            r"without\s+notice\s+or\s+compensation.{0,80}(?:any reason|deemed sufficient|sole discretion)",
            r"(?:employer|company).{0,80}(?:deems?|determines?).{0,40}sufficient.{0,80}terminat",
        ),
        explanation="The clause appears to allow immediate dismissal without a stated misconduct process or due inquiry.",
        recommendation="Limit immediate termination to lawful grounds such as proven misconduct after due inquiry, and preserve statutory termination protections.",
        law_section="Employment Act 1955 (Section 14)",
        law_text="Section 14 addresses termination for misconduct after due inquiry and should not be replaced by a blanket employer discretion clause.",
        rewrite="The Employer may terminate employment without notice only where permitted by applicable law, including for misconduct established after due inquiry in accordance with Section 14 of the Employment Act 1955.",
    ),
    RiskRule(
        id="insufficient-annual-leave",
        category="Employment",
        title="Annual leave below statutory minimum",
        severity="high",
        patterns=(
            r"annual leave.{0,60}(?:[0-7])\s+days?",
            r"(?:[0-7])\s+days?.{0,40}annual leave",
            r"(?:entitled|entitlement).{0,40}(?:[0-7])\s+days?.{0,40}annual leave",
        ),
        explanation="The annual leave entitlement appears to be below the Malaysian statutory minimum.",
        recommendation="Set annual leave at least to the statutory minimum and vary it by length of service where required.",
        law_section="Employment Act 1955 (Section 60E)",
        law_text="Section 60E provides statutory annual leave entitlements, including minimum days based on length of service.",
        rewrite="Annual leave shall be granted at not less than the statutory minimum required under Section 60E of the Employment Act 1955, including service-based increases where applicable.",
    ),
    RiskRule(
        id="annual-leave-forfeiture",
        category="Employment",
        title="Unused annual leave forfeiture",
        severity="high",
        patterns=(
            r"unused\s+(?:annual\s+)?leave.{0,80}(?:forfeit|forfeited)",
            r"(?:annual\s+)?leave.{0,80}(?:not\s+be\s+carried\s+forward|no\s+carry\s+forward|not\s+.*encashed)",
            r"leave.{0,80}(?:forfeit|forfeited).{0,80}(?:end of each calendar year|year end)",
        ),
        explanation="A blanket forfeiture of unused leave can undermine statutory annual leave entitlement and payment treatment.",
        recommendation="State how statutory annual leave is taken, carried forward, or paid in accordance with Malaysian employment law.",
        law_section="Employment Act 1955 (Section 60E)",
        law_text="Section 60E provides statutory annual leave entitlements and payment treatment for annual leave.",
        rewrite="Unused annual leave shall be managed in accordance with Section 60E of the Employment Act 1955, including any statutory carry-forward or payment in lieu where applicable.",
    ),
    RiskRule(
        id="insufficient-sick-leave",
        category="Employment",
        title="Sick leave below statutory minimum",
        severity="high",
        patterns=(
            r"sick leave.{0,60}(?:[0-9]|1[0-3])\s+days?",
            r"(?:[0-9]|1[0-3])\s+days?.{0,40}sick leave",
            r"(?:entitled|entitlement).{0,40}(?:[0-9]|1[0-3])\s+days?.{0,40}sick leave",
        ),
        explanation="The sick leave entitlement appears to be below the Malaysian statutory minimum.",
        recommendation="Set sick leave at least to the statutory minimum and distinguish hospitalization entitlement where applicable.",
        law_section="Employment Act 1955 (Section 60F)",
        law_text="Section 60F provides statutory sick leave entitlements, including non-hospitalization and hospitalization leave.",
        rewrite="Sick leave shall be granted at not less than the statutory minimum required under Section 60F of the Employment Act 1955.",
    ),
    RiskRule(
        id="unclear-company-execution-authority",
        category="Corporate authority",
        title="Company execution authority is unclear",
        severity="high",
        patterns=(
            r"(?:any employee|any staff).{0,80}(?:bind|execute|sign).{0,80}(?:company|corporation)",
            r"(?:bind|execute|sign).{0,80}(?:company|corporation).{0,80}without.{0,40}(?:director|board|authori[sz]ed)",
            r"no\s+(?:board|director|authori[sz]ed signatory)\s+(?:approval|authority).{0,80}(?:required|needed)",
        ),
        explanation="The clause appears to let a company be bound without clear board, director, or authorised-signatory authority.",
        recommendation="Require execution by directors, authorised signatories, or another clearly approved company representative.",
        law_section="Companies Act 2016 (Section 66)",
        law_text="Section 66 addresses company execution of documents. Contracts should clearly identify authority to execute or bind the company.",
        rewrite="This Agreement shall be executed only by directors or duly authorised signatories with authority to bind the Company in accordance with the Companies Act 2016.",
    ),
    RiskRule(
        id="hidden-fees",
        category="Fees and payment",
        title="Potential hidden fees or pass-through charges",
        severity="high",
        patterns=(
            r"additional fees?", r"administrative charges?", r"pass[-\s]?through costs?",
            r"fees .* subject to change", r"extra charges?", r"separate charges?",
            r"pricing .* may be adjusted",
        ),
        explanation="The contract may allow extra charges beyond the headline price.",
        recommendation="List all charge categories, caps, approval requirements, and invoice dispute rights.",
        law_section="Contracts Act 1950 (Section 10)",
        law_text="10. (1) All agreements are contracts if they are made by the free consent of parties competent to contract, for a lawful consideration and with a lawful object, and are not hereby expressly declared to be void.",
        rewrite="No additional administrative fees, pass-through charges, or extra costs shall be charged unless explicitly specified in this Agreement or agreed in writing.",
    ),
    RiskRule(
        id="broad-liability-waiver",
        category="Liability",
        title="Broad limitation or waiver of liability",
        severity="critical",
        patterns=(
            r"not liable for .* indirect", r"limitation of liability", r"liability .* capped",
            r"waive .* damages", r"exclude .* damages", r"disclaim .* liability",
            r"consequential damages",
        ),
        explanation="Liability may be excluded or capped too broadly for enterprise risk tolerance.",
        recommendation="Carve out fraud, confidentiality, data breach, IP infringement, and gross negligence.",
        law_section="Contracts Act 1950 (Section 29)",
        law_text="29. Every agreement, by which any party thereto is restricted absolutely from enforcing his rights under or in respect of any contract, by the usual legal proceedings in the ordinary tribunals, or which limits the time within which he may thus enforce his rights, is void to that extent.",
        rewrite="Neither Party excludes or limits its liability for fraud, gross negligence, intellectual property infringement, or breach of confidentiality.",
    ),
    RiskRule(
        id="data-use",
        category="Data and privacy",
        title="Broad data use or transfer permission",
        severity="high",
        patterns=(
            r"use .* data .* improve", r"share .* data .* affiliates?", r"transfer .* personal data",
            r"process .* data .* analytics", r"data .* third parties", r"personal information .* affiliates?",
            r"personal data.{0,120}(?:any\s+third\s+party|third\s+part(?:y|ies)).{0,120}any\s+purpose",
            r"personal data.{0,160}for\s+any\s+purpose",
            r"personal data.{0,120}(?:marketing partners|recruitment agencies|government bodies)",
        ),
        explanation="The vendor may use, share, or transfer enterprise/customer data broadly.",
        recommendation="Limit data use to service delivery, require data processing terms, and define retention/deletion duties.",
        law_section="PDPA 2010 (Section 6 - General Principle)",
        law_text="6. (1) A data user shall not, in the case of personal data other than sensitive personal data, process personal data about a data subject unless the data subject has given his consent to the processing of the personal data.",
        rewrite="The processing of personal data shall be limited strictly to the performance of the services, and shall not be shared with third parties without prior written consent.",
    ),
    RiskRule(
        id="pdpa-rights-waiver",
        category="Data and privacy",
        title="Attempted waiver of PDPA rights",
        severity="critical",
        patterns=(
            r"waive(?:s|d)?\s+all\s+rights\s+under\s+(?:the\s+)?(?:personal data protection act|pdpa)",
            r"(?:personal data protection act|pdpa).{0,80}(?:rights|protections).{0,40}(?:waived|do not apply|shall not apply)",
        ),
        explanation="The clause attempts to waive statutory personal data rights or protections.",
        recommendation="Remove the waiver and instead describe lawful purposes, notices, consent, access/correction rights, retention, and security safeguards.",
        law_section="PDPA 2010 (Act 709)",
        law_text="PDPA 2010 regulates commercial processing of personal data and includes statutory principles and data subject rights that should not be removed by blanket contract waiver.",
        rewrite="Nothing in this Agreement limits any rights or protections available under the Personal Data Protection Act 2010. Personal data shall be processed only for lawful, specific, and notified purposes.",
    ),
    RiskRule(
        id="exclusive-remedy",
        category="Remedies",
        title="Exclusive remedy restriction",
        severity="medium",
        patterns=(
            r"sole and exclusive remedy", r"exclusive remedy", r"limited to .* remedy", r"only remedy",
        ),
        explanation="Available remedies may be narrowed even when business harm is larger.",
        recommendation="Preserve injunctive relief, statutory rights, and remedies for severe breaches.",
        law_section="Contracts Act 1950 (Section 29)",
        law_text="29. Every agreement, by which any party thereto is restricted absolutely from enforcing his rights under or in respect of any contract, by the usual legal proceedings in the ordinary tribunals, or which limits the time within which he may thus enforce his rights, is void to that extent.",
        rewrite="The remedies set forth in this Agreement are cumulative and in addition to, not in lieu of, any other remedies available at law or in equity.",
    ),
    RiskRule(
        id="ambiguous-incorporation",
        category="Referenced documents",
        title="Terms incorporated by external reference",
        severity="medium",
        patterns=(
            r"incorporated by reference", r"available at https?://", r"as updated from time to time",
            r"posted on .* website", r"online terms?", r"external terms?",
        ),
        explanation="Important terms may live outside the uploaded contract and change later.",
        recommendation="Attach referenced terms as exhibits and freeze the applicable version at signature.",
        law_section="Contracts Act 1950 (Section 30)",
        law_text="30. Agreements, the meaning of which is not certain, or capable of being made certain, are void.",
        rewrite="Terms incorporated by external reference are frozen as of the date of signature and cannot be unilaterally updated by either Party.",
    ),
    # --- NDA / confidentiality-specific rules ---
    RiskRule(
        id="overbroad-confidential-definition",
        category="Confidentiality",
        title="Overbroad definition of confidential information",
        severity="high",
        patterns=(
            r"absolutely all information", r"in any form whatsoever", r"publicly available.{0,40}confidential",
            r"regardless of (?:whether|how) (?:marked|disclosed)",
        ),
        explanation="Defining confidential information to include publicly available or independently developed information is overbroad and may be unenforceable.",
        recommendation="Limit the definition to non-public information that is marked confidential or reasonably understood to be confidential, with standard carve-outs (public domain, independently developed, already known).",
        law_section="Contracts Act 1950 (Section 28)",
        law_text="28. Every agreement by which anyone is restrained from exercising a lawful profession, trade, or business of any kind, is to that extent void.",
        rewrite="Confidential Information shall not include information that is publicly known, already possessed by the receiving party, or independently developed.",
    ),
    RiskRule(
        id="indefinite-duration",
        category="Duration",
        title="Indefinite or permanent contractual obligation",
        severity="high",
        patterns=(
            r"permanently and indefinitely", r"without any expiry date", r"perpetually binding",
            r"remain.{0,20}permanently binding", r"no expiration",
        ),
        explanation="Obligations with no time limit are commercially unusual and may be struck down by courts as an unreasonable restraint.",
        recommendation="Specify a fixed term (commonly 2-5 years for confidentiality) after which obligations lapse, unless renewed by agreement.",
        law_section="Contracts Act 1950 (Section 28)",
        law_text="28. Every agreement by which anyone is restrained from exercising a lawful profession, trade, or business of any kind, is to that extent void.",
        rewrite="The obligations of confidentiality under this Agreement shall survive the termination or expiration of this Agreement for a period of three (3) years.",
    ),
    RiskRule(
        id="no-legal-disclosure-carveout",
        category="Compliance",
        title="No carve-out for legally required disclosure",
        severity="critical",
        patterns=(
            r"no exception shall apply", r"regardless of.{0,30}court order", r"required by law.{0,30}shall not apply",
            r"including where disclosure is required by law",
        ),
        explanation="A clause that prohibits disclosure even when required by law, court order, or regulator is unenforceable and may expose a party to contempt of court if relied upon.",
        recommendation="Add a standard carve-out permitting disclosure required by law or valid court/regulatory order, with prior notice to the other party where legally permitted.",
        law_section="Contracts Act 1950 (Section 29)",
        law_text="29. Every agreement, by which any party thereto is restricted absolutely from enforcing his rights under or in respect of any contract, by the usual legal proceedings in the ordinary tribunals, or which limits the time within which he may thus enforce his rights, is void to that extent.",
        rewrite="A receiving party may disclose Confidential Information if required by law or court order, provided it gives prompt written notice to the disclosing party.",
    ),
    RiskRule(
        id="disproportionate-penalty",
        category="Remedies",
        title="Disproportionate liquidated damages clause",
        severity="critical",
        patterns=(
            r"liquidated damages.{0,60}regardless of actual loss",
            r"damages of no less than RM\s?[\d,]{4,}",
            r"penalty of (?:RM|USD|\$)\s?[\d,]{4,}",
        ),
        explanation="A fixed damages amount unrelated to actual loss may be treated as an unenforceable penalty rather than a genuine pre-estimate of loss under contract law.",
        recommendation="Tie liquidated damages to a reasonable pre-estimate of loss, or rely on general damages assessed by a court instead of a large fixed figure.",
        law_section="Contracts Act 1950 (Section 75)",
        law_text="75. When a contract has been broken, if a sum is named in the contract as the amount to be paid in case of such breach, or if the contract contains any other stipulation by way of penalty, the party complaining of the breach is entitled, whether or not actual damage or loss is proved to have been caused thereby, to receive from the party who has broken the contract reasonable compensation not exceeding the amount so named or the penalty stipulated for.",
        rewrite="Any damages for breach of contract shall be limited to actual, proven losses, up to a reasonable pre-estimate of loss.",
    ),
)


SELECTABLE_LAW_IDS = ("employment", "pdpa", "companies")
LAW_SECTION_MARKERS = {
    "employment": ("employment act",),
    "pdpa": ("pdpa", "personal data protection"),
    "companies": ("companies act",),
}

POLICY_CONFLICT_TERMS = (
    "without consent", "without prior consent", "without approval", "sole discretion",
    "any purpose", "any third party", "no obligation", "not required", "waive",
    "waives", "unlimited", "forfeited", "no additional compensation",
)
POLICY_REQUIREMENT_TERMS = (
    "must", "shall", "required", "requires", "minimum", "at least", "no less than",
    "only", "prior consent", "approval", "confidential", "prohibited", "must not",
    "shall not", "may not", "not disclose", "not share", "not transfer",
)


def analyze_text(
    text: str,
    selected_laws: Iterable[str] | None = None,
    policies_text: str = "",
) -> list[ClauseFinding]:
    """
    Splits the contract into its real numbered sections/clauses, then runs
    every rule against each clause individually. Returns one ClauseFinding
    per clause (status 'low' if no rule matched, otherwise the matched
    rule's severity) so the full original structure can be reconstructed
    by the frontend.
    """
    sections = split_into_sections(text)
    selected_law_ids = _normalise_selected_laws(selected_laws)
    findings: list[ClauseFinding] = []

    for section in sections:
        section_label = section.title or "General"
        for clause in section.clauses:
            clean = " ".join(clause.text.split())
            if not clean:
                continue

            matched_rules = _match_clause(clean, selected_law_ids)
            policy_match = _match_policy_clause(clean, policies_text)

            if matched_rules or policy_match:
                for match_index, (matched_rule, excerpt, confidence) in enumerate(matched_rules, start=1):
                    finding_id = f"{matched_rule.id}-{clause.id}"
                    if len(matched_rules) > 1:
                        finding_id = f"{finding_id}-{match_index}"
                    findings.append(
                        ClauseFinding(
                            id=finding_id,
                            category=section_label,
                            title=matched_rule.title,
                            severity=matched_rule.severity,
                            confidence=confidence,
                            excerpt=f"{clause.id} {clean}",
                            explanation=matched_rule.explanation,
                            recommendation=matched_rule.recommendation,
                            line_number=None,
                            matched_snippet=excerpt,
                            law_section=matched_rule.law_section,
                            law_text=matched_rule.law_text,
                            rewrite=matched_rule.rewrite,
                        )
                    )
                if policy_match:
                    policy_excerpt, policy_reason, confidence = policy_match
                    findings.append(
                        ClauseFinding(
                            id=f"company-policy-conflict-{clause.id}",
                            category=section_label,
                            title="Possible company policy conflict",
                            severity="high",
                            confidence=confidence,
                            excerpt=f"{clause.id} {clean}",
                            explanation=policy_reason,
                            recommendation="Review this clause against the linked company policy and align the contract wording with the policy requirement or obtain documented approval for an exception.",
                            line_number=None,
                            matched_snippet=clean,
                            law_section="Company policy",
                            law_text=policy_excerpt,
                            rewrite="Revise this clause so it follows the linked company policy requirement, or document an approved policy exception before signing.",
                        )
                    )
            else:
                # No issue found — still emit a "low" finding so the clause
                # appears in the reconstructed document as a clean/ok clause.
                findings.append(
                    ClauseFinding(
                        id=f"clean-{clause.id}",
                        category=section_label,
                        title="No issues detected",
                        severity="low",
                        confidence=0.5,
                        excerpt=f"{clause.id} {clean}",
                        explanation="",
                        recommendation="",
                        line_number=None,
                        matched_snippet=None,
                        law_section=None,
                        law_text=None,
                        rewrite=None,
                    )
                )
    return findings


def _match_policy_clause(clean_line: str, policies_text: str) -> tuple[str, str, float] | None:
    if not policies_text.strip():
        return None

    clause_lower = clean_line.lower()
    if not any(term in clause_lower for term in POLICY_CONFLICT_TERMS):
        return None

    clause_words = extract_keywords(clean_line)
    if len(clause_words) < 3:
        return None

    best: tuple[int, str] | None = None
    for chunk in chunk_text(policies_text, chunk_chars=700):
        chunk_lower = chunk.lower()
        if not any(term in chunk_lower for term in POLICY_REQUIREMENT_TERMS):
            continue
        chunk_words = extract_keywords(chunk)
        overlap = len(clause_words & chunk_words)
        if overlap < 2:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, chunk)

    if not best:
        return None

    policy_excerpt = " ".join(best[1].split())
    reason = (
        "The clause contains broad permission or waiver language that appears inconsistent "
        "with a related mandatory/prohibitive requirement in the linked company policy."
    )
    confidence = min(0.9, 0.68 + (best[0] * 0.04))
    return (_excerpt_around(policy_excerpt, 0, min(len(policy_excerpt), 220), radius=220), reason, confidence)


def _normalise_selected_laws(selected_laws: Iterable[str] | None) -> set[str] | None:
    if selected_laws is None:
        return None
    return {
        str(law).strip().lower()
        for law in selected_laws
        if str(law).strip().lower() in SELECTABLE_LAW_IDS
    }


def _rule_matches_selected_laws(rule: RiskRule, selected_law_ids: set[str] | None) -> bool:
    if selected_law_ids is None:
        return True
    section = rule.law_section.lower()
    return any(
        any(marker in section for marker in LAW_SECTION_MARKERS[law_id])
        for law_id in selected_law_ids
    )


def _match_clause(clean_line: str, selected_law_ids: set[str] | None = None) -> list[tuple[RiskRule, str, float]]:
    matches: list[tuple[RiskRule, str, float]] = []
    for rule in RISK_RULES:
        if not _rule_matches_selected_laws(rule, selected_law_ids):
            continue
        for pattern in rule.patterns:
            match = re.search(pattern, clean_line, re.IGNORECASE)
            if match:
                matches.append((rule, _excerpt_around(clean_line, match.start(), match.end()), 0.82))
                break
    return matches


def calculate_risk_score(findings: list[ClauseFinding]) -> int:
    weights = {"low": 0, "medium": 18, "high": 28, "critical": 40}
    score = sum(weights[finding.severity] for finding in findings)
    return min(score, 100)


def risk_level_from_score(score: int) -> RiskLevel:
    if score >= 80:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _excerpt_around(text: str, start: int, end: int, radius: int = 200) -> str:
    left = max(start - radius, 0)
    if left > 0:
        space_idx = text.find(" ", left)
        if space_idx != -1 and space_idx < start:
            left = space_idx + 1

    right = min(end + radius, len(text))
    if right < len(text):
        space_idx = text.rfind(" ", start, right)
        if space_idx != -1 and space_idx > end:
            right = space_idx

    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""
    return f"{prefix}{text[left:right]}{suffix}"

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.models import ClauseFinding

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


RISK_RULES: tuple[RiskRule, ...] = (
    RiskRule(
        id="placeholder-rule",
        category="General",
        title="Placeholder rule",
        severity="low",
        patterns=(
            r"placeholder",
        ),
        explanation="Placeholder.",
        recommendation="Replace with real rule.",
    ),

    RiskRule(
        id="material-term-changes",
        category="General",
        title="Material term changes",
        severity="medium",
        patterns=(
            r"material changes",
            r"substantial modifications",
        ),
        explanation="The contract may allow significant changes to its terms.",
        recommendation="Require written notice, mutual consent, and a right to terminate if material terms change.",
    ),

    RiskRule(
        id="hidden-fees",
        category="Fees and payment",
        title="Potential hidden fees or pass-through charges",
        severity="high",
        patterns=(
            r"additional fees?",
            r"administrative charges?",
            r"pass[-\s]?through costs?",
            r"fees .* subject to change",
            r"extra charges?",
            r"separate charges?",
            r"pricing .* may be adjusted",
        ),
        explanation="The contract may allow extra charges beyond the headline price.",
        recommendation="List all charge categories, caps, approval requirements, and invoice dispute rights.",
    ),
    RiskRule(
        id="broad-liability-waiver",
        category="Liability",
        title="Broad limitation or waiver of liability",
        severity="critical",
        patterns=(
            r"not liable for .* indirect",
            r"limitation of liability",
            r"liability .* capped",
            r"waive .* damages",
            r"exclude .* damages",
            r"disclaim .* liability",
            r"consequential damages",
        ),
        explanation="Liability may be excluded or capped too broadly for enterprise risk tolerance.",
        recommendation="Carve out fraud, confidentiality, data breach, IP infringement, and gross negligence.",
    ),
    RiskRule(
        id="data-use",
        category="Data and privacy",
        title="Broad data use or transfer permission",
        severity="high",
        patterns=(
            r"use .* data .* improve",
            r"share .* data .* affiliates?",
            r"transfer .* personal data",
            r"process .* data .* analytics",
            r"data .* third parties",
            r"personal information .* affiliates?",
        ),
        explanation="The vendor may use, share, or transfer enterprise/customer data broadly.",
        recommendation="Limit data use to service delivery, require data processing terms, and define retention/deletion duties.",
    ),
    RiskRule(
        id="exclusive-remedy",
        category="Remedies",
        title="Exclusive remedy restriction",
        severity="medium",
        patterns=(
            r"sole and exclusive remedy",
            r"exclusive remedy",
            r"limited to .* remedy",
            r"only remedy",
        ),
        explanation="Available remedies may be narrowed even when business harm is larger.",
        recommendation="Preserve injunctive relief, statutory rights, and remedies for severe breaches.",
    ),
    RiskRule(
        id="ambiguous-incorporation",
        category="Referenced documents",
        title="Terms incorporated by external reference",
        severity="medium",
        patterns=(
            r"incorporated by reference",
            r"available at https?://",
            r"as updated from time to time",
            r"posted on .* website",
            r"online terms?",
            r"external terms?",
        ),
        explanation="Important terms may live outside the uploaded contract and change later.",
        recommendation="Attach referenced terms as exhibits and freeze the applicable version at signature.",
    ),
)


def analyze_text(text: str) -> list[ClauseFinding]:
    findings: list[ClauseFinding] = []
    lines = text.splitlines() or [text]

    for rule in RISK_RULES:
        match = _find_rule_match(rule, lines)
        if match is None:
            continue

        line_number, excerpt, confidence = match
        findings.append(
            ClauseFinding(
                id=rule.id,
                category=rule.category,
                title=rule.title,
                severity=rule.severity,
                confidence=confidence,
                excerpt=excerpt,
                explanation=rule.explanation,
                recommendation=rule.recommendation,
                line_number=line_number,
            )
        )

    return findings


def calculate_risk_score(findings: list[ClauseFinding]) -> int:
    weights = {"low": 10, "medium": 18, "high": 28, "critical": 40}
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


def _find_rule_match(rule: RiskRule, lines: list[str]) -> tuple[int | None, str, float] | None:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in rule.patterns]

    for index, line in enumerate(lines, start=1):
        clean_line = " ".join(line.split())
        if not clean_line:
            continue

        for pattern in compiled:
            match = pattern.search(clean_line)
            if match:
                return index, _excerpt_around(clean_line, match.start(), match.end()), 0.82

    joined = " ".join(line.strip() for line in lines if line.strip())
    for pattern in compiled:
        match = pattern.search(joined)
        if match:
            return None, _excerpt_around(joined, match.start(), match.end()), 0.72

    return None


def _excerpt_around(text: str, start: int, end: int, radius: int = 160) -> str:
    left = max(start - radius, 0)
    right = min(end + radius, len(text))
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""
    return f"{prefix}{text[left:right]}{suffix}"
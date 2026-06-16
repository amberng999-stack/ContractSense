from app.services.risk_rules import analyze_text, calculate_risk_score, risk_level_from_score


def test_detects_hidden_terms() -> None:
    text = """
    The provider may change the pricing at its sole discretion without prior notice.
    This agreement will automatically renew unless the customer gives written notice.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert "unilateral-change" in ids
    assert "auto-renewal" in ids


def test_detects_english_hidden_fees_and_liability() -> None:
    text = """
    Provider may charge additional fees and administrative charges.
    The limitation of liability is capped at one month of fees.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert "hidden-fees" in ids
    assert "broad-liability-waiver" in ids


def test_risk_score_maps_to_level() -> None:
    findings = analyze_text("The agreement may modify terms at any time without prior notice.")

    score = calculate_risk_score(findings)

    assert score > 0
    assert risk_level_from_score(score) in {"medium", "high", "critical"}
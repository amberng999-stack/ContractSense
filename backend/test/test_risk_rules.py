from app.services.risk_rules import analyze_text, calculate_risk_score, risk_level_from_score


def test_detects_hidden_terms() -> None:
    text = """
    1. GENERAL TERMS
    1.1 The provider may change the pricing at its sole discretion without prior notice.
    1.2 This agreement will automatically renew unless the customer gives written notice.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert any(fid.startswith("unilateral-change") for fid in ids)
    assert any(fid.startswith("auto-renewal") for fid in ids)


def test_detects_english_hidden_fees_and_liability() -> None:
    text = """
    1. FEES AND LIABILITY
    1.1 Provider may charge additional fees and administrative charges.
    1.2 The limitation of liability is capped at one month of fees.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert any(fid.startswith("hidden-fees") for fid in ids)
    assert any(fid.startswith("broad-liability-waiver") for fid in ids)


def test_risk_score_maps_to_level() -> None:
    findings = analyze_text("The agreement may modify terms at any time without prior notice.")

    score = calculate_risk_score(findings)

    assert score > 0
    assert risk_level_from_score(score) in {"medium", "high", "critical"}


def test_detects_employment_hours_and_non_compete() -> None:
    text = """
    1. EMPLOYMENT TERMS
    1.1 The Employee shall work 60 hours per week as normal working hours.
    1.2 After termination, the Employee shall not work for a competitor for two years.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert any(fid.startswith("excessive-working-hours") for fid in ids)
    assert any(fid.startswith("post-employment-non-compete") for fid in ids)


def test_detects_specific_employment_and_pdpa_errors() -> None:
    text = """
    1. EMPLOYMENT AND DATA TERMS
    1.1 All overtime shall be compensated at the standard hourly rate with no additional premium.
    1.2 The Employee may be required to work on public holidays without additional compensation.
    1.3 The Employee shall receive 5 days annual leave per year.
    1.4 Sick leave entitlement shall be 5 days per year.
    1.5 The Employee waives all rights under the Personal Data Protection Act 2010.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert any(fid.startswith("no-overtime-premium") for fid in ids)
    assert any(fid.startswith("public-holiday-no-pay") for fid in ids)
    assert any(fid.startswith("insufficient-annual-leave") for fid in ids)
    assert any(fid.startswith("insufficient-sick-leave") for fid in ids)
    assert any(fid.startswith("pdpa-rights-waiver") for fid in ids)


def test_detects_problem_contract_employment_and_pdpa_clauses() -> None:
    text = """
    4. LEAVE
    4.1 Unused leave shall be forfeited at the end of each calendar year and shall not be carried forward or encashed.
    5. TERMINATION
    5.1 Either party may terminate this Agreement by providing 24 hours written notice to the other party.
    5.2 The Employer may terminate the Employee's services immediately and without notice or compensation for any reason deemed sufficient by the Employer.
    6. PERSONAL DATA
    6.1 The Employee consents to the Employer collecting, processing, and disclosing their personal data to any third party for any purpose the Employer deems necessary.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert any(fid.startswith("annual-leave-forfeiture") for fid in ids)
    assert any(fid.startswith("unlawful-short-termination-notice") for fid in ids)
    assert any(fid.startswith("summary-dismissal-without-due-inquiry") for fid in ids)
    assert any(fid.startswith("data-use") for fid in ids)


def test_detects_decimal_clauses_without_section_headers() -> None:
    text = """
    This Employment Agreement is made between the parties.
    1.1 The Employee shall work 60 hours per week as normal working hours.
    1.2 After termination, the Employee shall not work for a competitor for two years.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert any(fid.startswith("excessive-working-hours-1.1") for fid in ids)
    assert any(fid.startswith("post-employment-non-compete-1.2") for fid in ids)


def test_detects_multiple_issues_in_same_clause() -> None:
    text = """
    1. DATA TERMS
    1.1 The Company may transfer personal data to affiliates and third parties for analytics, and the Employee waives all rights under the Personal Data Protection Act 2010.
    """

    findings = analyze_text(text)

    ids = {finding.id for finding in findings}
    assert any(fid.startswith("data-use-1.1") for fid in ids)
    assert any(fid.startswith("pdpa-rights-waiver-1.1") for fid in ids)


def test_filters_findings_by_selected_laws() -> None:
    text = """
    1. SELECTED LAW TERMS
    1.1 The Employee shall work 60 hours per week as normal working hours.
    1.2 The Employee waives all rights under the Personal Data Protection Act 2010.
    1.3 Any employee may sign and bind the company without board approval.
    """

    employment_findings = analyze_text(text, selected_laws=["employment"])
    employment_ids = {finding.id for finding in employment_findings}
    assert any(fid.startswith("excessive-working-hours") for fid in employment_ids)
    assert not any(fid.startswith("pdpa-rights-waiver") for fid in employment_ids)
    assert not any(fid.startswith("unclear-company-execution-authority") for fid in employment_ids)

    pdpa_findings = analyze_text(text, selected_laws=["pdpa"])
    pdpa_ids = {finding.id for finding in pdpa_findings}
    assert any(fid.startswith("pdpa-rights-waiver") for fid in pdpa_ids)
    assert not any(fid.startswith("excessive-working-hours") for fid in pdpa_ids)

    companies_findings = analyze_text(text, selected_laws=["companies"])
    companies_ids = {finding.id for finding in companies_findings}
    assert any(fid.startswith("unclear-company-execution-authority") for fid in companies_ids)
    assert not any(fid.startswith("excessive-working-hours") for fid in companies_ids)


def test_flat_clause_splitting() -> None:
    from app.services.clause_splitter import split_into_sections
    text = """
    NOW therefore it is hereby agreed as follows:
    1. In consideration of the payments to be made to the Service Provider.
    2. The Institute shall pay the Service Provider such sums.
    3. The Quality of performance related to the work is the essence.
    """
    sections = split_into_sections(text)
    assert len(sections) == 3
    assert sections[0].title == ""
    assert len(sections[0].clauses) == 1
    assert sections[0].clauses[0].id == "1"
    assert sections[0].clauses[0].text == "In consideration of the payments to be made to the Service Provider."
    assert sections[1].clauses[0].id == "2"
    assert sections[2].clauses[0].id == "3"

def test_strips_section_headers_from_clauses() -> None:
    from app.services.clause_splitter import split_into_sections
    text = """
    4. NON-COMPETE
    4.1 The Freelancer agrees not to compete.
    4.2 Breach of this clause shall result in a penalty.
    5. TERMINATION
    5.1 The Client may terminate this Agreement.
    """
    sections = split_into_sections(text)
    assert len(sections) == 2
    non_compete_sec = next(s for s in sections if "NON-COMPETE" in s.title)
    c42 = next(c for c in non_compete_sec.clauses if c.id == "4.2")
    assert "TERMINATION" not in c42.text
    assert c42.text == "Breach of this clause shall result in a penalty."


def test_splits_three_level_clause_numbers() -> None:
    from app.services.clause_splitter import split_into_sections
    text = """
    1. DEFINITIONS
    1.1.1 The provider may change the pricing at its sole discretion without prior notice.
    1.1.2 This agreement will automatically renew unless the customer gives written notice.
    """

    clauses = [clause for section in split_into_sections(text) for clause in section.clauses]

    assert [clause.id for clause in clauses] == ["1.1.1", "1.1.2"]


def test_unstructured_contract_is_checked_sentence_by_sentence() -> None:
    from app.services.clause_splitter import split_into_sections
    text = (
        "The Employee shall work 60 hours per week as normal working hours. "
        "The Employee waives all rights under the Personal Data Protection Act 2010. "
        "The agreement will automatically renew unless the customer gives written notice."
    )

    clauses = [clause for section in split_into_sections(text) for clause in section.clauses]
    findings = analyze_text(text)
    ids = {finding.id for finding in findings}

    assert len(clauses) == 3
    assert any(fid.startswith("excessive-working-hours-1") for fid in ids)
    assert any(fid.startswith("pdpa-rights-waiver-2") for fid in ids)
    assert any(fid.startswith("auto-renewal-3") for fid in ids)


def test_detects_company_policy_conflict_per_clause() -> None:
    policy = """
    Personal data must only be disclosed to approved processors with prior written consent.
    Employees shall receive no less than the statutory minimum annual leave and unused leave must be handled according to HR approval.
    """
    text = """
    1. POLICY CONFLICTS
    1.1 The Employer may disclose personal data to any third party for any purpose it deems necessary.
    1.2 Unused leave shall be forfeited at the end of each calendar year.
    """

    findings = analyze_text(text, policies_text=policy)
    ids = {finding.id for finding in findings}

    assert any(fid.startswith("company-policy-conflict-1.1") for fid in ids)
    assert any(fid.startswith("company-policy-conflict-1.2") for fid in ids)

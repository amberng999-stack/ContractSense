from app.services.automation import is_likely_contract

def test_is_likely_contract_valid():
    valid_text = """
    NON-DISCLOSURE AGREEMENT
    This Agreement is made on 5 June 2026 by and between Party A and Party B.
    The parties agree as follows:
    1. Confidential Information shall be protected.
    IN WITNESS WHEREOF, the parties hereto have executed this Agreement as of the date first written above.
    """
    assert is_likely_contract(valid_text) is True

def test_is_likely_contract_invalid_short():
    short_text = "NDA between A and B."
    assert is_likely_contract(short_text) is False

def test_is_likely_contract_invalid_general():
    unrelated_text = """
    Meeting notes from Tuesday project review.
    We discussed the timeline, milestones, and deliverables.
    Please ensure the slides are prepared by tomorrow afternoon.
    """
    assert is_likely_contract(unrelated_text) is False

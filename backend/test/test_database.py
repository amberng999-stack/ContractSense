import pytest
from app.db import init_db, save_contract, get_all_contracts, get_contract_by_id, delete_contract, clear_all_contracts

def test_db_crud():
    # Setup
    init_db()
    clear_all_contracts()
    
    # Pre-condition check
    assert len(get_all_contracts()) == 0
    
    # Create record data
    record = {
        "file_name": "test_contract_nda.pdf",
        "company": "Test Company Sdn. Bhd.",
        "risk_score": 35,
        "risk_level": "medium",
        "summary": "Found 1 medium risk clause.",
        "findings": [
            {
                "id": "c1",
                "category": "Liability",
                "title": "Uncapped liability",
                "severity": "medium",
                "confidence": 0.85,
                "excerpt": "Vendor shall be liable for all damages.",
                "explanation": "No cap on liability.",
                "recommendation": "Add a cap."
            }
        ],
        "llm_review": {
            "provider": "local",
            "model": "local-fallback",
            "review": "Executive review text."
        },
        "contract_text": "This Agreement between Test Company Sdn. Bhd. and other party...",
        "pdf_base64": "YmFzZTY0",
        "page_sizes": [{"width": 595.0, "height": 842.0}],
        "highlight_boxes": [
            {
                "finding_id": "c1",
                "page": 0,
                "x0": 100.0,
                "x1": 200.0,
                "top": 500.0,
                "bottom": 520.0,
                "severity": "medium"
            }
        ]
    }
    
    # Save contract
    db_id = save_contract(record)
    assert db_id is not None
    assert db_id > 0
    
    # Query contract details
    db_record = get_contract_by_id(db_id)
    assert db_record is not None
    assert db_record["file_name"] == "test_contract_nda.pdf"
    assert db_record["company"] == "Test Company Sdn. Bhd."
    assert db_record["status"] == "issues" # Medium maps to 'issues'
    assert len(db_record["findings"]) == 1
    assert db_record["findings"][0]["title"] == "Uncapped liability"
    assert db_record["llm_review"]["provider"] == "local"
    assert db_record["pdf_base64"] == "YmFzZTY0"
    assert len(db_record["page_sizes"]) == 1
    assert len(db_record["highlight_boxes"]) == 1
    assert db_record["highlight_boxes"][0]["finding_id"] == "c1"
    assert db_record["is_automated"] is False
    
    # Query list
    contracts_list = get_all_contracts()
    assert len(contracts_list) == 1
    assert contracts_list[0]["id"] == db_id
    assert contracts_list[0]["filename"] == "test_contract_nda.pdf"
    assert contracts_list[0]["company"] == "Test Company Sdn. Bhd."
    assert contracts_list[0]["status"] == "issues"
    
    # Clean up
    delete_contract(db_id)
    assert get_contract_by_id(db_id) is None
    assert len(get_all_contracts()) == 0

def test_search_and_update_text():
    # Setup
    init_db()
    clear_all_contracts()
    
    from app.db import update_contract_text
    
    # Save contract 1
    c1_id = save_contract({
        "file_name": "alpha_contract.pdf",
        "company": "Alpha Corp",
        "risk_level": "low",
        "contract_text": "This is the Alpha Corp freelancer agreement text."
    })
    
    # Save contract 2
    c2_id = save_contract({
        "file_name": "beta_contract.pdf",
        "company": "Beta Inc",
        "risk_level": "medium",
        "contract_text": "This is the Beta Inc document showing RM 150 fees."
    })
    
    # Test search by name match
    results_name = get_all_contracts("alpha")
    assert len(results_name) == 1
    assert results_name[0]["id"] == c1_id
    
    # Test search by content match
    results_content = get_all_contracts("RM 150")
    assert len(results_content) == 1
    assert results_content[0]["id"] == c2_id
    
    # Test search not matching
    results_none = get_all_contracts("nonexistent")
    assert len(results_none) == 0
    
    # Test update_contract_text
    update_contract_text(c1_id, "This is the updated text for Alpha Corp.")
    updated_rec = get_contract_by_id(c1_id)
    assert updated_rec["contract_text"] == "This is the updated text for Alpha Corp."
    
    # Clean up
    delete_contract(c1_id)
    delete_contract(c2_id)

import os
import shutil
from fastapi.testclient import TestClient
from app.main import app, LAWS_DIR, POLICIES_DIR

client = TestClient(app)

def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Enterprise Contract Compliance API"}

def test_reference_endpoints() -> None:
    # Clear directory first
    for filepath in LAWS_DIR.glob("*"):
        filepath.unlink()
    for filepath in POLICIES_DIR.glob("*"):
        filepath.unlink()

    # Verify lists are empty initially
    response = client.get("/api/reference/files")
    assert response.status_code == 200
    assert len(response.json()["laws"]) == 0
    assert len(response.json()["policies"]) == 0

    # Test uploading a law reference file
    law_file_content = b"This is the Employment Act 1955 content text."
    files = {"file": ("employment_act_1955.txt", law_file_content, "text/plain")}
    data = {"type": "law"}
    
    response = client.post("/api/reference/upload", files=files, data=data)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "filename": "employment_act_1955.txt", "type": "law"}

    # Test uploading a policy reference file
    policy_file_content = b"This is the Company HR Handbook content text."
    files = {"file": ("hr_handbook.txt", policy_file_content, "text/plain")}
    data = {"type": "policy"}
    
    response = client.post("/api/reference/upload", files=files, data=data)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "filename": "hr_handbook.txt", "type": "policy"}

    # Verify lists contain uploaded files
    response = client.get("/api/reference/files")
    assert response.status_code == 200
    assert len(response.json()["laws"]) == 1
    assert response.json()["laws"][0]["name"] == "employment_act_1955.txt"
    assert len(response.json()["policies"]) == 1
    assert response.json()["policies"][0]["name"] == "hr_handbook.txt"

    # Test deleting the files
    response = client.delete("/api/reference/files/law/employment_act_1955.txt")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "filename": "employment_act_1955.txt", "type": "law"}

    response = client.delete("/api/reference/files/policy/hr_handbook.txt")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "filename": "hr_handbook.txt", "type": "policy"}

    # Verify they are deleted
    response = client.get("/api/reference/files")
    assert response.status_code == 200
    assert len(response.json()["laws"]) == 0
    assert len(response.json()["policies"]) == 0

def test_chat_endpoint_no_key() -> None:
    # Testing useful local agent fallback when OPENAI_API_KEY is not configured
    payload = {
        "message": "hi",
        "contract_text": "Clause 1. Permanent employment starting 2026.",
        "findings": [],
        "chat_history": []
    }
    
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "ContractSense AI" in reply
    assert "compliance" in reply.lower()

def test_search_and_edit_endpoints() -> None:
    from app.db import init_db, clear_all_contracts, save_contract, get_contract_by_id
    init_db()
    clear_all_contracts()
    
    c_id = save_contract({
        "file_name": "gamma_agreement.pdf",
        "company": "Gamma Ltd",
        "risk_level": "low",
        "contract_text": "This is Gamma contract details."
    })
    
    # Test api search matching
    response = client.get("/api/history?search=gamma")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["filename"] == "gamma_agreement.pdf"
    
    # Test api search not matching
    response = client.get("/api/history?search=nonexistent")
    assert response.status_code == 200
    assert len(response.json()) == 0
    
    # Test api update text
    payload = {"contract_text": "This is the updated Gamma contract text."}
    response = client.post(f"/api/history/{c_id}/text", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # Verify update in db
    rec = get_contract_by_id(c_id)
    assert rec["contract_text"] == "This is the updated Gamma contract text."
    
    # Cleanup
    from app.db import delete_contract
    delete_contract(c_id)

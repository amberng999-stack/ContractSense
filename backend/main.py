import asyncio
import base64
import os
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.config import get_settings
from app.models import ContractAnalysisResponse, ClauseFinding, PageSize, HighlightBoxOut
from app.services.llm_review import review_with_llm
from app.services.llm_chat import chat_with_llm
from app.services.risk_rules import analyze_text, calculate_risk_score, risk_level_from_score
from app.services.text_extraction import read_and_validate_upload, extract_text_from_bytes
from app.services.pdf_highlight import extract_pdf_with_coords, match_excerpt_to_boxes

from app.db import init_db, save_contract, get_all_contracts, get_contract_by_id, delete_contract, clear_all_contracts, get_email_config, save_email_config, disconnect_email
from app.services.automation import start_automation_watcher, process_incoming_contracts, AUTO_IMPORT_DIR, AUTO_IMPORT_PROCESSED_DIR
from app.services.malaysia_law_updater import (
    read_malaysia_law_update_status,
    start_malaysia_law_updater,
    update_malaysia_law_database,
)
from app.services.sharepoint_policy_sync import (
    link_company_policy_source,
    read_company_policy_source_status,
    start_company_policy_sync,
    sync_company_policy_source,
)

settings = get_settings()
app = FastAPI(title=settings.app_name)

@app.on_event("startup")
def startup_event():
    init_db()
    AUTO_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    AUTO_IMPORT_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    start_automation_watcher()
    start_malaysia_law_updater(
        LAWS_DIR,
        source_url=settings.malaysia_law_source_url,
        interval_hours=settings.malaysia_law_update_interval_hours,
        enabled=settings.malaysia_law_auto_update_enabled,
    )
    start_company_policy_sync(
        POLICIES_DIR,
        interval_minutes=settings.company_policy_sync_interval_minutes,
        enabled=settings.company_policy_sync_enabled,
    )

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=["*"],
)

# Reference Directories
DATA_DIR = Path("data")
REFERENCE_DIR = DATA_DIR / "reference"
LAWS_DIR = REFERENCE_DIR / "laws"
POLICIES_DIR = REFERENCE_DIR / "policies"
for folder in (LAWS_DIR, POLICIES_DIR):
    folder.mkdir(parents=True, exist_ok=True)
def _load_reference_text(folder: Path) -> str:
    texts = []
    for filepath in folder.glob("*"):
        if filepath.is_file() and filepath.suffix.lower() in {".txt", ".md", ".pdf", ".docx"}:
            try:
                content = filepath.read_bytes()
                from app.services.text_extraction import _decode_text, _extract_pdf, _extract_docx
                ext = filepath.suffix.lower()
                if ext in {".txt", ".md"}:
                    text = _decode_text(content)
                elif ext == ".pdf":
                    text = _extract_pdf(content)
                elif ext == ".docx":
                    text = _extract_docx(content)
                else:
                    text = ""
                if text.strip():
                    texts.append(f"--- File: {filepath.name} ---\n{text.strip()}")
            except Exception as e:
                print(f"Error reading reference file {filepath}: {e}")
    return "\n\n".join(texts)
class ChatMessage(BaseModel):
    role: str
    content: str
class ChatRequest(BaseModel):
    message: str
    contract_text: str
    findings: list[ClauseFinding] = []
    chat_history: list[ChatMessage] = []

class CompanyPolicyLinkRequest(BaseModel):
    source_url: str
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}

@app.post("/api/contracts/analyze", response_model=ContractAnalysisResponse)
async def analyze_contract(
    file: UploadFile = File(...),
    jurisdiction: str | None = Form(default=None),
    language: str | None = Form(default=None),
) -> ContractAnalysisResponse:
    content, extension = await read_and_validate_upload(file, settings.max_upload_mb)
    contract_text = extract_text_from_bytes(content, extension)

    if not contract_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract readable text from the uploaded contract.",
        )

    # Load uploaded reference databases
    laws_text = _load_reference_text(LAWS_DIR)
    policies_text = _load_reference_text(POLICIES_DIR)
    findings = analyze_text(contract_text)
    risk_score = calculate_risk_score(findings)
    risk_level = risk_level_from_score(risk_score)
    llm_review = await review_with_llm(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        contract_text=contract_text,
        findings=findings,
        jurisdiction=jurisdiction,
        language=language,
        laws_text=laws_text,
        policies_text=policies_text,
    )

    summary = (
        f"Found {len(findings)} potential hidden/risky clauses."
        if findings
        else "No hidden/risky clauses were detected by the current rule set."
    )

    # PDF-native rendering data: only built for PDF uploads. Renders the
    # REAL PDF in the browser (via PDF.js) with highlight boxes drawn at
    # exact coordinates, instead of reconstructing the document as HTML.
    pdf_base64 = None
    page_sizes_out = None
    highlight_boxes_out = None

    if extension == ".pdf":
        try:
            extraction = extract_pdf_with_coords(content)
            pdf_base64 = base64.b64encode(content).decode("ascii")
            page_sizes_out = [PageSize(width=w, height=h) for (w, h) in extraction.page_sizes]

            boxes: list[HighlightBoxOut] = []
            # Only flagged (non-"low") findings need highlighting — clean
            # clauses don't need a box drawn on the real PDF.
            for finding in findings:
                if finding.severity == "low":
                    continue
                query_excerpt = finding.matched_snippet or finding.excerpt
                matched = match_excerpt_to_boxes(extraction, query_excerpt, finding.severity)
                for box in matched:
                    boxes.append(HighlightBoxOut(
                        finding_id=finding.id,
                        page=box.page,
                        x0=box.x0,
                        x1=box.x1,
                        top=box.top,
                        bottom=box.bottom,
                        severity=box.severity,
                    ))
            highlight_boxes_out = boxes

        except Exception as e:
            # If coordinate extraction fails for any reason (malformed PDF,
            # scanned/image-only PDF with no extractable words, etc.), fall
            # back gracefully — the scan still completes with text-based
            # results, just without PDF-native highlighting.
            print(f"PDF coordinate extraction failed: {e}")

    # Save the scanned contract to the database
    db_findings = [f.model_dump() for f in findings]
    db_llm_review = llm_review.model_dump() if llm_review else None
    db_page_sizes = [{"width": s.width, "height": s.height} for s in page_sizes_out] if page_sizes_out else None
    db_highlight_boxes = [
        {
            "finding_id": b.finding_id,
            "page": b.page,
            "x0": b.x0,
            "x1": b.x1,
            "top": b.top,
            "bottom": b.bottom,
            "severity": b.severity
        } for b in highlight_boxes_out
    ] if highlight_boxes_out else None

    contract_record = {
        "file_name": file.filename or "uploaded-contract",
        "summary": summary,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "findings": db_findings,
        "llm_review": db_llm_review,
        "contract_text": contract_text,
        "pdf_base64": pdf_base64,
        "page_sizes": db_page_sizes,
        "highlight_boxes": db_highlight_boxes,
        "is_automated": False
    }
    
    db_id = save_contract(contract_record)
    db_contract = get_contract_by_id(db_id)

    return ContractAnalysisResponse(
        id=db_id,
        file_name=file.filename or "uploaded-contract",
        summary=summary,
        risk_score=risk_score,
        risk_level=risk_level,
        findings=findings,
        llm_review=llm_review,
        contract_text=contract_text,
        pdf_base64=pdf_base64,
        page_sizes=page_sizes_out,
        highlight_boxes=highlight_boxes_out,
        company=db_contract.get("company") if db_contract else "—",
        date=db_contract.get("date") if db_contract else None,
        time=db_contract.get("time") if db_contract else None,
        is_automated=False
    )

@app.get("/api/reference/files")
def list_reference_files():
    def get_files_in_dir(directory: Path):
        files_list = []
        for p in directory.glob("*"):
            if p.is_file():
                stat = p.stat()
                files_list.append({
                    "name": p.name,
                    "size_bytes": stat.st_size,
                    "created_at": stat.st_mtime
                })
        return files_list
    return {
        "laws": get_files_in_dir(LAWS_DIR),
        "policies": get_files_in_dir(POLICIES_DIR)
    }

@app.get("/api/reference/laws/update-status")
def get_malaysia_law_update_status():
    return read_malaysia_law_update_status(LAWS_DIR)

@app.post("/api/reference/laws/update")
async def refresh_malaysia_law_reference():
    try:
        return await asyncio.to_thread(
            update_malaysia_law_database,
            LAWS_DIR,
            source_url=settings.malaysia_law_source_url,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Malaysia law database update failed: {str(e)}"
        )

@app.get("/api/reference/policy/source")
def get_company_policy_source():
    return read_company_policy_source_status(POLICIES_DIR)

@app.post("/api/reference/policy/source")
async def save_company_policy_source(request: CompanyPolicyLinkRequest):
    try:
        return await asyncio.to_thread(
            link_company_policy_source,
            POLICIES_DIR,
            source_url=request.source_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Company policy source link failed: {str(e)}"
        )

@app.post("/api/reference/policy/sync")
async def sync_company_policy_now():
    return await asyncio.to_thread(sync_company_policy_source, POLICIES_DIR)

@app.post("/api/reference/upload")
async def upload_reference_file(
    file: UploadFile = File(...),
    type: Literal["law", "policy"] = Form(...)
):
    target_dir = LAWS_DIR if type == "law" else POLICIES_DIR
    target_path = target_dir / (file.filename or "uploaded-file")
    
    # Save file
    try:
        content = await file.read()
        with open(target_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save file: {str(e)}"
        )
        
    return {"status": "ok", "filename": file.filename, "type": type}

@app.delete("/api/reference/files/{type}/{filename}")
def delete_reference_file(
    type: Literal["law", "policy"],
    filename: str
):
    target_dir = LAWS_DIR if type == "law" else POLICIES_DIR
    target_path = target_dir / filename
    
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {filename} not found in {type} reference database."
        )
        
    try:
        target_path.unlink()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete file: {str(e)}"
        )
        
    return {"status": "ok", "filename": filename, "type": type}

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    laws_text = _load_reference_text(LAWS_DIR)
    policies_text = _load_reference_text(POLICIES_DIR)
    
    history_list = [{"role": msg.role, "content": msg.content} for msg in request.chat_history]
    
    reply = await chat_with_llm(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        message=request.message,
        contract_text=request.contract_text,
        findings=request.findings,
        laws_text=laws_text,
        policies_text=policies_text,
        chat_history=history_list,
    )
    
    return {"reply": reply}


@app.get("/api/history")
def get_history(search: str | None = None):
    try:
        return get_all_contracts(search)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}"
        )

class UpdateTextRequest(BaseModel):
    contract_text: str

@app.post("/api/history/{id}/text")
def update_contract_text_endpoint(id: int, request: UpdateTextRequest):
    try:
        from app.db import update_contract_text, get_contract_by_id
        update_contract_text(id, request.contract_text)
        
        # Save a copy of the edited contract text to the server filesystem
        contract = get_contract_by_id(id)
        if contract:
            filename = contract.get("file_name", f"contract_{id}")
            # Ensure name matches extension/type
            edited_dir = Path("data/edited")
            edited_dir.mkdir(parents=True, exist_ok=True)
            
            # Save clean text copy on server filesystem
            txt_filename = Path(filename).with_suffix(".txt").name
            text_path = edited_dir / f"{id}_{txt_filename}"
            text_path.write_text(request.contract_text, encoding="utf-8")
            
            # If the original contract was from auto-import folder, keep it synced in processed folder
            processed_path = Path("data/auto_import/processed") / filename
            if processed_path.exists():
                processed_path.write_text(request.contract_text, encoding="utf-8")

        return {"status": "ok", "message": "Contract text updated successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update contract text: {str(e)}"
        )

@app.get("/api/history/{id}", response_model=ContractAnalysisResponse)
def get_history_detail(id: int):
    try:
        contract = get_contract_by_id(id)
        if not contract:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contract scan with ID {id} not found."
            )
        return contract
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}"
        )

@app.delete("/api/history/{id}")
def delete_history_item(id: int):
    try:
        delete_contract(id)
        return {"status": "ok", "message": f"Deleted contract {id}"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {str(e)}"
        )

@app.delete("/api/history")
def clear_history():
    try:
        clear_all_contracts()
        return {"status": "ok", "message": "All history cleared"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clear failed: {str(e)}"
        )

@app.post("/api/automation/scan")
async def trigger_automation():
    try:
        new_records = await process_incoming_contracts()
        return {"status": "ok", "imported_count": len(new_records), "records": new_records}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Folder scan failed: {str(e)}"
        )

class EmailConfigParams(BaseModel):
    imap_server: str
    imap_port: int
    email_address: str
    email_password: str

@app.get("/api/automation/email-config")
def get_email_connection_status():
    config = get_email_config()
    if config:
        return {
            "is_connected": True,
            "email_address": config["email_address"],
            "imap_server": config["imap_server"],
            "imap_port": config["imap_port"]
        }
    return {"is_connected": False}

@app.post("/api/automation/email-config")
def connect_email_inbox(params: EmailConfigParams):
    import imaplib
    try:
        # Test IMAP connection synchronously
        mail = imaplib.IMAP4_SSL(params.imap_server, params.imap_port)
        mail.login(params.email_address, params.email_password)
        mail.logout()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email connection check failed. Please check host, port, credentials, or App Password setup. Details: {str(e)}"
        )
        
    try:
        save_email_config(
            params.imap_server,
            params.imap_port,
            params.email_address,
            params.email_password
        )
        return {"status": "ok", "message": "Email inbox connected and active."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store email connection configuration: {str(e)}"
        )

@app.delete("/api/automation/email-config")
def disconnect_email_inbox():
    try:
        disconnect_email()
        return {"status": "ok", "message": "Email inbox disconnected successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect: {str(e)}"
        )

@app.get("/api/test-imap")
def test_imap_endpoint():
    logs = []
    logs.append("Starting IMAP test...")
    
    config = get_email_config()
    if not config:
        return {"status": "error", "message": "No config in database", "logs": logs}
        
    logs.append(f"Config found: {config['email_address']} on {config['imap_server']}:{config['imap_port']}")
    
    import imaplib
    import socket
    
    # Set socket timeout
    socket.setdefaulttimeout(10)
    logs.append("Socket timeout set to 10s")
    
    try:
        logs.append("Connecting to IMAP server...")
        mail = imaplib.IMAP4_SSL(config["imap_server"], config["imap_port"])
        logs.append("Connected! Logging in...")
        
        mail.login(config["email_address"], config["email_password"])
        logs.append("Logged in successfully! Selecting inbox...")
        
        status, messages = mail.select("inbox")
        logs.append(f"Inbox select status: {status}, message count: {messages[0].decode('utf-8') if isinstance(messages[0], bytes) else messages[0]}")
        
        status, search_res = mail.search(None, "UNSEEN")
        logs.append(f"Search UNSEEN status: {status}")
        
        if status == "OK" and search_res[0]:
            email_ids = search_res[0].split()
            logs.append(f"Found {len(email_ids)} unread emails.")
            for email_id in email_ids:
                logs.append(f"Message ID: {email_id.decode('utf-8') if isinstance(email_id, bytes) else email_id}")
        else:
            logs.append("No unread emails found.")
            
        mail.logout()
        logs.append("Logged out.")
        return {"status": "success", "logs": logs}
        
    except Exception as e:
        logs.append(f"Error during IMAP operations: {str(e)}")
        return {"status": "error", "logs": logs}




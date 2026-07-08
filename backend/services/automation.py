import asyncio
import os
import shutil
import base64
import imaplib
import email
from email.header import decode_header
from datetime import datetime
from pathlib import Path
from app.config import get_settings
from app.services.text_extraction import extract_text_from_bytes
from app.services.pdf_highlight import extract_pdf_with_coords, match_excerpt_to_boxes
from app.services.risk_rules import analyze_text, calculate_risk_score, risk_level_from_score
from app.services.llm_review import review_with_llm
from app.db import save_contract, get_contract_by_id, get_email_config

DATA_DIR = Path("data")
AUTO_IMPORT_DIR = DATA_DIR / "auto_import"
AUTO_IMPORT_PROCESSED_DIR = AUTO_IMPORT_DIR / "processed"

# Semaphore to prevent multiple scans running at the same time
_scan_lock = asyncio.Lock()

def is_likely_contract(text: str) -> bool:
    """
    Implements a robust multi-criteria heuristic check to verify if a text is
    actually a legal contract or agreement, avoiding false positives on unrelated files.
    """
    if not text or len(text.strip()) < 100:
        return False
        
    text_lower = text.lower()
    
    # 1. Standard title indicators
    titles = [
        "agreement", "contract", "nda", "non-disclosure", "covenant", 
        "terms of service", "terms and conditions", "memorandum of understanding",
        "service level agreement", "sla", "employment contract"
    ]
    has_title = any(t in text_lower for t in titles)
    
    # 2. Opening/parties clause indicators
    openings = [
        "this agreement", "is made on", "by and between", "entered into",
        "agree as follows", "parties agree", "hereinafter referred to",
        "hereby agree", "mutual confidentiality", "disclosing party", "receiving party"
    ]
    has_opening = any(op in text_lower for op in openings)
    
    # 3. Execution/Signatures block indicators
    signatures = [
        "in witness whereof", "signed by", "authorized signatory", "execute",
        "executed as a deed", "execution", "hand and seal", "written above"
    ]
    has_signature = any(sig in text_lower for sig in signatures)
    
    # Needs to satisfy at least 2 out of the 3 major indicators to be classified as a contract
    score = 0
    if has_title: score += 1
    if has_opening: score += 1
    if has_signature: score += 1
    
    return score >= 2

async def process_incoming_contracts() -> list[dict]:
    """
    Checks AUTO_IMPORT_DIR for PDF/DOCX files, runs compliance checks,
    saves results to the database, and moves processed files.
    Returns a list of newly imported contract database records.
    """
    if _scan_lock.locked():
        return []
        
    async with _scan_lock:
        new_contracts = []
        if not AUTO_IMPORT_DIR.exists():
            return []
            
        for filepath in AUTO_IMPORT_DIR.glob("*"):
            if not filepath.is_file():
                continue
            ext = filepath.suffix.lower()
            if ext not in {".pdf", ".docx", ".txt", ".md"}:
                continue
                
            try:
                # Check if file size is stable (ensuring it's fully written)
                prev_size = filepath.stat().st_size
                await asyncio.sleep(0.5)
                if filepath.stat().st_size != prev_size:
                    continue
                    
                content = filepath.read_bytes()
            except Exception as e:
                print(f"Skipping {filepath.name}, cannot read file: {e}")
                continue
                
            print(f"Auto-import scanner: processing {filepath.name}...")
            try:
                contract_text = extract_text_from_bytes(content, ext)
                if not contract_text.strip() or not is_likely_contract(contract_text):
                    print(f"Auto-import scanner: empty text or not classified as a contract in {filepath.name}. Skipping.")
                    # Move to processed folder as skipped
                    dest_path = AUTO_IMPORT_PROCESSED_DIR / f"ignored_non_contract_{filepath.name}"
                    shutil.move(str(filepath), str(dest_path))
                    continue
                    
                # Run rule analyzer
                findings = analyze_text(contract_text)
                risk_score = calculate_risk_score(findings)
                risk_level = risk_level_from_score(risk_score)
                
                # Load reference text (laws & policies)
                from app.main import _load_reference_text, LAWS_DIR, POLICIES_DIR
                laws_text = _load_reference_text(LAWS_DIR)
                policies_text = _load_reference_text(POLICIES_DIR)
                
                # Run LLM review (async)
                settings = get_settings()
                llm_review = await review_with_llm(
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                    gemini_api_key=settings.gemini_api_key,
                    gemini_model=settings.gemini_model,
                    contract_text=contract_text,
                    findings=findings,
                    jurisdiction="Malaysia",
                    language="English",
                    laws_text=laws_text,
                    policies_text=policies_text,
                )
                
                pdf_base64 = None
                page_sizes_out = None
                highlight_boxes_out = None
                if ext == ".pdf":
                    try:
                        extraction = extract_pdf_with_coords(content)
                        pdf_base64 = base64.b64encode(content).decode("ascii")
                        page_sizes_out = [{"width": w, "height": h} for (w, h) in extraction.page_sizes]
                        
                        boxes = []
                        for finding in findings:
                            if finding.severity == "low":
                                continue
                            query_excerpt = finding.matched_snippet or finding.excerpt
                            matched = match_excerpt_to_boxes(extraction, query_excerpt, finding.severity)
                            for box in matched:
                                boxes.append({
                                    "finding_id": finding.id,
                                    "page": box.page,
                                    "x0": box.x0,
                                    "x1": box.x1,
                                    "top": box.top,
                                    "bottom": box.bottom,
                                    "severity": box.severity,
                                })
                        highlight_boxes_out = boxes
                    except Exception as coord_err:
                        print(f"PDF coord extraction failed during auto-import: {coord_err}")
                
                # Save to database
                db_findings = [f.model_dump() for f in findings]
                db_llm_review = llm_review.model_dump() if llm_review else None
                
                contract_record = {
                    "file_name": filepath.name,
                    "summary": f"Found {len(findings)} potential compliance issues." if findings else "No compliance issues detected.",
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "findings": db_findings,
                    "llm_review": db_llm_review,
                    "contract_text": contract_text,
                    "pdf_base64": pdf_base64,
                    "page_sizes": page_sizes_out,
                    "highlight_boxes": highlight_boxes_out,
                    "is_automated": True
                }
                
                db_id = save_contract(contract_record)
                
                # Retrieve final record
                db_record = get_contract_by_id(db_id)
                if db_record:
                    new_contracts.append(db_record)
                    
                # Move file to processed folder
                dest_path = AUTO_IMPORT_PROCESSED_DIR / filepath.name
                if dest_path.exists():
                    stem = filepath.stem
                    suffix = filepath.suffix
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest_path = AUTO_IMPORT_PROCESSED_DIR / f"{stem}_{timestamp}{suffix}"
                shutil.move(str(filepath), str(dest_path))
                print(f"Auto-import scanner: successfully imported {filepath.name} (DB ID: {db_id})")
                
            except Exception as scan_err:
                print(f"Error processing {filepath.name} in auto-import: {scan_err}")
                try:
                    dest_path = AUTO_IMPORT_PROCESSED_DIR / f"failed_error_{filepath.name}"
                    shutil.move(str(filepath), str(dest_path))
                except Exception as move_err:
                    print(f"Could not move failed file {filepath.name}: {move_err}")
                    
        return new_contracts

_email_lock = asyncio.Lock()

def _decode_email_header(header_value: str) -> str:
    if not header_value:
        return ""
    decoded = decode_header(header_value)
    parts = []
    for text, encoding in decoded:
        if isinstance(text, bytes):
            try:
                parts.append(text.decode(encoding or "utf-8", errors="ignore"))
            except Exception:
                parts.append(text.decode("latin1", errors="ignore"))
        else:
            parts.append(str(text))
    return "".join(parts).strip()

def fetch_unread_emails_sync() -> list[dict]:
    config = get_email_config()
    if not config or not config.get("is_connected"):
        return []
        
    server = config["imap_server"]
    port = config["imap_port"]
    username = config["email_address"]
    password = config["email_password"]
    
    unread_contracts = []
    
    try:
        mail = imaplib.IMAP4_SSL(server, port)
        mail.login(username, password)
        mail.select("inbox")
        
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            mail.logout()
            return []
            
        email_ids = messages[0].split()
        
        # Take only the 15 most recent unread emails to avoid getting stuck on thousands of historical unread emails
        email_ids = list(reversed(email_ids))[:15]
        
        for email_id in email_ids:
            try:
                # 1. Fetch Subject and From headers first to preserve privacy and bandwidth
                status, header_data = mail.fetch(email_id, "(BODY[HEADER.FIELDS (SUBJECT FROM)])")
                if status != "OK" or not header_data or not header_data[0]:
                    continue
                    
                raw_headers = header_data[0][1]
                header_msg = email.message_from_bytes(raw_headers)
                
                subject = _decode_email_header(header_msg.get("Subject", ""))
                sender = _decode_email_header(header_msg.get("From", ""))
                
                # Check subject keywords (case-insensitive)
                subject_lower = subject.lower()
                contract_keywords = {
                    "contract", "agreement", "nda", "compliance", "terms", "policy", 
                    "signature", "signatory", "covenant", "liability", "proposal", 
                    "addendum", "amendment"
                }
                
                is_contract_subject = any(kw in subject_lower for kw in contract_keywords)
                if not is_contract_subject:
                    # Skip unrelated personal emails entirely, leaving them UNREAD (\Seen flag not touched)
                    continue
                    
                # 2. Only fetch the full email payload if the subject matches contract heuristics
                status, full_data = mail.fetch(email_id, "(RFC822)")
                if status != "OK" or not full_data or not full_data[0]:
                    continue
                    
                raw_email = full_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Look for attachments
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                        
                    filename = _decode_email_header(part.get_filename() or "")
                    if not filename:
                        continue
                        
                    ext = Path(filename).suffix.lower()
                    if ext not in {".pdf", ".docx", ".doc", ".txt", ".md"}:
                        continue
                        
                    file_bytes = part.get_payload(decode=True)
                    if not file_bytes:
                        continue
                        
                    unread_contracts.append({
                        "sender": sender,
                        "subject": subject,
                        "filename": filename,
                        "file_bytes": file_bytes,
                        "ext": ext
                    })
                    
                # Mark as seen so we don't process this email again next time
                # Note: We only mark it as seen if it matches our subject filter, ensuring personal emails are untouched.
                mail.store(email_id, '+FLAGS', '\\Seen')
                
            except Exception as item_err:
                print(f"IMAP fetch error for msg ID {email_id}: {item_err}")
                
        mail.logout()
    except Exception as server_err:
        print(f"IMAP server sync check failed: {server_err}")
        
    return unread_contracts

async def process_email_contract_async(email_item: dict) -> None:
    filename = email_item["filename"]
    file_bytes = email_item["file_bytes"]
    ext = email_item["ext"]
    sender = email_item["sender"]
    subject = email_item["subject"]
    
    try:
        # Extract text and run a quick contract validator check
        contract_text = extract_text_from_bytes(file_bytes, ext)
        if not contract_text.strip() or not is_likely_contract(contract_text):
            print(f"IMAP scanner: attachment '{filename}' empty or does not meet strict contract criteria. Ignoring.")
            return
            
        print(f"IMAP scanner: automatic screening contract '{filename}' from '{sender}'...")
        
        # Rule analyzer
        findings = analyze_text(contract_text)
        risk_score = calculate_risk_score(findings)
        risk_level = risk_level_from_score(risk_score)
        
        # Load reference databases (laws & policies)
        from app.main import _load_reference_text, LAWS_DIR, POLICIES_DIR
        laws_text = _load_reference_text(LAWS_DIR)
        policies_text = _load_reference_text(POLICIES_DIR)
        
        # Run LLM review (async)
        settings = get_settings()
        llm_review = await review_with_llm(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            contract_text=contract_text,
            findings=findings,
            jurisdiction="Malaysia",
            language="English",
            laws_text=laws_text,
            policies_text=policies_text,
        )
        
        pdf_base64 = None
        page_sizes_out = None
        highlight_boxes_out = None
        if ext == ".pdf":
            try:
                extraction = extract_pdf_with_coords(file_bytes)
                pdf_base64 = base64.b64encode(file_bytes).decode("ascii")
                page_sizes_out = [{"width": w, "height": h} for (w, h) in extraction.page_sizes]
                
                boxes = []
                for finding in findings:
                    if finding.severity == "low":
                        continue
                    query_excerpt = finding.matched_snippet or finding.excerpt
                    matched = match_excerpt_to_boxes(extraction, query_excerpt, finding.severity)
                    for box in matched:
                        boxes.append({
                            "finding_id": finding.id,
                            "page": box.page,
                            "x0": box.x0,
                            "x1": box.x1,
                            "top": box.top,
                            "bottom": box.bottom,
                            "severity": box.severity,
                        })
                highlight_boxes_out = boxes
            except Exception as coord_err:
                print(f"PDF coord extraction failed during IMAP scan: {coord_err}")
                
        # Save to database
        db_findings = [f.model_dump() for f in findings]
        db_llm_review = llm_review.model_dump() if llm_review else None
        
        summary = f"Received via email from {sender}. Subject: \"{subject}\". Found {len(findings)} potential compliance issues."
        
        contract_record = {
            "file_name": filename,
            "summary": summary,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "findings": db_findings,
            "llm_review": db_llm_review,
            "contract_text": contract_text,
            "pdf_base64": pdf_base64,
            "page_sizes": page_sizes_out,
            "highlight_boxes": highlight_boxes_out,
            "is_automated": True
        }
        
        db_id = save_contract(contract_record)
        print(f"IMAP scanner: successfully scanned contract '{filename}' (DB ID: {db_id})")
        
    except Exception as parse_err:
        print(f"IMAP scanner: error processing '{filename}': {parse_err}")

async def check_connected_email_inbox() -> None:
    if _email_lock.locked():
        return
        
    async with _email_lock:
        # Connect to email server synchronously in a thread pool to avoid blocking
        email_items = await asyncio.to_thread(fetch_unread_emails_sync)
        if not email_items:
            return
            
        for item in email_items:
            await process_email_contract_async(item)

async def _watcher_loop():
    print("Auto-import watcher loop started.")
    # Wait a few seconds on startup before first check
    await asyncio.sleep(5)
    while True:
        try:
            # 1. Check local auto_import folder
            await process_incoming_contracts()
        except Exception as err:
            print(f"Error in folder auto-import watcher: {err}")
            
        try:
            # 2. Check connected email inbox
            await check_connected_email_inbox()
        except Exception as err:
            print(f"Error in IMAP email ingestion: {err}")
            
        await asyncio.sleep(10)

def start_automation_watcher():
    loop = asyncio.get_event_loop()
    loop.create_task(_watcher_loop())


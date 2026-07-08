import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime
from app.config import get_settings

DB_PATH = Path("data") / "contractsense.db"

def is_postgres() -> bool:
    settings = get_settings()
    url = settings.database_url or ""
    return url.startswith("postgres://") or url.startswith("postgresql://")

def get_db_connection():
    settings = get_settings()
    url = settings.database_url or ""
    if is_postgres():
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        # Strip pgbouncer query parameter which psycopg2 connection parser rejects
        if "?" in url:
            base_url, query = url.split("?", 1)
            params = [p for p in query.split("&") if not p.startswith("pgbouncer=")]
            if params:
                url = base_url + "?" + "&".join(params)
            else:
                url = base_url
                
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        return conn

    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

def get_placeholder() -> str:
    return "%s" if is_postgres() else "?"

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if is_postgres():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id SERIAL PRIMARY KEY,
                file_name TEXT NOT NULL,
                company TEXT,
                date TEXT,
                time TEXT,
                status TEXT,
                risk_score INTEGER,
                risk_level TEXT,
                summary TEXT,
                contract_text TEXT,
                findings_json TEXT,
                llm_review_json TEXT,
                pdf_base64 TEXT,
                page_sizes_json TEXT,
                highlight_boxes_json TEXT,
                is_automated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_config (
                id SERIAL PRIMARY KEY,
                imap_server TEXT NOT NULL,
                imap_port INTEGER NOT NULL,
                email_address TEXT NOT NULL,
                email_password TEXT NOT NULL,
                is_connected INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                company TEXT,
                date TEXT,
                time TEXT,
                status TEXT,
                risk_score INTEGER,
                risk_level TEXT,
                summary TEXT,
                contract_text TEXT,
                findings_json TEXT,
                llm_review_json TEXT,
                pdf_base64 TEXT,
                page_sizes_json TEXT,
                highlight_boxes_json TEXT,
                is_automated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imap_server TEXT NOT NULL,
                imap_port INTEGER NOT NULL,
                email_address TEXT NOT NULL,
                email_password TEXT NOT NULL,
                is_connected INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
    conn.commit()
    conn.close()


def extract_company_from_text(text: str) -> str:
    if not text:
        return "—"
    match = re.search(r"([A-Z0-9a-z\s,\.\(\)\-\&]+(?:Sdn\.\s*Bhd\.|Sdn\s*Bhd|Bhd\.|Bhd))", text, re.IGNORECASE)
    if match:
        company_name = match.group(1).strip()
        # Find the last occurrence of common separator words in the company name
        # and strip everything before and including it.
        separators = ["between", "and", "this", "agreement", "by", "employer", "client", "vendor", "contract", "parties", "is", "are"]
        pattern = r"\b(?:" + "|".join(separators) + r")\b"
        matches = list(re.finditer(pattern, company_name, flags=re.IGNORECASE))
        if matches:
            last_match = matches[-1]
            company_name = company_name[last_match.end():].strip()
            
        # Clean leading non-alphanumeric chars (e.g. commas, dashes)
        company_name = re.sub(r"^[^A-Za-z0-9]+", "", company_name)
        if len(company_name) > 60:
            company_name = company_name[:60]
        return company_name
    return "—"

def get_current_date_time_malaysia():
    now = datetime.now()
    date_str = now.strftime("%d %b %Y")  # e.g., "23 Jun 2026"
    time_str = now.strftime("%I:%M %p")  # e.g., "09:42 PM"
    return date_str, time_str

def save_contract(record: dict) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    date_str, time_str = get_current_date_time_malaysia()
    
    risk_level = record.get("risk_level", "low")
    if risk_level in ["critical", "high"]:
        status = "critical"
    elif risk_level == "medium":
        status = "issues"
    else:
        status = "safe"
        
    company = record.get("company", "—")
    if not company or company == "—":
        company = extract_company_from_text(record.get("contract_text", ""))
        
    p = get_placeholder()
    params = (
        record.get("file_name"),
        company,
        date_str,
        time_str,
        status,
        record.get("risk_score", 0),
        risk_level,
        record.get("summary", ""),
        record.get("contract_text", ""),
        json.dumps(record.get("findings", [])),
        json.dumps(record.get("llm_review", {})),
        record.get("pdf_base64"),
        json.dumps(record.get("page_sizes", [])),
        json.dumps(record.get("highlight_boxes", [])),
        1 if record.get("is_automated") else 0
    )
    
    if is_postgres():
        query = f"""
            INSERT INTO contracts (
                file_name, company, date, time, status, risk_score, risk_level, summary,
                contract_text, findings_json, llm_review_json, pdf_base64, page_sizes_json,
                highlight_boxes_json, is_automated
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            RETURNING id
        """
        cursor.execute(query, params)
        inserted_id = cursor.fetchone()["id"]
    else:
        query = f"""
            INSERT INTO contracts (
                file_name, company, date, time, status, risk_score, risk_level, summary,
                contract_text, findings_json, llm_review_json, pdf_base64, page_sizes_json,
                highlight_boxes_json, is_automated
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
        """
        cursor.execute(query, params)
        inserted_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return inserted_id

def get_all_contracts(search_query: str | None = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if search_query:
        p = get_placeholder()
        like_pattern = f"%{search_query}%"
        cursor.execute(f"""
            SELECT id, file_name, company, date, time, status, risk_score, risk_level, summary, is_automated, created_at
            FROM contracts
            WHERE file_name LIKE {p} OR contract_text LIKE {p}
            ORDER BY id DESC
        """, (like_pattern, like_pattern))
    else:
        cursor.execute("""
            SELECT id, file_name, company, date, time, status, risk_score, risk_level, summary, is_automated, created_at
            FROM contracts
            ORDER BY id DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "filename": r["file_name"],
            "company": r["company"] or "—",
            "date": r["date"],
            "time": r["time"],
            "status": r["status"],
            "risk_score": r["risk_score"],
            "risk_level": r["risk_level"],
            "summary": r["summary"],
            "is_automated": bool(r["is_automated"]),
            "created_at": str(r["created_at"])
        })
    return results

def get_contract_by_id(contract_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    p = get_placeholder()
    cursor.execute(f"SELECT * FROM contracts WHERE id = {p}", (contract_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
        
    try:
        findings = json.loads(row["findings_json"]) if row["findings_json"] else []
    except Exception:
        findings = []
        
    try:
        llm_review = json.loads(row["llm_review_json"]) if row["llm_review_json"] else None
    except Exception:
        llm_review = None
        
    try:
        page_sizes = json.loads(row["page_sizes_json"]) if row["page_sizes_json"] else None
    except Exception:
        page_sizes = None
        
    try:
        highlight_boxes = json.loads(row["highlight_boxes_json"]) if row["highlight_boxes_json"] else None
    except Exception:
        highlight_boxes = None
        
    return {
        "id": row["id"],
        "file_name": row["file_name"],
        "company": row["company"] or "—",
        "date": row["date"],
        "time": row["time"],
        "status": row["status"],
        "risk_score": row["risk_score"],
        "risk_level": row["risk_level"],
        "summary": row["summary"],
        "findings": findings,
        "llm_review": llm_review,
        "contract_text": row["contract_text"],
        "pdf_base64": row["pdf_base64"],
        "page_sizes": page_sizes,
        "highlight_boxes": highlight_boxes,
        "is_automated": bool(row["is_automated"]),
        "created_at": str(row["created_at"])
    }

def delete_contract(contract_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    cursor.execute(f"DELETE FROM contracts WHERE id = {p}", (contract_id,))
    conn.commit()
    conn.close()

def update_contract_text(contract_id: int, new_text: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    cursor.execute(f"UPDATE contracts SET contract_text = {p} WHERE id = {p}", (new_text, contract_id))
    conn.commit()
    conn.close()

def clear_all_contracts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM contracts")
    conn.commit()
    conn.close()

def save_email_config(imap_server, imap_port, email_address, email_password) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    p = get_placeholder()
    
    # Clear any previous configurations to only hold one active email inbox config
    cursor.execute("DELETE FROM email_config")
    
    if is_postgres():
        query = """
            INSERT INTO email_config (imap_server, imap_port, email_address, email_password, is_connected)
            VALUES (%s, %s, %s, %s, 1)
        """
    else:
        query = """
            INSERT INTO email_config (imap_server, imap_port, email_address, email_password, is_connected)
            VALUES (?, ?, ?, ?, 1)
        """
    cursor.execute(query, (imap_server, imap_port, email_address, email_password))
    conn.commit()
    conn.close()

def get_email_config():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT imap_server, imap_port, email_address, email_password, is_connected
        FROM email_config
        WHERE is_connected = 1
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "imap_server": row["imap_server"],
            "imap_port": row["imap_port"],
            "email_address": row["email_address"],
            "email_password": row["email_password"],
            "is_connected": bool(row["is_connected"])
        }
    return None

def disconnect_email() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE email_config SET is_connected = 0")
    conn.commit()
    conn.close()


import os
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.config import get_settings
from app.models import ContractAnalysisResponse, ClauseFinding
from app.services.llm_review import review_with_llm
from app.services.llm_chat import chat_with_llm
from app.services.risk_rules import analyze_text, calculate_risk_score, risk_level_from_score
from app.services.text_extraction import extract_text_from_upload

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="static"), name="static")
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
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}

@app.post("/api/contracts/analyze", response_model=ContractAnalysisResponse)
async def analyze_contract(
    file: UploadFile = File(...),
    jurisdiction: str | None = Form(default=None),
    language: str | None = Form(default=None),
) -> ContractAnalysisResponse:
    contract_text = await extract_text_from_upload(file, settings.max_upload_mb)
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
    return ContractAnalysisResponse(
        file_name=file.filename or "uploaded-contract",
        summary=summary,
        risk_score=risk_score,
        risk_level=risk_level,
        findings=findings,
        llm_review=llm_review,
        contract_text=contract_text,
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
        message=request.message,
        contract_text=request.contract_text,
        findings=request.findings,
        laws_text=laws_text,
        policies_text=policies_text,
        chat_history=history_list,
    )
    
    return {"reply": reply}

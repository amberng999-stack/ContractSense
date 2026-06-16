from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import ContractAnalysisResponse
from app.services.llm_review import review_with_llm
from app.services.risk_rules import analyze_text, calculate_risk_score, risk_level_from_score
from app.services.text_extraction import extract_text_from_upload


settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
    )
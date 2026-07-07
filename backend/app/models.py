from typing import Literal
from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]

class ClauseFinding(BaseModel):
    id: str
    category: str
    title: str
    severity: RiskLevel
    confidence: float = Field(ge=0, le=1)
    excerpt: str
    explanation: str
    recommendation: str
    line_number: int | None = None
    matched_snippet: str | None = None
    law_section: str | None = None
    law_text: str | None = None
    rewrite: str | None = None


class LlmReview(BaseModel):
    provider: str
    model: str
    review: str

class PageSize(BaseModel):
    width: float
    height: float

class HighlightBoxOut(BaseModel):
    finding_id: str       # links back to ClauseFinding.id
    page: int             # 0-indexed
    x0: float
    x1: float
    top: float
    bottom: float
    severity: RiskLevel

class ContractAnalysisResponse(BaseModel):
    id: int | None = None
    file_name: str
    summary: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    findings: list[ClauseFinding]
    llm_review: LlmReview | None = None
    contract_text: str | None = None
    # PDF-native rendering data — present only when the upload was a PDF
    # that pdfplumber could parse. Frontend uses these to render the real
    # PDF pages via PDF.js and overlay highlight boxes at exact coordinates,
    # instead of reconstructing the document as HTML text.
    pdf_base64: str | None = None
    page_sizes: list[PageSize] | None = None
    highlight_boxes: list[HighlightBoxOut] | None = None
    company: str | None = None
    date: str | None = None
    time: str | None = None
    is_automated: bool | None = None

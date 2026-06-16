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


class LlmReview(BaseModel):
    provider: str
    model: str
    review: str


class ContractAnalysisResponse(BaseModel):
    file_name: str
    summary: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    findings: list[ClauseFinding]
    llm_review: LlmReview | None = None
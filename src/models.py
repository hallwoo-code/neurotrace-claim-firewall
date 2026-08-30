from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


REVIEW_STATUSES = ("pending", "approve", "needs_fix", "reject")


@dataclass(frozen=True)
class EvidenceRecord:
    paper_id: str
    citation: str
    year: int
    title: str
    pdf_file_name: str
    sha256: str
    evidence_role: str
    directness: str
    scope: str
    finding: str
    claim_boundary: str
    source_pages: List[int]
    related_figures: List[str]
    population: str
    conditions: str
    erp_windows: List[str]
    effect_direction: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditRisk:
    risk_id: str
    title: str
    explanation: str
    trigger: str
    severity: str = "high"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class AuditResult:
    verdict: str
    verdict_zh: str
    dimensions: Dict[str, str]
    risks: List[AuditRisk] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "verdict_zh": self.verdict_zh,
            "dimensions": dict(self.dimensions),
            "risks": [risk.to_dict() for risk in self.risks],
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class ReviewDecision:
    status: str = "pending"
    corrected_value: str = ""
    reviewed_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in REVIEW_STATUSES:
            raise ValueError(f"Unsupported review status: {self.status}")

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


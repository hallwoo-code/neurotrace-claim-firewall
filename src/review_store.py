from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping

from .models import EvidenceRecord, ReviewDecision


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_eligible(review: ReviewDecision) -> bool:
    if review.status == "approve":
        return True
    return review.status == "needs_fix" and bool(review.corrected_value.strip())


def eligible_evidence(
    records: Iterable[EvidenceRecord],
    reviews: Mapping[str, ReviewDecision],
) -> List[Dict[str, object]]:
    eligible: List[Dict[str, object]] = []
    for record in records:
        review = reviews.get(record.paper_id, ReviewDecision())
        if not is_eligible(review):
            continue
        item = record.to_dict()
        item["original_finding"] = record.finding
        if review.status == "needs_fix":
            item["finding"] = review.corrected_value.strip()
        item["review"] = review.to_dict()
        # Evidence role is copied from the immutable source record and can never be promoted.
        item["evidence_role"] = record.evidence_role
        eligible.append(item)
    return eligible


def normalize_reviews(raw: Mapping[str, Mapping[str, str]]) -> Dict[str, ReviewDecision]:
    return {
        paper_id: ReviewDecision(
            status=value.get("status", "pending"),
            corrected_value=value.get("corrected_value", ""),
            reviewed_at=value.get("reviewed_at", ""),
        )
        for paper_id, value in raw.items()
    }


from src.evidence_store import load_evidence
from src.models import ReviewDecision
from src.review_store import eligible_evidence, is_eligible


def test_pending_reject_and_unfixed_records_are_excluded():
    assert not is_eligible(ReviewDecision("pending"))
    assert not is_eligible(ReviewDecision("reject"))
    assert not is_eligible(ReviewDecision("needs_fix", "  "))


def test_needs_fix_requires_and_exports_corrected_value():
    record = load_evidence()[0]
    review = ReviewDecision("needs_fix", "经人工核验后的修订发现。", "2026-08-29T00:00:00+00:00")
    items = eligible_evidence([record], {record.paper_id: review})
    assert len(items) == 1
    assert items[0]["finding"] == "经人工核验后的修订发现。"
    assert items[0]["original_finding"] == record.finding
    assert items[0]["evidence_role"] == "boundary_evidence"


def test_approve_keeps_baiocco_as_boundary_evidence():
    record = load_evidence()[0]
    items = eligible_evidence([record], {record.paper_id: ReviewDecision("approve")})
    assert items[0]["evidence_role"] == "boundary_evidence"
    assert items[0]["directness"] == "not_a_direct_test_of_supportive_context"


from src.claim_audit import GOLDEN_CLAIM, audit_claim
from src.evidence_store import load_evidence


def test_golden_claim_is_overgeneralized_with_all_required_risks():
    result = audit_claim(GOLDEN_CLAIM)
    assert result.verdict == "Overgeneralized"
    assert result.verdict_zh == "过度概括"
    assert result.dimensions["ERP_component"] == "N400"
    assert set(result.dimensions) == {
        "population", "context", "metaphor_type", "task", "ERP_component",
        "processing_stage", "effect_direction",
    }
    assert {risk.risk_id for risk in result.risks} == {
        "absolute_language", "cross_type_generalization", "n400_direction",
        "processing_stage_omission", "task_emotionality_boundary",
    }


def test_evidence_roles_are_locked_to_the_three_papers():
    records = {item.citation: item for item in load_evidence()}
    assert records["Tang et al. (2025)"].evidence_role == "conditional_support"
    assert records["Yao et al. (2025)"].evidence_role == "direct_qualifier_or_counterevidence"
    baiocco = records["Baiocco et al. (2025)"]
    assert baiocco.evidence_role == "boundary_evidence"
    assert baiocco.directness == "not_a_direct_test_of_supportive_context"


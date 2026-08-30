from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .models import EvidenceRecord


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_PATH = PROJECT_ROOT / "data" / "gold_evidence.json"

EXPECTED_ROLES = {
    "unknown-nd-baiocco-metaphor-processing-is-influenced-c9e215e1": "boundary_evidence",
    "unknown-nd-tang-等-context-modulating-effect-80fe1563": "conditional_support",
    "unknown-nd-yao-等-dynamic-effect-of-1033eeb9": "direct_qualifier_or_counterevidence",
}


def load_evidence(path: Path = DEFAULT_EVIDENCE_PATH) -> List[EvidenceRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = [EvidenceRecord(**item) for item in payload["records"]]
    validate_evidence(records)
    return records


def validate_evidence(records: Iterable[EvidenceRecord]) -> None:
    records = list(records)
    if len(records) != 3:
        raise ValueError("NeuroTrace MVP must contain exactly three claim-level records.")
    ids = {record.paper_id for record in records}
    if ids != set(EXPECTED_ROLES):
        raise ValueError("Evidence IDs do not match the three locked papers.")
    for record in records:
        if record.evidence_role != EXPECTED_ROLES[record.paper_id]:
            raise ValueError(f"Locked evidence role changed for {record.paper_id}.")
        if not record.source_pages or not record.related_figures:
            raise ValueError(f"Missing traceability for {record.paper_id}.")
        if len(record.sha256) != 64:
            raise ValueError(f"Invalid SHA256 for {record.paper_id}.")


from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Sequence

from .models import AuditResult, EvidenceRecord, ReviewDecision
from .review_store import eligible_evidence


SCOPE_STATEMENT = "仅覆盖3篇黄金论文、1条演示论断；不是通用RAG或开放问答系统。"


def build_evidence_pack(
    original_claim: str,
    audit: AuditResult,
    safe_rewrite: str,
    records: Iterable[EvidenceRecord],
    reviews: Mapping[str, ReviewDecision],
    source_integrity: Mapping[str, Mapping[str, object]],
    generated_at: str = "",
) -> Dict[str, object]:
    record_list = list(records)
    evidence = eligible_evidence(record_list, reviews)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    public_integrity: Dict[str, Dict[str, object]] = {}
    for record in record_list:
        source = source_integrity.get(record.paper_id, {})
        public_integrity[record.paper_id] = {
            "status": source.get("status", "unknown"),
            "file_name": record.pdf_file_name,
            "expected_sha256": source.get("expected_sha256", record.sha256),
            "actual_sha256": source.get("actual_sha256", ""),
        }
    return {
        "product": "NeuroTrace",
        "generated_at": generated_at,
        "scope_statement": SCOPE_STATEMENT,
        "original_claim": original_claim,
        "audit": audit.to_dict(),
        "safe_rewrite": safe_rewrite,
        "eligible_evidence_count": len(evidence),
        "evidence_matrix": evidence,
        "source_integrity": public_integrity,
    }


def export_json(pack: Mapping[str, object]) -> str:
    return json.dumps(pack, ensure_ascii=False, indent=2)


def export_markdown(pack: Mapping[str, object]) -> str:
    audit = pack["audit"]
    assert isinstance(audit, Mapping)
    dimensions = audit["dimensions"]
    risks = audit["risks"]
    evidence = pack["evidence_matrix"]
    integrity = pack["source_integrity"]
    assert isinstance(dimensions, Mapping)
    assert isinstance(risks, Sequence)
    assert isinstance(evidence, Sequence)
    assert isinstance(integrity, Mapping)

    lines = [
        "# NeuroTrace Evidence Pack",
        "",
        f"- Generated at: `{pack['generated_at']}`",
        f"- Scope: {pack['scope_statement']}",
        "",
        "## Original claim",
        "",
        str(pack["original_claim"]),
        "",
        "## Audit verdict",
        "",
        f"**{audit['verdict']} / {audit['verdict_zh']}**",
        "",
        str(audit["explanation"]),
        "",
        "### Claim dimensions",
        "",
        "| Dimension | Compiled value |",
        "|---|---|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in dimensions.items())
    lines.extend(["", "### Scope risks", ""])
    for risk in risks:
        assert isinstance(risk, Mapping)
        lines.append(f"- **{risk['title']}** — {risk['explanation']}")
    lines.extend(["", "## Safe rewrite", "", str(pack["safe_rewrite"]), "", "## Reviewed evidence matrix", ""])

    if not evidence:
        lines.append("No evidence passed the human-review gate.")
    for item in evidence:
        assert isinstance(item, Mapping)
        review = item["review"]
        assert isinstance(review, Mapping)
        lines.extend([
            f"### {item['citation']}",
            "",
            f"- Role: `{item['evidence_role']}`",
            f"- Directness: `{item['directness']}`",
            f"- Scope: {item['scope']}",
            f"- Finding: {item['finding']}",
            f"- Claim boundary: {item['claim_boundary']}",
            f"- Source pages: {', '.join(map(str, item['source_pages']))}",
            f"- Related figures: {', '.join(item['related_figures'])}",
            f"- Review: `{review['status']}` at `{review['reviewed_at'] or 'not-recorded'}`",
            f"- Corrected value: {review['corrected_value'] or '—'}",
            "",
        ])

    lines.extend(["## Source integrity", "", "| Paper ID | Status | SHA256 |", "|---|---|---|"])
    for paper_id, item in integrity.items():
        assert isinstance(item, Mapping)
        sha = item.get("actual_sha256") or item.get("expected_sha256") or ""
        lines.append(f"| `{paper_id}` | {item.get('status', 'unknown')} | `{sha}` |")
    lines.append("")
    return "\n".join(lines)


CSV_FIELDS = [
    "product", "generated_at", "scope_statement", "original_claim", "audit_verdict",
    "audit_verdict_zh", "risk_ids", "dimensions_json", "safe_rewrite", "paper_id",
    "citation", "evidence_role", "directness", "scope", "finding", "original_finding",
    "claim_boundary", "source_pages", "related_figures", "review_status", "corrected_value",
    "reviewed_at", "expected_sha256", "actual_sha256", "integrity_status",
]


def export_csv(pack: Mapping[str, object]) -> str:
    audit = pack["audit"]
    assert isinstance(audit, Mapping)
    evidence = pack["evidence_matrix"]
    integrity = pack["source_integrity"]
    assert isinstance(evidence, Sequence)
    assert isinstance(integrity, Mapping)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for item in evidence:
        assert isinstance(item, Mapping)
        review = item["review"]
        assert isinstance(review, Mapping)
        source = integrity.get(item["paper_id"], {})
        assert isinstance(source, Mapping)
        writer.writerow({
            "product": pack["product"],
            "generated_at": pack["generated_at"],
            "scope_statement": pack["scope_statement"],
            "original_claim": pack["original_claim"],
            "audit_verdict": audit["verdict"],
            "audit_verdict_zh": audit["verdict_zh"],
            "risk_ids": "|".join(str(risk["risk_id"]) for risk in audit["risks"]),
            "dimensions_json": json.dumps(audit["dimensions"], ensure_ascii=False),
            "safe_rewrite": pack["safe_rewrite"],
            "paper_id": item["paper_id"],
            "citation": item["citation"],
            "evidence_role": item["evidence_role"],
            "directness": item["directness"],
            "scope": item["scope"],
            "finding": item["finding"],
            "original_finding": item["original_finding"],
            "claim_boundary": item["claim_boundary"],
            "source_pages": "|".join(map(str, item["source_pages"])),
            "related_figures": "|".join(item["related_figures"]),
            "review_status": review["status"],
            "corrected_value": review["corrected_value"],
            "reviewed_at": review["reviewed_at"],
            "expected_sha256": source.get("expected_sha256", item["sha256"]),
            "actual_sha256": source.get("actual_sha256", ""),
            "integrity_status": source.get("status", "unknown"),
        })
    return "\ufeff" + buffer.getvalue()

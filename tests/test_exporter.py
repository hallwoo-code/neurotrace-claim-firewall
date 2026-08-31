import csv
import io
import json

from src.claim_audit import GOLDEN_CLAIM, SAFE_REWRITE, audit_claim
from src.evidence_store import load_evidence
from src.exporter import build_evidence_pack, export_csv, export_json, export_markdown
from src.models import ReviewDecision


def _pack():
    records = load_evidence()
    reviews = {
        records[0].paper_id: ReviewDecision("approve", reviewed_at="2026-08-29T00:00:00+00:00"),
        records[1].paper_id: ReviewDecision("needs_fix", "修订后的 Tang 发现。", "2026-08-29T00:01:00+00:00"),
        records[2].paper_id: ReviewDecision("reject", reviewed_at="2026-08-29T00:02:00+00:00"),
    }
    integrity = {
        record.paper_id: {
            "status": "verified", "path": f"C:\\private\\papers\\{record.pdf_file_name}",
            "expected_sha256": record.sha256, "actual_sha256": record.sha256,
        }
        for record in records
    }
    return build_evidence_pack(
        GOLDEN_CLAIM, audit_claim(GOLDEN_CLAIM), SAFE_REWRITE,
        records, reviews, integrity, "2026-08-29T00:03:00+00:00",
    )


def test_json_markdown_and_csv_round_trip_with_traceability():
    pack = _pack()
    parsed_json = json.loads(export_json(pack))
    parsed_csv = list(csv.DictReader(io.StringIO(export_csv(pack).lstrip("\ufeff"))))
    markdown = export_markdown(pack)
    assert parsed_json["eligible_evidence_count"] == 2
    assert len(parsed_csv) == 2
    assert parsed_csv[1]["finding"] == "修订后的 Tang 发现。"
    assert "Fig. 3" in markdown and "Fig. 11" in markdown
    assert "Source pages: 1, 10" in markdown
    assert "不是通用RAG" in markdown
    assert all(row["expected_sha256"] for row in parsed_csv)
    assert all("path" not in source for source in parsed_json["source_integrity"].values())
    assert all(source["file_name"].endswith(".pdf") for source in parsed_json["source_integrity"].values())
    assert "C:\\private\\papers" not in export_json(pack)

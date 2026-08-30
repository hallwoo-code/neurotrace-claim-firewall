import json

import pytest

from src.evidence_store import load_evidence
from src.source_integrity import configured_pdf_dir, sha256_file, verify_sources


def test_sha256_file_and_mismatch_detection(tmp_path):
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"read-only-source")
    assert sha256_file(path) == "1CCB3574F0CE2A85697DF68B9B4551536B60E3614444A7275075A8CB5E69EEBC"


def test_locked_sources_match_when_local_config_is_present():
    pdf_dir = configured_pdf_dir()
    if pdf_dir is None:
        pytest.skip("Local PDF directory is intentionally not committed.")
    results = verify_sources(load_evidence(), pdf_dir)
    assert {item["status"] for item in results.values()} == {"verified"}

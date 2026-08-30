from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional

from .models import EvidenceRecord


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG_PATH = PROJECT_ROOT / "config.local.json"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def configured_pdf_dir(config_path: Path = LOCAL_CONFIG_PATH) -> Optional[Path]:
    env_value = os.getenv("NEUROTRACE_PDF_DIR", "").strip()
    if env_value:
        return Path(env_value).expanduser()
    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        value = str(payload.get("pdf_dir", "")).strip()
        if value:
            return Path(value).expanduser()
    return None


def resolve_source_path(record: EvidenceRecord, pdf_dir: Optional[Path]) -> Optional[Path]:
    return None if pdf_dir is None else pdf_dir / record.pdf_file_name


def verify_sources(
    records: Iterable[EvidenceRecord], pdf_dir: Optional[Path]
) -> Dict[str, Dict[str, object]]:
    results: Dict[str, Dict[str, object]] = {}
    for record in records:
        path = resolve_source_path(record, pdf_dir)
        if path is None or not path.is_file():
            results[record.paper_id] = {
                "status": "missing",
                "path": str(path) if path else "未配置 NEUROTRACE_PDF_DIR",
                "expected_sha256": record.sha256,
                "actual_sha256": "",
            }
            continue
        actual = sha256_file(path)
        results[record.paper_id] = {
            "status": "verified" if actual == record.sha256.upper() else "mismatch",
            "path": str(path),
            "expected_sha256": record.sha256,
            "actual_sha256": actual,
        }
    return results


def integrity_hash_map(results: Mapping[str, Mapping[str, object]]) -> Dict[str, str]:
    return {
        paper_id: str(result.get("actual_sha256") or result.get("expected_sha256") or "")
        for paper_id, result in results.items()
    }


from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:23119/api/users/0"


class ZoteroUnavailableError(RuntimeError):
    """Raised when the Zotero local API cannot be read."""


@dataclass(frozen=True)
class ZoteroPaper:
    item_key: str
    title: str
    creators: List[str]
    year: str
    item_type: str
    attachment_key: str
    pdf_path: Optional[Path]
    metadata_complete: bool
    metadata_source: str = "zotero"

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["pdf_path"] = str(self.pdf_path) if self.pdf_path else ""
        return payload


def _api_get(path: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 8.0):
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(url, headers={"Zotero-API-Version": "3"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            content_type = response.headers.get("Content-Type", "")
    except Exception as exc:  # urllib exposes platform-specific connection errors.
        raise ZoteroUnavailableError(
            "无法连接 Zotero 本地 API。请保持 Zotero Desktop 打开；23119 是程序接口，不是审核网页。"
        ) from exc
    if "json" in content_type:
        return json.loads(raw)
    return raw.strip()


def file_uri_to_path(uri: str) -> Optional[Path]:
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme.lower() != "file":
        return None
    raw = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:/", raw):
        raw = raw[1:]
    return Path(raw)


def _creator_names(data: Mapping[str, object], meta: Mapping[str, object]) -> List[str]:
    names: List[str] = []
    for creator in data.get("creators", []) or []:
        if not isinstance(creator, Mapping):
            continue
        name = str(creator.get("name", "")).strip()
        if not name:
            name = " ".join(
                part for part in (str(creator.get("firstName", "")).strip(), str(creator.get("lastName", "")).strip())
                if part
            )
        if name:
            names.append(name)
    if not names and meta.get("creatorSummary"):
        names.append(str(meta["creatorSummary"]))
    return names


def _attachment_key(item: Mapping[str, object]) -> str:
    data = item.get("data", {}) or {}
    if data.get("itemType") == "attachment" and (
        data.get("contentType") == "application/pdf"
        or str(data.get("filename", "")).lower().endswith(".pdf")
        or str(data.get("title", "")).lower().endswith(".pdf")
        or data.get("linkMode") == "imported_file"
    ):
        return str(item.get("key", ""))
    attachment = (item.get("links", {}) or {}).get("attachment", {}) or {}
    if attachment.get("attachmentType") != "application/pdf":
        return ""
    return str(attachment.get("href", "")).rstrip("/").split("/")[-1]


def load_collection(
    collection_key: str,
    base_url: str = DEFAULT_BASE_URL,
    resolve_paths: bool = True,
) -> List[ZoteroPaper]:
    if not collection_key.strip():
        raise ValueError("Zotero collection key cannot be empty.")
    items = _api_get(f"collections/{collection_key}/items/top?limit=100", base_url=base_url)
    if not isinstance(items, list):
        raise ZoteroUnavailableError("Zotero collection 返回了无法识别的数据。")

    papers: List[ZoteroPaper] = []
    for item in items:
        data = item.get("data", {}) or {}
        meta = item.get("meta", {}) or {}
        attachment_key = _attachment_key(item)
        pdf_path = None
        if resolve_paths and attachment_key:
            uri = _api_get(f"items/{attachment_key}/file/view/url", base_url=base_url)
            pdf_path = file_uri_to_path(str(uri))
        title = str(data.get("title", "")).strip() or f"Untitled Zotero item {item.get('key', '')}"
        year = str(meta.get("parsedDate") or data.get("date") or "").strip()
        creators = _creator_names(data, meta)
        papers.append(
            ZoteroPaper(
                item_key=str(item.get("key", "")),
                title=title,
                creators=creators,
                year=year,
                item_type=str(data.get("itemType", "")),
                attachment_key=attachment_key,
                pdf_path=pdf_path,
                metadata_complete=bool(creators and year and data.get("itemType") != "attachment"),
                metadata_source="zotero" if data.get("itemType") != "attachment" else "zotero_attachment",
            )
        )
    return papers


def apply_metadata_overrides(papers: Iterable[ZoteroPaper], override_path: Path) -> List[ZoteroPaper]:
    """Apply an auditable fallback for standalone PDFs without parent metadata."""
    if not override_path.is_file():
        return list(papers)
    payload = json.loads(override_path.read_text(encoding="utf-8"))
    overrides = payload.get("items", {}) if isinstance(payload, dict) else {}
    enriched: List[ZoteroPaper] = []
    for paper in papers:
        override = overrides.get(paper.item_key) or overrides.get(paper.attachment_key)
        if not isinstance(override, Mapping):
            enriched.append(paper)
            continue
        title = str(override.get("title", "")).strip() or paper.title
        creators = [str(value).strip() for value in override.get("creators", []) if str(value).strip()]
        year = str(override.get("year", "")).strip() or paper.year
        enriched.append(
            replace(
                paper,
                title=title,
                creators=creators or paper.creators,
                year=year,
                metadata_complete=bool(title and (creators or paper.creators) and year),
                metadata_source=str(override.get("source", "pdf_first_page")),
            )
        )
    return enriched


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"\.pdf$", "", value)
    value = re.sub(r"\b(?:19|20)\d{2}\b", " ", value)
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def title_similarity(left: str, right: str) -> float:
    a = normalize_title(left)
    b = normalize_title(right)
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    overlap = len(a_tokens & b_tokens)
    coverage = overlap / max(1, min(len(a_tokens), len(b_tokens)))
    containment = 1.0 if a in b or b in a else 0.0
    return max(seq, coverage * 0.95, containment)


def load_legacy_rows(index_path: Path) -> List[Dict[str, str]]:
    with index_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def map_legacy_papers(
    papers: Iterable[ZoteroPaper],
    legacy_rows: Iterable[Mapping[str, str]],
    minimum_score: float = 0.55,
) -> Dict[str, ZoteroPaper]:
    papers = list(papers)
    mapping: Dict[str, ZoteroPaper] = {}
    used: set[str] = set()
    for row in legacy_rows:
        paper_id = str(row.get("paper_id", ""))
        pdf_stem = Path(str(row.get("pdf_path", ""))).stem
        candidates = []
        for paper in papers:
            if paper.item_key in used:
                continue
            score = max(
                title_similarity(str(row.get("title", "")), paper.title),
                title_similarity(pdf_stem, paper.title),
            )
            candidates.append((score, paper))
        if not candidates:
            continue
        score, best = max(candidates, key=lambda value: value[0])
        if score >= minimum_score:
            mapping[paper_id] = best
            used.add(best.item_key)
    return mapping

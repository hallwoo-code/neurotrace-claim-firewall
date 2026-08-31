from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REVIEW_SELECTOR_PREFIX = "review_item_selector__"
REVIEW_SELECTOR_EPOCH_KEY = "_review_item_selector_epoch"
DEFERRED_REVIEW_SELECTOR_KEY = "_deferred_review_item_selector"


@dataclass(frozen=True)
class CorpusReviewConfig:
    zotero_collection_key: str
    review_queue_path: Path
    literature_index_path: Path
    generated_notes_dir: Path
    review_output_path: Path


@dataclass(frozen=True)
class ReviewItem:
    review_id: str
    paper_id: str
    target_type: str
    target_id: str
    question: str
    current_value: str
    source_trace: str
    priority: str
    original_status: str
    value: Mapping[str, object] = field(default_factory=dict)

    @property
    def label(self) -> str:
        primary = str(self.value.get("label") or self.value.get("title") or self.value.get("experiment_label") or self.target_id)
        page = self.primary_page
        return f"{primary} · p.{page}" if page else primary

    @property
    def primary_page(self) -> Optional[int]:
        if isinstance(self.value.get("page"), (int, float)):
            return int(self.value["page"])
        if isinstance(self.value.get("page_start"), (int, float)):
            return int(self.value["page_start"])
        pages = self.value.get("pages")
        if isinstance(pages, list) and pages:
            try:
                return int(pages[0])
            except (TypeError, ValueError):
                pass
        match = re.search(r"PDF pages?\s+(\d+)", self.source_trace, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    @property
    def page_range(self) -> Tuple[List[int], List[str]]:
        issues: List[str] = []
        pages: List[int] = []
        if isinstance(self.value.get("page"), (int, float)):
            pages = [int(self.value["page"])]
        elif "page_start" in self.value:
            start = int(self.value.get("page_start") or 0)
            end = int(self.value.get("page_end") or 0)
            if start > 0:
                pages = [start]
            if end <= 0:
                issues.append("旧标签的 page_end 缺失或为 0")
            elif end < start:
                issues.append("旧标签的 page_end 早于 page_start")
            else:
                pages = list(range(start, min(end, start + 30) + 1))
        elif isinstance(self.value.get("pages"), list):
            pages = [int(page) for page in self.value["pages"] if isinstance(page, (int, float)) and int(page) > 0]
        return pages, issues

    @property
    def locator_text(self) -> str:
        for key in ("caption", "title", "experiment_label"):
            value = str(self.value.get(key, "")).strip()
            if value:
                return value
        match = re.search(r":\s*(.+)$", self.source_trace)
        return match.group(1).strip() if match else ""


@dataclass(frozen=True)
class CorpusDecision:
    status: str = "pending"
    corrected_value: str = ""
    corrected_page: Optional[int] = None
    notes: str = ""
    human_location_confirmed: bool = False
    reviewed_at: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def defer_review_selection(state: MutableMapping[str, object], review_id: str) -> None:
    """Queue a target and rotate to a new widget key on the next script run."""
    state[DEFERRED_REVIEW_SELECTOR_KEY] = review_id
    state[REVIEW_SELECTOR_EPOCH_KEY] = int(state.get(REVIEW_SELECTOR_EPOCH_KEY, 0)) + 1


def prepare_review_selector(
    state: MutableMapping[str, object], option_ids: Sequence[str]
) -> Tuple[str, int]:
    """Return a fresh widget key and target index without mutating a widget key."""
    if not option_ids:
        raise ValueError("option_ids cannot be empty")
    review_id = state.pop(DEFERRED_REVIEW_SELECTOR_KEY, None)
    selected_index = option_ids.index(review_id) if isinstance(review_id, str) and review_id in option_ids else 0
    epoch = int(state.get(REVIEW_SELECTOR_EPOCH_KEY, 0))
    context = hashlib.sha1("\0".join(option_ids).encode("utf-8")).hexdigest()[:10]
    return f"{REVIEW_SELECTOR_PREFIX}{context}_{epoch}", selected_index


def build_core_review_ids(items: Sequence[ReviewItem]) -> set[str]:
    """Build a compact review set: main card, experiment unit, and one result figure per paper."""
    core = {item.review_id for item in items if item.target_type in {"main_card", "experiment_unit"}}
    figures_by_paper: Dict[str, List[ReviewItem]] = {}
    for item in items:
        if item.target_type == "figure_table":
            figures_by_paper.setdefault(item.paper_id, []).append(item)

    result_terms = (
        "n400", "p600", "erp", "waveform", "grand average", "topograph",
        "amplitude", "electrode", "effect", "interaction",
    )

    def figure_score(item: ReviewItem) -> Tuple[float, int, str]:
        text = " ".join(str(value) for value in item.value.values()).lower()
        keyword_score = sum(term in text for term in result_terms)
        try:
            confidence = float(item.value.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        valid_page = int(bool(item.primary_page and item.primary_page > 0))
        return keyword_score + confidence, valid_page, item.review_id

    for figures in figures_by_paper.values():
        core.add(max(figures, key=figure_score).review_id)
    return core


def load_review_config(config_path: Path = PROJECT_ROOT / "config.local.json") -> CorpusReviewConfig:
    payload: Dict[str, object] = {}
    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))

    def setting(env: str, key: str, default: str = "") -> str:
        return os.getenv(env, "").strip() or str(payload.get(key, default)).strip()

    collection_key = setting("NEUROTRACE_ZOTERO_COLLECTION_KEY", "zotero_collection_key", "TIGIF3TV")
    queue_path = setting("NEUROTRACE_REVIEW_QUEUE", "review_queue_path")
    index_path = setting("NEUROTRACE_LITERATURE_INDEX", "literature_index_path")
    notes_dir = setting("NEUROTRACE_GENERATED_NOTES_DIR", "generated_notes_dir")
    if not queue_path or not index_path:
        raise ValueError("请在 config.local.json 配置 review_queue_path 与 literature_index_path。")
    return CorpusReviewConfig(
        zotero_collection_key=collection_key,
        review_queue_path=Path(queue_path).expanduser(),
        literature_index_path=Path(index_path).expanduser(),
        generated_notes_dir=Path(notes_dir).expanduser() if notes_dir else Path(),
        review_output_path=PROJECT_ROOT / "outputs" / "corpus_reviews.json",
    )


def _parse_value(raw: str) -> Mapping[str, object]:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"value": value}
    except (json.JSONDecodeError, TypeError):
        return {"text": raw}


def load_review_items(path: Path) -> List[ReviewItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items = payload.get("items", []) if isinstance(payload, dict) else payload
    return [
        ReviewItem(
            review_id=str(item["review_id"]),
            paper_id=str(item["paper_id"]),
            target_type=str(item["target_type"]),
            target_id=str(item["target_id"]),
            question=str(item.get("question", "")),
            current_value=str(item.get("current_value", "")),
            source_trace=str(item.get("source_trace", "")),
            priority=str(item.get("priority", "medium")),
            original_status=str(item.get("status", "pending")),
            value=_parse_value(str(item.get("current_value", ""))),
        )
        for item in raw_items
    ]


def load_decisions(path: Path) -> Dict[str, CorpusDecision]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    decisions = payload.get("decisions", {})
    return {
        review_id: CorpusDecision(
            status=str(value.get("status", "pending")),
            corrected_value=str(value.get("corrected_value", "")),
            corrected_page=value.get("corrected_page"),
            notes=str(value.get("notes", "")),
            human_location_confirmed=bool(value.get("human_location_confirmed", False)),
            reviewed_at=str(value.get("reviewed_at", "")),
        )
        for review_id, value in decisions.items()
    }


def save_decision(path: Path, review_id: str, decision: CorpusDecision) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "1.0", "updated_at": _utc_now(), "decisions": {}}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("decisions", {})
    payload["updated_at"] = _utc_now()
    payload["decisions"][review_id] = decision.to_dict()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_decision(decision: CorpusDecision, location_confirmed: bool) -> Optional[str]:
    if decision.status not in {"pending", "approve", "needs_fix", "reject"}:
        return "审核状态无效。"
    if decision.status == "approve" and not location_confirmed:
        return "通过为 Gold 前，必须在原始 PDF 中人工确认位置并勾选确认；否则请改为 needs_fix / reject。"
    if decision.status == "needs_fix" and not (decision.corrected_value.strip() or decision.corrected_page):
        return "needs_fix 至少需要填写修订值或修订页码。"
    return None


def export_review_json(
    items: Iterable[ReviewItem], decisions: Mapping[str, CorpusDecision], paper_titles: Mapping[str, str]
) -> bytes:
    records = []
    for item in items:
        decision = decisions.get(item.review_id, CorpusDecision())
        records.append(
            {
                "review_id": item.review_id,
                "paper_id": item.paper_id,
                "paper_title": paper_titles.get(item.paper_id, item.paper_id),
                "target_type": item.target_type,
                "target_id": item.target_id,
                "source_trace": item.source_trace,
                "candidate": dict(item.value),
                "review": decision.to_dict(),
            }
        )
    return json.dumps({"schema_version": "1.0", "records": records}, ensure_ascii=False, indent=2).encode("utf-8")


def export_review_csv(
    items: Iterable[ReviewItem], decisions: Mapping[str, CorpusDecision], paper_titles: Mapping[str, str]
) -> bytes:
    output = io.StringIO(newline="")
    fields = [
        "review_id", "paper_id", "paper_title", "target_type", "target_id", "source_trace",
        "status", "corrected_value", "corrected_page", "notes", "human_location_confirmed", "reviewed_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in items:
        decision = decisions.get(item.review_id, CorpusDecision())
        writer.writerow(
            {
                "review_id": item.review_id,
                "paper_id": item.paper_id,
                "paper_title": paper_titles.get(item.paper_id, item.paper_id),
                "target_type": item.target_type,
                "target_id": item.target_id,
                "source_trace": item.source_trace,
                **decision.to_dict(),
            }
        )
    return output.getvalue().encode("utf-8-sig")


def main_card_path(config: CorpusReviewConfig, paper_id: str) -> Optional[Path]:
    if not str(config.generated_notes_dir):
        return None
    path = config.generated_notes_dir / paper_id / f"{paper_id}_main_card.md"
    return path if path.is_file() else None

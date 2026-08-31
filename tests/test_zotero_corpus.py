import json
from pathlib import Path

from src.zotero_corpus import (
    ZoteroPaper,
    apply_metadata_overrides,
    file_uri_to_path,
    map_legacy_papers,
    title_similarity,
)


def test_file_uri_to_windows_path_and_title_similarity():
    path = file_uri_to_path("file:///C:/Users/demo/Zotero/storage/ABC/Paper%20Title.pdf")
    assert path == Path("C:/Users/demo/Zotero/storage/ABC/Paper Title.pdf")
    assert title_similarity(
        "Tang - 2025 - Context-modulating effect on processing scientific metaphors",
        "Context-modulating effect on processing scientific metaphors: Evidence from ERPs",
    ) > 0.75


def test_map_legacy_papers_uses_real_zotero_title():
    paper = ZoteroPaper(
        item_key="ITEM1234",
        title="Dynamic effect of context on processing L2 metaphors with varied conventionality: An ERP study",
        creators=["Zhao Yao"],
        year="2025",
        item_type="journalArticle",
        attachment_key="PDF12345",
        pdf_path=Path("Yao.pdf"),
        metadata_complete=True,
    )
    rows = [
        {
            "paper_id": "legacy-yao",
            "title": "yao dynamic effect of context on processing l2 metaphors with varied conventionality an erp study",
            "pdf_path": "Yao - 2025 - Dynamic effect of context on processing L2 metaphors.pdf",
        }
    ]
    mapping = map_legacy_papers([paper], rows)
    assert mapping["legacy-yao"].title.startswith("Dynamic effect")


def test_standalone_pdf_metadata_override_is_auditable(tmp_path):
    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        json.dumps(
            {
                "items": {
                    "ATTACH": {
                        "title": "Real title",
                        "creators": ["A. Author"],
                        "year": "2005",
                        "source": "pdf_first_page",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    paper = ZoteroPaper(
        "ATTACH", "filename", [], "", "attachment", "ATTACH", None, False, "zotero_attachment"
    )
    enriched = apply_metadata_overrides([paper], override_path)[0]
    assert enriched.title == "Real title"
    assert enriched.metadata_complete is True
    assert enriched.metadata_source == "pdf_first_page"

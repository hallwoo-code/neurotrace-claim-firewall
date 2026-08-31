import json

from src.corpus_review import (
    CorpusDecision,
    ReviewItem,
    build_core_review_ids,
    defer_review_selection,
    export_review_csv,
    load_decisions,
    load_review_items,
    prepare_review_selector,
    save_decision,
    validate_decision,
)


def _queue_payload():
    return {
        "items": [
            {
                "review_id": "review-1",
                "paper_id": "paper-1",
                "target_type": "functional_section",
                "target_id": "section-1",
                "question": "Confirm section.",
                "current_value": json.dumps(
                    {"title": "Introduction", "page_start": 2, "page_end": 0}, ensure_ascii=False
                ),
                "source_trace": "Heading candidate on PDF page 2: Introduction",
                "priority": "medium",
                "status": "pending",
            }
        ]
    }


def test_queue_parsing_flags_invalid_legacy_page_range(tmp_path):
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(json.dumps(_queue_payload()), encoding="utf-8")
    item = load_review_items(queue_path)[0]
    pages, issues = item.page_range
    assert pages == [2]
    assert "page_end" in issues[0]
    assert item.locator_text == "Introduction"


def test_review_store_and_gate(tmp_path):
    output = tmp_path / "reviews.json"
    decision = CorpusDecision(status="approve", human_location_confirmed=True, reviewed_at="2026-01-01T00:00:00+00:00")
    assert validate_decision(decision, location_confirmed=True) is None
    assert validate_decision(CorpusDecision(status="approve"), location_confirmed=False)
    assert validate_decision(CorpusDecision(status="needs_fix"), location_confirmed=True)
    save_decision(output, "review-1", decision)
    loaded = load_decisions(output)
    assert loaded["review-1"].status == "approve"


def test_review_csv_contains_real_paper_title(tmp_path):
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(json.dumps(_queue_payload()), encoding="utf-8")
    item = load_review_items(queue_path)[0]
    payload = export_review_csv([item], {item.review_id: CorpusDecision(status="reject")}, {"paper-1": "Real paper title"})
    text = payload.decode("utf-8-sig")
    assert "Real paper title" in text
    assert "reject" in text


def test_next_review_selection_is_deferred_until_before_widget_creation():
    state = {"review_item_selector__old_0": "review-1"}
    defer_review_selection(state, "review-2")

    # The active widget key is never modified during or after the submit run.
    assert state["review_item_selector__old_0"] == "review-1"

    selector_key, selected_index = prepare_review_selector(state, ["review-1", "review-2"])
    assert selector_key.startswith("review_item_selector__")
    assert selector_key != "review_item_selector__old_0"
    assert selected_index == 1
    assert state["review_item_selector__old_0"] == "review-1"
    assert "_deferred_review_item_selector" not in state


def test_deferred_selection_ignores_item_removed_by_filters():
    state = {"review_item_selector__old_0": "review-1"}
    defer_review_selection(state, "review-2")
    selector_key, selected_index = prepare_review_selector(state, ["review-1"])
    assert selector_key.startswith("review_item_selector__")
    assert selected_index == 0
    assert state["review_item_selector__old_0"] == "review-1"


def test_core_review_set_keeps_cards_experiments_and_one_result_figure_per_paper():
    def item(review_id, paper_id, target_type, value):
        return ReviewItem(review_id, paper_id, target_type, review_id, "", "", "", "high", "pending", value)

    items = [
        item("card-1", "paper-1", "main_card", {}),
        item("experiment-1", "paper-1", "experiment_unit", {}),
        item("figure-method", "paper-1", "figure_table", {"caption": "Trial sequence", "page": 2, "confidence": 0.9}),
        item("figure-result", "paper-1", "figure_table", {"caption": "Grand average N400 waveform", "page": 6, "confidence": 0.7}),
        item("section-1", "paper-1", "functional_section", {"title": "Introduction"}),
    ]
    core = build_core_review_ids(items)
    assert core == {"card-1", "experiment-1", "figure-result"}

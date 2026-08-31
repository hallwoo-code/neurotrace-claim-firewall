from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.corpus_review import (  # noqa: E402
    CorpusDecision,
    ReviewItem,
    build_core_review_ids,
    defer_review_selection,
    export_review_csv,
    export_review_json,
    load_decisions,
    load_review_config,
    load_review_items,
    main_card_path,
    prepare_review_selector,
    save_decision,
    validate_decision,
)
from src.pdf_locator import (  # noqa: E402
    TextLocation,
    annotate_page,
    crop_figure_or_table,
    locate_text,
    page_count,
    png_data_uri,
    render_page_png,
    validate_png_bytes,
)
from src.zotero_corpus import (  # noqa: E402
    ZoteroPaper,
    ZoteroUnavailableError,
    apply_metadata_overrides,
    load_collection,
    load_legacy_rows,
    map_legacy_papers,
)


TYPE_LABELS = {
    "functional_section": "章节结构",
    "figure_table": "图表",
    "experiment_unit": "实验单元",
    "main_card": "论文主卡",
}
STATUS_LABELS = {
    "pending": "待审核",
    "approve": "通过",
    "needs_fix": "需修订",
    "reject": "拒绝",
}
QUESTION_LABELS = {
    "functional_section": "核对章节功能、标题与页码范围。",
    "figure_table": "核对图表标题、类型、实验归属及结果语境。",
    "experiment_unit": "核对实验边界、实验类型和字段抽取。",
    "main_card": "核对论文主卡是否忠实于原文，且不包含未经验证的可用论断。",
}


def inject_styles() -> None:
    tokens = (ROOT / "tokens.css").read_text(encoding="utf-8")
    app_css = (ROOT / "app.css").read_text(encoding="utf-8").replace('@import url("tokens.css");', "")
    review_css = (ROOT / "review.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{tokens}\n{app_css}\n{review_css}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=60, show_spinner=False)
def cached_corpus(collection_key: str, index_path: str) -> Tuple[List[ZoteroPaper], Dict[str, ZoteroPaper]]:
    raw_papers = load_collection(collection_key)
    raw_mapping = map_legacy_papers(raw_papers, load_legacy_rows(Path(index_path)))
    papers = apply_metadata_overrides(raw_papers, ROOT / "data" / "zotero_metadata_overrides.json")
    papers_by_key = {paper.item_key: paper for paper in papers}
    mapping = {paper_id: papers_by_key[paper.item_key] for paper_id, paper in raw_mapping.items()}
    return papers, mapping


@st.cache_data(show_spinner=False)
def cached_items(queue_path: str) -> List[ReviewItem]:
    return load_review_items(Path(queue_path))


@st.cache_data(show_spinner=False)
def cached_page_count(pdf_path: str, modified_ns: int) -> int:
    del modified_ns
    return page_count(Path(pdf_path))


@st.cache_data(show_spinner=False)
def cached_location(pdf_path: str, modified_ns: int, page_number: int, query: str) -> TextLocation:
    del modified_ns
    return locate_text(Path(pdf_path), page_number, query)


@st.cache_data(show_spinner=False)
def cached_page_png(pdf_path: str, modified_ns: int, page_number: int) -> bytes:
    del modified_ns
    return render_page_png(Path(pdf_path), page_number)


def _mtime(path: Path) -> int:
    return path.stat().st_mtime_ns if path.is_file() else 0


def _safe(value: object) -> str:
    return html.escape(str(value if value not in (None, "") else "—"))


def _paper_meta(paper: ZoteroPaper) -> str:
    creators = "; ".join(paper.creators) if paper.creators else "作者元数据缺失"
    year = paper.year or "年份缺失"
    source = "Zotero 元数据" if paper.metadata_source == "zotero" else "PDF 首页校准"
    return f"{creators} · {year} · {source} · Zotero {paper.item_key} · PDF {paper.attachment_key}"


def _location_class(location: TextLocation) -> str:
    if location.confirmed:
        return "nt-location nt-location--ok"
    if location.status in {"invalid_page", "missing_pdf"}:
        return "nt-location nt-location--error"
    return "nt-location nt-location--warn"


def _location_title(location: TextLocation) -> str:
    return {
        "exact": "原文定位通过",
        "approximate": "相似文本定位通过",
        "page_only": "仅确认页码",
        "invalid_page": "页码无效",
        "missing_pdf": "PDF 缺失",
    }.get(location.status, "定位待核对")


def _display_fields(item: ReviewItem) -> List[Tuple[str, object]]:
    value = item.value
    keys_by_type = {
        "functional_section": ("function", "title", "page_start", "page_end", "confidence"),
        "figure_table": ("label", "item_type", "caption", "page", "related_experiment_id", "possible_content_type", "confidence"),
        "experiment_unit": ("experiment_label", "experiment_type", "pages", "participants", "task", "erp_components", "time_windows", "confidence"),
        "main_card": ("text",),
    }
    labels = {
        "function": "预测功能", "title": "候选标题", "page_start": "起始页", "page_end": "结束页",
        "confidence": "旧置信度", "label": "图表标签", "item_type": "类型", "caption": "标题文字",
        "page": "旧页码", "related_experiment_id": "实验归属", "possible_content_type": "内容类型",
        "experiment_label": "实验标签", "experiment_type": "实验类型", "pages": "候选页范围",
        "participants": "被试", "task": "任务", "erp_components": "ERP 成分", "time_windows": "时间窗",
        "text": "旧值",
    }
    fields: List[Tuple[str, object]] = []
    for key in keys_by_type.get(item.target_type, tuple(value.keys())):
        if key in value:
            raw = value[key]
            if isinstance(raw, list):
                raw = ", ".join(map(str, raw)) or "—"
            fields.append((labels.get(key, key), raw))
    return fields


def _render_spec(item: ReviewItem) -> None:
    rows = "".join(
        f"<div><dt>{_safe(label)}</dt><dd>{_safe(value)}</dd></div>" for label, value in _display_fields(item)
    )
    st.markdown(f"<dl class='nt-review-spec'>{rows}</dl>", unsafe_allow_html=True)


def _render_png_preview(payload: bytes, caption: str, alt_text: str) -> None:
    """Render proof images without Streamlit's short-lived media endpoint."""
    width, height = validate_png_bytes(payload)
    source = png_data_uri(payload)
    st.markdown(
        "<figure class='nt-proof-figure'>"
        f"<img src='{source}' alt='{html.escape(alt_text, quote=True)}' "
        f"width='{width}' height='{height}' decoding='async' fetchpriority='high'>"
        f"<figcaption>{html.escape(caption)}</figcaption>"
        "</figure>",
        unsafe_allow_html=True,
    )


def _status_counts(items: List[ReviewItem], decisions: Mapping[str, CorpusDecision]) -> Dict[str, int]:
    counts = {status: 0 for status in STATUS_LABELS}
    for item in items:
        counts[decisions.get(item.review_id, CorpusDecision()).status] += 1
    return counts


def _next_item(current: ReviewItem, visible: List[ReviewItem], decisions: Mapping[str, CorpusDecision]) -> Optional[str]:
    if not visible:
        return None
    try:
        start = visible.index(current)
    except ValueError:
        start = -1
    ordered = visible[start + 1 :] + visible[: start + 1]
    for item in ordered:
        if decisions.get(item.review_id, CorpusDecision()).status == "pending":
            return item.review_id
    return ordered[0].review_id if ordered else None


def _decision_from_form(item: ReviewItem, existing: CorpusDecision) -> Tuple[CorpusDecision, bool, bool]:
    with st.form(f"review_form_{item.review_id}", clear_on_submit=False):
        status = st.radio(
            "审核结论",
            options=list(STATUS_LABELS),
            format_func=STATUS_LABELS.get,
            index=list(STATUS_LABELS).index(existing.status),
            horizontal=True,
        )
        has_details = bool(existing.corrected_page or existing.corrected_value or existing.notes)
        with st.expander("修订与备注（可选）", expanded=has_details):
            corrected_page_raw = st.text_input(
                "修订页码（可选）",
                value=str(existing.corrected_page or ""),
                placeholder="例如：6",
            )
            corrected_value = st.text_area(
                "修订值",
                value=existing.corrected_value,
                placeholder="需修订时填写经 PDF 核对后的完整值；其他状态可留空。",
                height=88,
            )
            notes = st.text_area(
                "审核备注",
                value=existing.notes,
                placeholder="记录判断依据、无法确认的原因或需要回查的内容。",
                height=72,
            )
        human_confirmed = st.checkbox(
            "我已在原始 PDF 页面中人工确认该位置",
            value=existing.human_location_confirmed,
        )
        left, right = st.columns(2)
        save_only = left.form_submit_button("保存审核", use_container_width=True)
        save_next = right.form_submit_button("保存并下一条", type="primary", use_container_width=True)

    corrected_page = None
    if corrected_page_raw.strip():
        if corrected_page_raw.strip().isdigit() and int(corrected_page_raw) > 0:
            corrected_page = int(corrected_page_raw)
        elif save_only or save_next:
            st.error("修订页码必须是大于 0 的整数。")
            return existing, False, False
    reviewed_at = existing.reviewed_at
    candidate = CorpusDecision(
        status=status,
        corrected_value=corrected_value.strip(),
        corrected_page=corrected_page,
        notes=notes.strip(),
        human_location_confirmed=human_confirmed,
        reviewed_at=reviewed_at,
    )
    return candidate, save_only or save_next, save_next


def main() -> None:
    st.set_page_config(
        page_title="NeuroTrace · 20 篇证据审核",
        page_icon="NT",
        layout="wide",
        initial_sidebar_state="auto",
    )
    inject_styles()
    try:
        config = load_review_config()
        items = cached_items(str(config.review_queue_path))
        papers, mapping = cached_corpus(config.zotero_collection_key, str(config.literature_index_path))
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        st.error(f"审核数据配置无效：{exc}")
        st.stop()
    except ZoteroUnavailableError as exc:
        st.error(str(exc))
        st.info("不要把 127.0.0.1:23119 当成网页打开。请启动 Zotero Desktop 后刷新本页。")
        st.stop()

    decisions = load_decisions(config.review_output_path)
    paper_titles = {paper_id: paper.title for paper_id, paper in mapping.items()}
    all_counts = _status_counts(items, decisions)
    core_review_ids = build_core_review_ids(items)

    with st.sidebar:
        st.markdown("## 审阅队列")
        st.caption(f"Collection {config.zotero_collection_key} · {len(mapping)} / 20 已映射")
        if st.button("同步 Zotero", use_container_width=True):
            cached_corpus.clear()
            st.rerun()
        selected_scope = st.selectbox(
            "审核范围",
            options=["core", "all"],
            format_func=lambda value: (
                f"核心证据集（{len(core_review_ids)} 条）" if value == "core" else f"全部旧候选（{len(items)} 条）"
            ),
            help="核心集包含每篇论文的主卡、实验单元，以及有图表论文中最有结果证据价值的一条图表。",
        )

    scope_items = items if selected_scope == "all" else [item for item in items if item.review_id in core_review_ids]
    counts = _status_counts(scope_items, decisions)
    reviewed_count = len(scope_items) - counts["pending"]

    st.markdown(
        "<header class='nt-review-head'><div>"
        "<h1>证据审核台</h1>"
        "<p>805 条都是机器候选，不是 Gold。默认核心范围只保留主卡、实验单元和每篇代表性结果图表。</p>"
        "</div><div class='nt-review-metrics'>"
        f"<div class='nt-review-metric'><strong>{len(papers)}</strong><span>Zotero 论文</span></div>"
        f"<div class='nt-review-metric'><strong>{reviewed_count}</strong><span>当前范围 / {len(scope_items)}</span></div>"
        f"<div class='nt-review-metric'><strong>{all_counts['approve']}</strong><span>Gold 通过</span></div>"
        "</div></header>",
        unsafe_allow_html=True,
    )

    unmapped = sorted({item.paper_id for item in items} - set(mapping))
    if unmapped:
        st.warning(f"有 {len(unmapped)} 个旧 paper_id 未匹配到 Zotero；这些记录暂时不可审核。")

    scope_paper_ids = {item.paper_id for item in scope_items}
    mapped_ids = sorted(
        (paper_id for paper_id in mapping if paper_id in scope_paper_ids),
        key=lambda paper_id: mapping[paper_id].title.casefold(),
    )
    with st.sidebar:
        selected_paper_id = st.selectbox(
            "论文",
            options=mapped_ids,
            format_func=lambda paper_id: mapping[paper_id].title,
        )
        available_types = [target_type for target_type in TYPE_LABELS if any(item.target_type == target_type for item in scope_items)]
        selected_type = st.selectbox(
            "记录类型",
            options=["all", *available_types],
            format_func=lambda value: "全部类型" if value == "all" else TYPE_LABELS[value],
        )
        selected_status = st.selectbox(
            "审核状态",
            options=["all", *STATUS_LABELS],
            format_func=lambda value: "全部状态" if value == "all" else STATUS_LABELS[value],
        )
        st.progress(reviewed_count / max(1, len(scope_items)), text=f"当前范围 {reviewed_count} / {len(scope_items)}")
        st.markdown(
            f"通过 {counts['approve']} · 修订 {counts['needs_fix']} · 拒绝 {counts['reject']} · 待审 {counts['pending']}"
        )
        if selected_scope == "core":
            st.caption("核心集：20 主卡 + 20 实验单元 + 19 代表性结果图表。需要全面清洗旧结构时再切换到 805 条。")

    visible = [item for item in scope_items if item.paper_id == selected_paper_id]
    if selected_type != "all":
        visible = [item for item in visible if item.target_type == selected_type]
    if selected_status != "all":
        visible = [
            item for item in visible
            if decisions.get(item.review_id, CorpusDecision()).status == selected_status
        ]
    if not visible:
        st.info("当前筛选条件下没有审核记录。请调整侧栏筛选。")
        st.stop()

    option_ids = [item.review_id for item in visible]
    selector_key, selector_index = prepare_review_selector(st.session_state, option_ids)
    selected_review_id = st.selectbox(
        "当前审核项",
        options=option_ids,
        index=selector_index,
        key=selector_key,
        format_func=lambda review_id: next(item.label for item in visible if item.review_id == review_id),
    )
    item = next(candidate for candidate in visible if candidate.review_id == selected_review_id)
    paper = mapping[item.paper_id]
    existing = decisions.get(item.review_id, CorpusDecision())

    st.markdown(f"<h2 class='nt-paper-title'>{_safe(paper.title)}</h2>", unsafe_allow_html=True)
    st.markdown(f"<p class='nt-paper-meta'>{_safe(_paper_meta(paper))}</p>", unsafe_allow_html=True)
    if not paper.metadata_complete:
        st.warning("该 Zotero 项是独立 PDF，缺少规范父文献元数据；可以审核页面，但导出引用前应补齐作者与年份。")

    left, right = st.columns([0.92, 1.28], gap="large")
    pages, page_issues = item.page_range
    preview_default = existing.corrected_page or item.primary_page or 1
    pdf_path = paper.pdf_path
    location = TextLocation("missing_pdf", "Zotero 未返回可用 PDF 路径。", preview_default, item.locator_text)
    total_pages = 0
    if pdf_path and pdf_path.is_file():
        total_pages = cached_page_count(str(pdf_path), _mtime(pdf_path))
        if preview_default > total_pages:
            location = TextLocation(
                "invalid_page", f"旧标签指向第 {preview_default} 页，但 PDF 只有 {total_pages} 页。",
                preview_default, item.locator_text,
            )
        else:
            location = cached_location(str(pdf_path), _mtime(pdf_path), preview_default, item.locator_text)

    with left:
        st.markdown("<section class='nt-review-item'><h2>候选记录</h2></section>", unsafe_allow_html=True)
        badge_status = existing.status
        badges = (
            f"<span class='nt-review-badge nt-review-badge--active'>{_safe(TYPE_LABELS.get(item.target_type, item.target_type))}</span>"
            f"<span class='nt-review-badge'>{_safe(item.priority)}</span>"
            f"<span class='nt-review-badge'>{_safe(STATUS_LABELS[badge_status])}</span>"
        )
        if page_issues:
            badges += "<span class='nt-review-badge nt-review-badge--warn'>旧页范围异常</span>"
        st.markdown(f"<div class='nt-review-badges'>{badges}</div>", unsafe_allow_html=True)
        st.markdown(QUESTION_LABELS.get(item.target_type, item.question))
        _render_spec(item)
        st.markdown(f"**旧来源追踪**　{item.source_trace or '—'}")
        for issue in page_issues:
            st.warning(issue)
        st.markdown(
            f"<div class='{_location_class(location)}'><strong>{_safe(_location_title(location))}</strong>"
            f"{_safe(location.message)}</div>",
            unsafe_allow_html=True,
        )

        candidate, submitted, go_next = _decision_from_form(item, existing)
        if submitted:
            # Automatic matching is only a locator aid. Gold approval always
            # requires the reviewer to confirm the source position explicitly.
            error = validate_decision(candidate, candidate.human_location_confirmed)
            if error:
                st.error(error)
            else:
                reviewed_at = "" if candidate.status == "pending" else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                candidate = replace(candidate, reviewed_at=reviewed_at)
                save_decision(config.review_output_path, item.review_id, candidate)
                decisions[item.review_id] = candidate
                if go_next:
                    next_id = _next_item(item, visible, decisions)
                    if next_id:
                        defer_review_selection(st.session_state, next_id)
                st.rerun()

        with st.expander("查看旧记录原始值"):
            st.code(json.dumps(dict(item.value), ensure_ascii=False, indent=2), language="json")
        if item.target_type == "main_card":
            card_path = main_card_path(config, item.paper_id)
            if card_path:
                with st.expander("查看旧论文主卡"):
                    st.markdown(card_path.read_text(encoding="utf-8"))

    with right:
        st.markdown("<section class='nt-proof-pane'><h2>原始 PDF 证据</h2></section>", unsafe_allow_html=True)
        if not pdf_path or not pdf_path.is_file():
            st.error("Zotero 返回的 PDF 路径不可用。请在 Zotero 中检查附件文件。")
        else:
            preview_page = st.number_input(
                "预览页码",
                min_value=1,
                max_value=max(1, total_pages),
                value=min(max(1, preview_default), max(1, total_pages)),
                step=1,
            )
            if int(preview_page) != location.page_number:
                location = cached_location(str(pdf_path), _mtime(pdf_path), int(preview_page), item.locator_text)
            zotero_url = f"zotero://open-pdf/library/items/{paper.attachment_key}?page={int(preview_page)}"
            st.link_button("在 Zotero 中打开此页", zotero_url, use_container_width=True)
            try:
                page_png = cached_page_png(str(pdf_path), _mtime(pdf_path), int(preview_page))
                annotated = annotate_page(page_png, location)
                if item.target_type == "figure_table":
                    item_type = str(item.value.get("item_type", "figure"))
                    screenshot = crop_figure_or_table(page_png, location, item_type)
                    st.markdown(
                        "<p class='nt-proof-caption'>图表候选截图由当前 Zotero PDF 重新生成；蓝线表示自动定位到的标题位置。</p>",
                        unsafe_allow_html=True,
                    )
                    _render_png_preview(
                        screenshot,
                        f"{item.label} · 原始 PDF 第 {int(preview_page)} 页",
                        f"{paper.title} 第 {int(preview_page)} 页图表候选截图",
                    )
                    st.download_button(
                        "下载图表截图",
                        data=screenshot,
                        file_name=f"{item.paper_id}_{item.target_id}_p{int(preview_page)}.png",
                        mime="image/png",
                        use_container_width=True,
                    )
                    with st.expander("查看完整 PDF 页面"):
                        _render_png_preview(
                            annotated,
                            f"原始 PDF 第 {int(preview_page)} / {total_pages} 页",
                            f"{paper.title} 第 {int(preview_page)} 页完整预览",
                        )
                else:
                    st.markdown(
                        "<p class='nt-proof-caption'>页面直接从 Zotero PDF 渲染；蓝线表示自动定位到的候选文字。</p>",
                        unsafe_allow_html=True,
                    )
                    _render_png_preview(
                        annotated,
                        f"原始 PDF 第 {int(preview_page)} / {total_pages} 页",
                        f"{paper.title} 第 {int(preview_page)} 页证据预览",
                    )
                    st.download_button(
                        "下载页面截图",
                        data=annotated,
                        file_name=f"{item.paper_id}_{item.target_id}_p{int(preview_page)}.png",
                        mime="image/png",
                        use_container_width=True,
                    )
            except (RuntimeError, ValueError) as exc:
                st.error(str(exc))

    current_decisions = load_decisions(config.review_output_path)
    st.markdown("<footer class='nt-review-footer'><strong>NeuroTrace Corpus Review</strong><span>Zotero 只读 · 原 PDF 核验 · 审核结果独立保存</span></footer>", unsafe_allow_html=True)
    export_left, export_right = st.columns(2)
    export_left.download_button(
        "导出审核 JSON",
        export_review_json(items, current_decisions, paper_titles),
        "neurotrace_corpus_reviews.json",
        "application/json",
        use_container_width=True,
    )
    export_right.download_button(
        "导出审核 CSV",
        export_review_csv(items, current_decisions, paper_titles),
        "neurotrace_corpus_reviews.csv",
        "text/csv",
        use_container_width=True,
    )


if __name__ == "__main__":
    main()

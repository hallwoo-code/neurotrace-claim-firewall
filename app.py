from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, List

import streamlit as st

from src.claim_audit import GOLDEN_CLAIM, SAFE_REWRITE, SAFE_REWRITE_ZH, audit_claim
from src.evidence_store import load_evidence
from src.exporter import build_evidence_pack, export_csv, export_json, export_markdown
from src.models import EvidenceRecord, ReviewDecision
from src.review_store import eligible_evidence, normalize_reviews, utc_timestamp
from src.source_integrity import configured_pdf_dir, verify_sources


ROOT = Path(__file__).resolve().parent
ROLE_LABELS = {
    "conditional_support": "有条件支持",
    "direct_qualifier_or_counterevidence": "直接限定 / 反例",
    "boundary_evidence": "边界证据",
}
DIRECTNESS_LABELS = {
    "direct_but_conditional": "直接检验，但有条件",
    "direct_test": "直接检验",
    "not_a_direct_test_of_supportive_context": "非支持性语境的直接检验",
}
STATUS_LABELS = {
    "pending": "pending · 待审核",
    "approve": "approve · 通过",
    "needs_fix": "needs_fix · 需修订",
    "reject": "reject · 拒绝",
}
ROLE_ORDER = {
    "conditional_support": 0,
    "direct_qualifier_or_counterevidence": 1,
    "boundary_evidence": 2,
}


def inject_styles() -> None:
    tokens = (ROOT / "tokens.css").read_text(encoding="utf-8")
    app_css = (ROOT / "app.css").read_text(encoding="utf-8").replace('@import url("tokens.css");', "")
    st.markdown(f"<style>{tokens}\n{app_css}</style>", unsafe_allow_html=True)


def initial_reviews(records: List[EvidenceRecord]) -> Dict[str, Dict[str, str]]:
    return {
        record.paper_id: {"status": "pending", "corrected_value": "", "reviewed_at": ""}
        for record in records
    }


def initialize_state(records: List[EvidenceRecord]) -> None:
    st.session_state.setdefault("claim_input", GOLDEN_CLAIM)
    st.session_state.setdefault("compiled_claim", "")
    st.session_state.setdefault("reviews", initial_reviews(records))


def reset_demo(records: List[EvidenceRecord]) -> None:
    for key in list(st.session_state):
        if key.startswith("review_status_") or key.startswith("correction_"):
            del st.session_state[key]
    st.session_state.claim_input = GOLDEN_CLAIM
    st.session_state.compiled_claim = ""
    st.session_state.reviews = initial_reviews(records)


def render_dimensions(dimensions: Dict[str, str]) -> None:
    rows = "".join(
        f"<div class='nt-dimension'><dt>{html.escape(key)}</dt><dd>{html.escape(value)}</dd></div>"
        for key, value in dimensions.items()
    )
    st.markdown(f"<dl class='nt-dimensions'>{rows}</dl>", unsafe_allow_html=True)


def render_verdict(claim: str) -> None:
    result = audit_claim(claim)
    risks = "".join(
        "<li class='nt-risk'>"
        f"<span class='nt-risk-index'>{index:02d}</span>"
        f"<span><strong>{html.escape(risk.title)}</strong><br>{html.escape(risk.explanation)}</span>"
        "</li>"
        for index, risk in enumerate(result.risks, 1)
    )
    st.markdown(
        "<section class='nt-verdict'>"
        f"<h2 class='nt-verdict-title'>{result.verdict} / {result.verdict_zh}</h2>"
        f"<p>{html.escape(result.explanation)}</p>"
        f"<ul class='nt-risk-list'>{risks}</ul>"
        "</section>",
        unsafe_allow_html=True,
    )
    st.markdown("<h2 class='nt-section-title'>论断维度</h2>", unsafe_allow_html=True)
    st.markdown(
        "<p class='nt-section-copy'>把一句流畅结论展开为可核验的条件集合；未写出的范围同样是风险。</p>",
        unsafe_allow_html=True,
    )
    render_dimensions(result.dimensions)


def update_review(record: EvidenceRecord, status: str, corrected_value: str) -> ReviewDecision:
    previous = st.session_state.reviews.get(record.paper_id, {})
    changed = status != previous.get("status") or corrected_value != previous.get("corrected_value")
    reviewed_at = previous.get("reviewed_at", "")
    if changed:
        reviewed_at = "" if status == "pending" else utc_timestamp()
    raw = {"status": status, "corrected_value": corrected_value, "reviewed_at": reviewed_at}
    st.session_state.reviews[record.paper_id] = raw
    return ReviewDecision(**raw)


def render_evidence_card(record: EvidenceRecord, integrity: Dict[str, object]) -> ReviewDecision:
    role = ROLE_LABELS[record.evidence_role]
    directness = DIRECTNESS_LABELS[record.directness]
    with st.expander(f"{record.citation} · {role}", expanded=record.evidence_role != "boundary_evidence"):
        badge_class = "nt-badge--boundary" if record.evidence_role == "boundary_evidence" else "nt-badge--direct"
        st.markdown(
            "<div class='nt-evidence-head'>"
            f"<span class='nt-badge {badge_class}'>{html.escape(role)}</span>"
            f"<span class='nt-badge'>{html.escape(directness)}</span>"
            f"<span class='nt-badge'>{html.escape(integrity['status'])} · SHA256</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='nt-trace'>"
            f"<p><strong>研究范围</strong><br>{html.escape(record.scope)}</p>"
            f"<p><strong>实验条件</strong><br>{html.escape(record.conditions)}</p>"
            f"<p><strong>结果摘要</strong><br>{html.escape(record.finding)}</p>"
            f"<p><strong>引用边界</strong><br>{html.escape(record.claim_boundary)}</p>"
            f"<p><strong>ERP 时间窗</strong><br>{html.escape(' · '.join(record.erp_windows))}</p>"
            f"<p><strong>效应方向</strong><br>{html.escape(record.effect_direction)}</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"**来源追踪**　PDF 页码：{', '.join(map(str, record.source_pages))}　·　"
            f"图号：{', '.join(record.related_figures)}"
        )
        st.markdown(
            f"<p class='nt-path'>本地只读 PDF：{html.escape(record.pdf_file_name)}<br>"
            f"SHA256: {html.escape(str(integrity['expected_sha256']))}</p>",
            unsafe_allow_html=True,
        )

        stored = st.session_state.reviews[record.paper_id]
        status_key = f"review_status_{record.paper_id}"
        if status_key not in st.session_state:
            st.session_state[status_key] = stored["status"]
        status = st.selectbox(
            "人工审核状态",
            options=list(STATUS_LABELS),
            format_func=STATUS_LABELS.get,
            key=status_key,
        )
        correction_key = f"correction_{record.paper_id}"
        if correction_key not in st.session_state:
            st.session_state[correction_key] = stored["corrected_value"]
        corrected = ""
        if status == "needs_fix":
            corrected = st.text_area(
                "修订后的 finding（必填）",
                key=correction_key,
                placeholder="写入经人工核验后的完整 finding；该值会替换导出包中的 finding。",
            )
            if not corrected.strip():
                st.markdown(
                    "<p class='nt-helper nt-helper--error'>该记录尚未通过门控：needs_fix 必须填写修订值。</p>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<p class='nt-helper'>修订值已填写；提交后会替换导出包中的 finding。</p>",
                    unsafe_allow_html=True,
                )
        else:
            corrected = st.session_state.get(correction_key, "")

        review = update_review(record, status, corrected)
        eligible = review.status == "approve" or (review.status == "needs_fix" and bool(review.corrected_value.strip()))
        gate_class = "nt-gate nt-gate--eligible" if eligible else "nt-gate"
        gate_text = "可进入 Evidence Pack" if eligible else "暂不进入 Evidence Pack"
        st.markdown(f"<p class='{gate_class}'>{gate_text}</p>", unsafe_allow_html=True)
        if record.evidence_role == "boundary_evidence":
            st.markdown(
                "<p class='nt-boundary-note'>角色锁定：即使 approve，Baiocco 仍是 boundary_evidence，不会升级为直接支持。</p>",
                unsafe_allow_html=True,
            )
        return review


def render_safe_rewrite() -> None:
    st.markdown(
        "<section class='nt-safe'>"
        "<h2>经审核可写入的安全论断</h2>"
        f"<blockquote>{html.escape(SAFE_REWRITE)}</blockquote>"
        f"<p>{html.escape(SAFE_REWRITE_ZH)}</p>"
        "<div class='nt-delta'>"
        "<div><strong>原论断</strong>跨类型、稳定、单向</div>"
        "<div><strong>安全论断</strong>按语境相关性、常规性、任务与阶段分层</div>"
        "<div><strong>方向变化</strong>允许无效应、早期阻碍与后期促进并存</div>"
        "</div>"
        "</section>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="NeuroTrace · Claim Audit",
        page_icon="NT",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_styles()
    records = sorted(load_evidence(), key=lambda item: ROLE_ORDER[item.evidence_role])
    initialize_state(records)
    pdf_dir = configured_pdf_dir()
    integrity = verify_sources(records, pdf_dir)

    st.markdown(
        "<header class='nt-topbar'>"
        "<div><h1 class='nt-wordmark'>NeuroTrace</h1>"
        "<p class='nt-subtitle'>ERP/EEG 科研论断防火墙——在论断进入论文前，编译可核验的证据边界。</p></div>"
        "<div class='nt-metrics'>"
        "<div class='nt-metric'><strong>3</strong><span>篇锁定论文</span></div>"
        "<div class='nt-metric'><strong>1</strong><span>条黄金论断</span></div>"
        "<div class='nt-metric'><strong>HITL</strong><span>人工审核门控</span></div>"
        "</div></header>",
        unsafe_allow_html=True,
    )

    st.markdown("<p class='nt-kicker'>Claim Audit / 论断审计</p>", unsafe_allow_html=True)
    st.markdown("<h2 class='nt-section-title'>先审计，再写入论文。</h2>", unsafe_allow_html=True)
    st.markdown(
        "<p class='nt-section-copy'>页面锁定三篇黄金论文；不调用在线模型，不扩展到开放问答。</p>",
        unsafe_allow_html=True,
    )
    st.text_area("候选论断", key="claim_input", height=118)
    st.markdown(
        "<p class='nt-helper'>预置黄金论断；修改后需重新点击“编译证据边界”。</p>",
        unsafe_allow_html=True,
    )
    compile_col, reset_col = st.columns([3, 1])
    with compile_col:
        if st.button("编译证据边界", type="primary", use_container_width=True):
            if st.session_state.claim_input.strip():
                st.session_state.compiled_claim = st.session_state.claim_input.strip()
            else:
                st.error("候选论断为空。请恢复演示或输入一条论断后再编译。")
    with reset_col:
        st.button(
            "恢复演示",
            use_container_width=True,
            on_click=reset_demo,
            args=(records,),
        )

    compiled_claim = st.session_state.compiled_claim
    if not compiled_claim:
        st.markdown(
            "<p class='nt-foot'>等待编译 · 当前证据与审核状态尚未进入 Evidence Pack。</p>",
            unsafe_allow_html=True,
        )
        return
    if compiled_claim != st.session_state.claim_input.strip():
        st.warning("输入内容已改变；当前结果仍对应上一次编译的论断。再次点击“编译证据边界”以更新。")

    render_verdict(compiled_claim)
    st.markdown("<h2 class='nt-section-title'>三篇论文，各守一条边界</h2>", unsafe_allow_html=True)
    st.markdown(
        "<p class='nt-section-copy'>展开记录核对对象、条件、ERP 时间窗、页码与图号，再决定它能否进入导出包。</p>",
        unsafe_allow_html=True,
    )

    current_reviews: Dict[str, ReviewDecision] = {}
    for record in records:
        current_reviews[record.paper_id] = render_evidence_card(record, integrity[record.paper_id])

    eligible = eligible_evidence(records, current_reviews)
    touched = any(review.status != "pending" for review in current_reviews.values())
    if touched and eligible:
        render_safe_rewrite()

    st.markdown("<h2 class='nt-section-title'>Evidence Pack</h2>", unsafe_allow_html=True)
    st.markdown(
        f"<p class='nt-section-copy'>当前 {len(eligible)} / 3 条证据通过人工门控。pending、reject 和未填写修订值的 needs_fix 均被排除。</p>",
        unsafe_allow_html=True,
    )
    pack = build_evidence_pack(
        compiled_claim,
        audit_claim(compiled_claim),
        SAFE_REWRITE,
        records,
        current_reviews,
        integrity,
    )
    md_col, json_col, csv_col = st.columns(3)
    disabled = not eligible
    with md_col:
        st.download_button(
            "下载 Markdown", export_markdown(pack), "neurotrace_evidence_pack.md",
            "text/markdown", disabled=disabled, use_container_width=True,
        )
    with json_col:
        st.download_button(
            "下载 JSON", export_json(pack), "neurotrace_evidence_pack.json",
            "application/json", disabled=disabled, use_container_width=True,
        )
    with csv_col:
        st.download_button(
            "下载 CSV", export_csv(pack), "neurotrace_evidence_pack.csv",
            "text/csv", disabled=disabled, use_container_width=True,
        )
    st.markdown(
        "<footer class='nt-foot'>NeuroTrace · 仅覆盖 3 篇黄金论文与 1 条演示论断 · 不是通用 RAG · 源 PDF 只读</footer>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

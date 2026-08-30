from __future__ import annotations

import re
from typing import Dict, List

from .models import AuditResult, AuditRisk


GOLDEN_CLAIM = (
    "Supportive contexts consistently facilitate metaphor comprehension "
    "by reducing N400 amplitudes across metaphor types."
)

GOLDEN_CLAIM_ZH = "支持性语境会跨隐喻类型稳定促进隐喻理解，并体现为 N400 波幅降低。"

SAFE_REWRITE = (
    "Context can modulate metaphor processing, but its direction and ERP signature depend on "
    "context relevance, metaphor type and conventionality, task demands, stimulus emotionality, "
    "and processing stage. In L2 novel metaphors, supportive context may increase early "
    "N400-related difficulty while facilitating later semantic integration, whereas conventional "
    "metaphors may show no reliable context effect."
)

SAFE_REWRITE_ZH = (
    "语境能够调节隐喻加工，但作用方向及 ERP 表征取决于语境相关性、隐喻类型与常规性、"
    "任务要求、刺激情绪性和加工阶段。对 L2 新颖隐喻，支持性语境可能增加早期 N400 相关"
    "加工难度，却促进后期语义整合；常规隐喻则可能不呈现可靠的语境效应。"
)


def _contains(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def decompose_claim(claim: str) -> Dict[str, str]:
    clean = " ".join(claim.split())
    return {
        "population": "未限定 / unspecified",
        "context": "支持性语境 / supportive contexts" if _contains(clean, r"supportive|支持性") else "未明确",
        "metaphor_type": "跨所有隐喻类型 / across metaphor types" if _contains(clean, r"across metaphor types|跨隐喻类型") else "未明确",
        "task": "未限定 / unspecified",
        "ERP_component": "N400" if _contains(clean, r"N\s*400") else "未明确",
        "processing_stage": "未区分早期与晚期 / collapsed" if _contains(clean, r"N\s*400|促进|facilitat") else "未明确",
        "effect_direction": "N400 降低 → 促进 / reduced N400 → facilitation" if _contains(clean, r"reducing|降低") else "未明确",
    }


def audit_claim(claim: str) -> AuditResult:
    clean = " ".join(claim.split())
    if not clean:
        raise ValueError("Candidate claim cannot be empty.")

    risks: List[AuditRisk] = []
    if _contains(clean, r"consistently|always|稳定|始终|一致"):
        risks.append(AuditRisk(
            "absolute_language", "绝对化表述", "“consistently”把条件性发现写成稳定规律。", "consistently",
        ))
    if _contains(clean, r"across metaphor types|all metaphor|跨隐喻类型|所有隐喻"):
        risks.append(AuditRisk(
            "cross_type_generalization", "跨类型泛化", "科学隐喻、L2 常规隐喻与新颖隐喻呈现不同模式。", "across metaphor types",
        ))
    if _contains(clean, r"reducing\s+N\s*400|N\s*400.{0,12}(降低|减小)|降低.{0,12}N\s*400"):
        risks.append(AuditRisk(
            "n400_direction", "N400 方向错误", "Yao 的 L2 新颖隐喻在支持性语境下早期 N400 更大，并非稳定降低。", "reducing N400",
        ))
    if _contains(clean, r"N\s*400|促进|facilitat"):
        risks.append(AuditRisk(
            "processing_stage_omission", "加工阶段遗漏", "早期词汇通达受阻与后期整合促进不能压缩为单向促进。", "single-stage effect",
        ))
    risks.append(AuditRisk(
        "task_emotionality_boundary", "任务与情绪边界遗漏",
        "Baiocco 只能证明任务要求与刺激情绪性共同改变 ERP 模式，不能直接支持语境论断。",
        "unspecified task/emotionality", "medium",
    ))

    return AuditResult(
        verdict="Overgeneralized",
        verdict_zh="过度概括",
        dimensions=decompose_claim(clean),
        risks=risks,
        explanation=(
            "三篇锁定论文不支持跨对象、跨隐喻类型、跨任务与跨加工阶段的统一 N400 下降。"
            "Tang 仅提供条件性支持；Yao 直接限定该方向；Baiocco 仅提供任务/情绪边界。"
        ),
    )


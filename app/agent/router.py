"""Phan loai intent + trich entity. Thu luat REGEX truoc (0 goi LLM, ~60% cau
hoi thuong gap khop duoc - docs/06-agent-design.md muc 6.1), chi roi xuong
LLM (`route_intent` prompt) khi khong luat nao khop hoac do tin cay thap.

Bang alias chien dich/phan khuc o day PHAI khop voi bang trong
prompts/route_intent.yaml (cung mot nguon su that, viet hai lan de LLM va
luat regex luon dong thuan voi nhau).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.contracts import Intent
from app.llm.usage import UsageCounters
from app.prompts.loader import PromptLoader
from app.semantic.catalog import YamlCatalog

# Khop dung bang "anh xa" trong instructions cua prompts/route_intent.yaml.
CAMPAIGN_ALIASES: dict[str, str] = {
    "broker": "CMP-PTN-BRK01",
    "tiktok": "CMP-TT-001",
    "zalo": "CMP-ZL-RL1",
    "momo": "CMP-PTN-MOMO",
    "facebook": "CMP-FB-001",
    "fb": "CMP-FB-001",
    "google": "CMP-GG-001",
}

SEGMENT_IDS = (
    "high_risk", "champion", "repeat_standard", "high_potential",
    "app_gap", "dormant", "rejected_only", "never_activated",
)

_ACTION_VERBS_RE = re.compile(
    r"(nên|nen)\s|làm gì|lam gi|cắt|cat\b|tăng ngân sách|tang ngan sach|"
    r"nếu.*thì|neu.*thi|đề xuất|de xuat|khuyến nghị|khuyen nghi"
)
_FUNNEL_RE = re.compile(r"phễu|pheu|nút thắt|nut that|rơi ở đâu|roi o dau")
_RISK_RE = re.compile(
    r"từ chối|tu choi|rủi ro|rui ro|gian lận|gian lan|vị trí không khớp|"
    r"vi tri khong khop|hệ điều hành|he dieu hanh|thiết bị|thiet bi"
)
_PERSONA_RE = re.compile(
    r"tập khách|tap khach|chân dung|chan dung|phân khúc|phan khuc|"
    r"khách vay lại|khach vay lai|nhóm tuổi|nhom tuoi|nhóm thu nhập|"
    r"nhom thu nhap|khách mới.*khách cũ|khach moi.*khach cu|cài app|cai app|"
    r"clv dự báo|clv du bao|khoảng tin cậy|khoang tin cay"
)
_OVERVIEW_RE = re.compile(r"chiến dịch nào|chien dich nao|romi tổng|romi tong|so sánh romi|so sanh romi")
_DATA_Q_RE = re.compile(
    r"^(có bao nhiêu|co bao nhieu|bao nhiêu|bao nhieu|tổng|tong|trung bình|"
    r"trung binh|có mấy|co may|top \d+%|top \d+ %)"
)
_DEEP_DIVE_RE = re.compile(r"chân dung nhóm|chan dung nhom|phân tích nhóm|phan tich nhom")
_DIAGNOSIS_VERB_RE = re.compile(
    r"vì sao|vi sao|tại sao|tai sao|phân rã|phan ra|lãi hay lỗ|lai hay lo|"
    r"phễu của|pheu cua|tỷ lệ tổn thất|ty le ton that|doanh thu của|"
    r"doanh thu cua|chi phí.*của|chi phi.*cua|tỷ lệ duyệt của|ty le duyet cua"
)


@dataclass(frozen=True, slots=True)
class RouteResult:
    intent: Intent
    entities: dict[str, list[str]]
    confidence: float
    used_llm: bool


def _extract_campaign_ids(question_lower: str) -> list[str]:
    found = []
    for alias, campaign_id in CAMPAIGN_ALIASES.items():
        if alias in question_lower and campaign_id not in found:
            found.append(campaign_id)
    return found


def _extract_segments(question_lower: str) -> list[str]:
    return [seg for seg in SEGMENT_IDS if seg in question_lower]


def _rule_based_route(question: str) -> RouteResult | None:
    q = question.lower()
    campaign_ids = _extract_campaign_ids(q)
    segments = _extract_segments(q)

    if _DEEP_DIVE_RE.search(q) and segments:
        return RouteResult(Intent.SEGMENT_DEEP_DIVE, {"segment": segments}, 0.9, False)

    if _ACTION_VERBS_RE.search(q) and (
        "clv" in q or "vòng đời" in q or "vong doi" in q or "ngân sách" in q or "ngan sach" in q
    ):
        return RouteResult(Intent.CLV_ACTIONS, {}, 0.85, False)

    if campaign_ids and _DIAGNOSIS_VERB_RE.search(q):
        return RouteResult(Intent.CAMPAIGN_DIAGNOSIS, {"campaign_id": campaign_ids}, 0.9, False)

    if _FUNNEL_RE.search(q) and not campaign_ids:
        return RouteResult(Intent.FUNNEL_ANALYSIS, {}, 0.85, False)

    if _RISK_RE.search(q):
        return RouteResult(Intent.RISK_FRAUD, {}, 0.85, False)

    if _PERSONA_RE.search(q):
        return RouteResult(Intent.CUSTOMER_PERSONA, {}, 0.8, False)

    if _OVERVIEW_RE.search(q):
        return RouteResult(Intent.CAMPAIGN_OVERVIEW, {}, 0.85, False)

    if campaign_ids:
        return RouteResult(Intent.CAMPAIGN_DIAGNOSIS, {"campaign_id": campaign_ids}, 0.75, False)

    if _DATA_Q_RE.search(q):
        return RouteResult(Intent.DATA_QUESTION, {}, 0.8, False)

    return None


_OUT_OF_SCOPE_HINTS = re.compile(
    r"thời tiết|thoi tiet|bóng đá|bong da|nấu ăn|nau an|chính trị|chinh tri"
)


class Router:
    """Trien khai buoc ROUTE cua may trang thai (docs/06 muc 6.1)."""

    def __init__(self, catalog: YamlCatalog, prompts: PromptLoader) -> None:
        self.catalog = catalog
        self.prompts = prompts

    async def route(
        self, llm_client: object, question: str, usage: UsageCounters,
        confidence_threshold: float = 0.6,
    ) -> RouteResult:
        if _OUT_OF_SCOPE_HINTS.search(question.lower()):
            return RouteResult(Intent.OUT_OF_SCOPE, {}, 0.95, False)

        rule_result = _rule_based_route(question)
        if rule_result is not None and rule_result.confidence >= confidence_threshold:
            return rule_result

        return await self._route_with_llm(llm_client, question, usage)

    async def _route_with_llm(
        self, llm_client: object, question: str, usage: UsageCounters,
    ) -> RouteResult:
        rendered = self.prompts.render(
            "route_intent", question=question,
            campaign_ids=self.catalog.dimension("campaign_id", "application").allowed_values or (),
            segments=SEGMENT_IDS,
        )
        text = await llm_client.complete(  # type: ignore[attr-defined]
            rendered.messages, temperature=rendered.params.get("temperature", 0.0),
            max_tokens=rendered.params.get("max_tokens", 250), response_format="json",
        )
        usage.add(tokens_in=0, tokens_out=0)  # da dem trong client; giu de doi xung API

        try:
            parsed = json.loads(text)
            intent = Intent(parsed["intent"])
            entities = {k: list(v) for k, v in (parsed.get("entities") or {}).items() if v}
            confidence = float(parsed.get("confidence", 0.5))
        except (json.JSONDecodeError, KeyError, ValueError):
            return RouteResult(Intent.FREEFORM, {}, 0.3, True)

        return RouteResult(intent, entities, confidence, True)


__all__ = ["Router", "RouteResult", "CAMPAIGN_ALIASES", "SEGMENT_IDS"]

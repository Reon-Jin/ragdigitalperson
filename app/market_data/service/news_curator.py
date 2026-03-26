from __future__ import annotations

import re
from datetime import datetime, timezone

from app.market_data.schemas.news import MarketEvent


class MarketNewsCurator:
    _THEME_KEYWORDS = {
        "政策监管": ("证监会", "国务院", "发改委", "央行", "降准", "降息", "监管", "政策", "会议", "国常会"),
        "业绩财报": ("业绩", "财报", "预增", "预亏", "快报", "利润", "营收", "分红", "回购"),
        "行业催化": ("涨价", "中标", "订单", "合作", "量产", "扩产", "突破", "新品", "招标"),
        "资金风格": ("北向", "南向", "主力", "净流入", "净流出", "两融", "成交额", "资金"),
        "风险扰动": ("减持", "问询", "处罚", "风险", "违约", "诉讼", "退市", "暴跌", "下调"),
        "宏观外部": ("美联储", "非农", "CPI", "PPI", "原油", "关税", "地缘", "汇率"),
    }
    _TRADING_IMPACT_KEYWORDS = (
        "超预期",
        "不及预期",
        "涨停",
        "跌停",
        "大涨",
        "大跌",
        "净流入",
        "净流出",
        "创历史新高",
        "创阶段新低",
        "停牌",
        "复牌",
        "回购",
        "分红",
        "业绩",
        "政策",
        "监管",
        "订单",
        "中标",
        "减持",
        "并购",
        "重组",
    )
    _LOW_VALUE_PATTERNS = (
        "placeholder",
        "模拟",
        "相关事件",
        "体育",
        "娱乐",
        "明星",
        "直播",
        "电竞",
        "彩票开奖",
    )
    _HIGH_CREDIBILITY_SOURCES = {
        "财联社": 1.0,
        "中国证券报": 0.9,
        "证券时报": 0.9,
        "证券日报": 0.8,
        "上海证券报": 0.85,
        "上证报": 0.85,
        "证监会": 1.2,
        "国务院": 1.2,
        "央行": 1.1,
        "东方财富": 0.55,
    }

    def curate(self, events: list[MarketEvent], *, limit: int = 4, focus_symbol: str | None = None) -> list[MarketEvent]:
        unique: dict[str, MarketEvent] = {}
        for item in events:
            normalized_title = self._normalize_title(item.title)
            if not normalized_title:
                continue
            scored = item.model_copy(update=self._decorate(item, focus_symbol=focus_symbol))
            if (scored.importance_score or 0) < 1.5:
                continue
            current = unique.get(normalized_title)
            if current is None or (scored.importance_score or 0) > (current.importance_score or 0):
                unique[normalized_title] = scored
        ranked = sorted(
            unique.values(),
            key=lambda item: ((item.importance_score or 0.0), self._sort_timestamp(item.publish_time)),
            reverse=True,
        )
        return ranked[:limit]

    def _decorate(self, event: MarketEvent, *, focus_symbol: str | None = None) -> dict[str, object]:
        title = str(event.title or "")
        summary = str(event.summary or "")
        source = str(event.source or "")
        body = f"{title} {summary}"
        theme = "市场动态"
        score = 0.8
        reason_parts: list[str] = []

        for label, keywords in self._THEME_KEYWORDS.items():
            hits = [keyword for keyword in keywords if keyword in body]
            if hits:
                theme = label
                score += 1.5 + min(0.5, len(hits) * 0.15)
                reason_parts.append(f"命中{label}关键词")
                break

        impact_hits = [keyword for keyword in self._TRADING_IMPACT_KEYWORDS if keyword in body]
        if impact_hits:
            score += min(1.6, 0.35 * len(impact_hits))
            reason_parts.append("直接影响交易预期")

        source_bonus = self._source_bonus(source)
        if source_bonus > 0:
            score += source_bonus
            reason_parts.append("信源可信度较高")

        if focus_symbol and focus_symbol in (event.related_symbols or []):
            score += 2.1
            reason_parts.append("直接关联当前个股")
        elif event.related_symbols:
            score += min(1.0, 0.35 * len(event.related_symbols))
            reason_parts.append("关联到具体证券")

        publish_time = self._parse_time(event.publish_time)
        if publish_time is not None:
            hours = max((datetime.now(timezone.utc) - publish_time).total_seconds() / 3600, 0.0)
            if hours <= 1:
                score += 2.0
                reason_parts.append("一小时内新鲜事件")
            elif hours <= 3:
                score += 1.5
                reason_parts.append("三小时内事件")
            elif hours <= 12:
                score += 0.8
                reason_parts.append("半日内仍具参考性")
            elif hours > 48:
                score -= 1.0

        if any(keyword in body for keyword in self._LOW_VALUE_PATTERNS):
            score -= 2.4
            reason_parts.append("疑似低价值内容")

        cleaned_summary = self._clean_summary(summary or title)
        action_hint = self._build_action_hint(theme, score)
        reason = "；".join(reason_parts[:3]) or "由 Agent 按时效性、信源和交易影响筛选"
        return {
            "summary": cleaned_summary,
            "theme": theme,
            "importance_score": round(score, 2),
            "agent_reason": reason,
            "action_hint": action_hint,
        }

    def _build_action_hint(self, theme: str, score: float) -> str:
        if score >= 5.0:
            return "优先核对这条信息是否已经反映在指数、板块或主力资金流里。"
        if theme == "风险扰动":
            return "先确认是否属于持续性风险，再决定是否继续跟踪。"
        if theme == "业绩财报":
            return "把业绩兑现度和当前估值位置放在一起看。"
        if theme == "政策监管":
            return "重点看受益或受压制的行业范围，不要只盯单条标题。"
        return "可作为下一步追问、筛选候选或验证市场风格的线索。"

    def _source_bonus(self, source: str) -> float:
        normalized = str(source or "")
        for key, bonus in self._HIGH_CREDIBILITY_SOURCES.items():
            if key in normalized:
                return bonus
        return 0.0

    def _clean_summary(self, text: str) -> str:
        compact = re.sub(r"\s+", " ", str(text or "")).strip()
        return compact[:160]

    def _normalize_title(self, title: str | None) -> str:
        return re.sub(r"\s+", "", str(title or "")).strip(" -:：")

    def _sort_timestamp(self, value: str | None) -> float:
        parsed = self._parse_time(value)
        return parsed.timestamp() if parsed is not None else 0.0

    def _parse_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        text = str(value).strip().replace("/", "-")
        candidates = (text, text.replace(" ", "T"))
        for candidate in candidates:
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            now = datetime.now()
            if fmt in {"%H:%M:%S", "%H:%M"}:
                parsed = parsed.replace(year=now.year, month=now.month, day=now.day)
            if fmt == "%m-%d %H:%M":
                parsed = parsed.replace(year=now.year)
            return parsed.replace(tzinfo=timezone.utc)
        return None

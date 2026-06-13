"""Multi-factor stock screener: technical + news sentiment + industry trends."""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.monitor import fetch_quote, _calc_rsi, _calc_macd, _calc_ma

logger = logging.getLogger(__name__)

# ── Universes ─────────────────────────────────────────────────────────

HK_TOP = [
    "00700.HK", "09988.HK", "00941.HK", "00388.HK", "01299.HK",
    "00005.HK", "02318.HK", "00939.HK", "01398.HK", "03988.HK",
    "01810.HK", "02382.HK", "01093.HK", "02628.HK", "01109.HK",
    "06869.HK", "02015.HK", "09618.HK", "09888.HK", "02020.HK",
    "00175.HK", "02269.HK", "01211.HK", "09633.HK", "06160.HK",
    "09999.HK", "01024.HK", "03690.HK", "09961.HK", "00669.HK",
]

CSI300_TOP = [
    "600519.SH", "000858.SZ", "601318.SH", "000333.SZ", "600036.SH",
    "601166.SH", "000002.SZ", "600900.SH", "601012.SH", "600030.SH",
    "000001.SZ", "002415.SZ", "601398.SH", "600276.SH", "000651.SZ",
    "300750.SZ", "603259.SH", "000725.SZ", "002714.SZ", "601888.SH",
    "600809.SH", "000568.SZ", "002475.SZ", "300059.SZ", "601899.SH",
    "603288.SH", "000063.SZ", "002304.SZ", "600585.SH", "000895.SZ",
]

US_TOP = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM",
    "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC",
    "XOM", "NFLX", "ADBE", "CRM", "AMD", "INTC", "PYPL", "COST",
]

# ── Industry mapping ──────────────────────────────────────────────────

INDUSTRY_MAP: dict[str, str] = {
    "00700.HK": "互联网", "09988.HK": "互联网", "03690.HK": "互联网", "09618.HK": "互联网",
    "09999.HK": "互联网", "01024.HK": "互联网", "09888.HK": "互联网", "09961.HK": "互联网",
    "01398.HK": "银行", "00939.HK": "银行", "03988.HK": "银行", "00005.HK": "银行", "00001.HK": "银行",
    "02628.HK": "保险", "02318.HK": "保险", "01299.HK": "保险",
    "00388.HK": "金融科技", "01810.HK": "消费电子", "01211.HK": "新能源车",
    "02015.HK": "新能源车", "09633.HK": "新能源", "06869.HK": "光纤通信",
    "02382.HK": "光学", "00669.HK": "工具制造", "00175.HK": "汽车", "02269.HK": "医药",
    "01109.HK": "地产", "01093.HK": "医药", "02020.HK": "体育用品", "06160.HK": "医药",
    "600519.SH": "白酒", "000858.SZ": "白酒", "000568.SZ": "白酒", "600809.SH": "白酒",
    "601318.SH": "保险", "601166.SH": "银行", "600036.SH": "银行", "000001.SZ": "银行", "601398.SH": "银行",
    "000333.SZ": "家电", "000651.SZ": "家电", "000002.SZ": "地产",
    "600900.SH": "电力", "601012.SH": "光伏", "600030.SH": "券商", "601888.SH": "旅游",
    "002415.SZ": "安防", "600276.SH": "医药", "300750.SZ": "电池", "603259.SH": "医药",
    "000725.SZ": "面板", "002714.SZ": "养殖", "603288.SH": "调味品", "000063.SZ": "通信",
    "002304.SZ": "白酒", "300059.SZ": "券商", "601899.SH": "矿业", "000895.SZ": "食品",
    "AAPL": "消费电子", "MSFT": "软件", "GOOGL": "互联网", "AMZN": "互联网",
    "NVDA": "半导体", "META": "互联网", "TSLA": "新能源车", "JPM": "银行",
    "V": "金融科技", "JNJ": "医药", "WMT": "零售", "PG": "消费品",
}


@dataclass
class StockScore:
    symbol: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    industry: str = ""
    total_score: float = 0.0
    tech_score: float = 0.0
    news_score: float = 0.0
    industry_score: float = 0.0
    news_headlines: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    error: str = ""


# ── News sentiment ────────────────────────────────────────────────────

def _fetch_news(symbol: str, name: str) -> tuple[float, list[str]]:
    """Fetch recent news and compute sentiment score (0-20). Returns (score, headlines)."""
    try:
        from ddgs import DDGS

        query = f"{symbol} {name} 股票 最新消息" if any(c > "一" for c in name) else f"{symbol} {name} stock news today"
        headlines: list[str] = []
        bullish = 0
        bearish = 0
        total = 0

        with DDGS() as ddg:
            results = list(ddg.text(query, max_results=8))

        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            text = f"{title} {body}".lower()
            if not text.strip():
                continue
            headlines.append(title[:120])
            total += 1

            # Chinese sentiment keywords
            for kw in ["涨", "利好", "增长", "突破", "买入", "盈利", "看多", "超预期", "大涨", "飙升", "反弹", "新高", "回购", "分红"]:
                if kw in text:
                    bullish += 1
                    break
            for kw in ["跌", "利空", "下滑", "亏损", "卖出", "看空", "不及预期", "大跌", "暴跌", "风险", "减持", "处罚", "调查"]:
                if kw in text:
                    bearish += 1
                    break
            # English keywords
            for kw in ["surge", "rally", "beat", "upgrade", "bullish", "growth", "buy", "positive", "breakout", "record high"]:
                if kw in text:
                    bullish += 1
                    break
            for kw in ["plunge", "drop", "miss", "downgrade", "bearish", "decline", "sell", "negative", "risk", "warning"]:
                if kw in text:
                    bearish += 1
                    break

        if total == 0:
            return 10.0, headlines

        # Sentiment score: 0 (all bearish) to 20 (all bullish), neutral = 10
        ratio = bullish / max(total, 1)
        # Scale: ratio 0 → 3, ratio 0.5 → 10, ratio 1 → 17
        score = round(3 + ratio * 14, 1)
        return score, headlines[:5]
    except Exception as e:
        logger.debug("news fetch failed for %s: %s", symbol, e)
        return 10.0, []


# ── Industry scoring ──────────────────────────────────────────────────

def _calc_industry_scores(scores: list[StockScore]) -> dict[str, float]:
    """Calculate industry momentum based on average stock performance in each industry."""
    industries: dict[str, list[float]] = {}
    for s in scores:
        if not s.industry:
            continue
        industries.setdefault(s.industry, []).append(s.change_pct)

    industry_avg: dict[str, float] = {}
    for ind, changes in industries.items():
        if changes:
            industry_avg[ind] = round(sum(changes) / len(changes), 2)

    # Normalize to 0-20 scale
    if not industry_avg:
        return {}
    max_v = max(abs(v) for v in industry_avg.values()) or 1
    result = {}
    for ind, avg in industry_avg.items():
        # Map -max..+max → 3..17, with 0 → 10
        result[ind] = round(10 + (avg / max_v) * 7, 1)
    return result


# ── Main screening ────────────────────────────────────────────────────

def _score_stock(symbol: str) -> StockScore:
    """Score a single stock on technical factors."""
    s = StockScore(symbol=symbol, industry=INDUSTRY_MAP.get(symbol, ""))
    q = fetch_quote(symbol)
    if q.error:
        s.error = q.error
        return s

    s.name = q.name
    s.price = q.price
    s.change_pct = q.change_pct

    ind = q.indicators or {}
    ma = ind.get("ma", {}) or {}
    rsi = ind.get("rsi")
    macd = ind.get("macd", {}) or {}

    # Technical score (0-60)
    tech = 0
    if ma.get("ma5") and ma.get("ma20"):
        if ma["ma5"] > ma["ma20"]: tech += 12
        if ma.get("ma10") and ma["ma10"] > ma["ma20"]: tech += 6
        if ma.get("ma20") and ma.get("ma60") and ma["ma20"] > ma["ma60"]: tech += 6
        if s.price > ma["ma5"] and s.price > ma["ma20"]: tech += 6
    # Momentum
    if s.change_pct > 5: tech += 15
    elif s.change_pct > 3: tech += 12
    elif s.change_pct > 1: tech += 8
    elif s.change_pct > 0: tech += 5
    else: tech += max(0, 5 + int(s.change_pct))
    # RSI
    if rsi is not None:
        if 40 <= rsi <= 60: tech += 10
        elif rsi < 30: tech += 10
        elif 30 <= rsi <= 70: tech += 5
    else: tech += 5
    # MACD
    if macd.get("macd") is not None:
        if macd["macd"] > 0: tech += 5
        elif macd["macd"] > -0.3: tech += 3
    s.tech_score = min(60, tech)

    for sig in q.signals:
        s.signals.append(sig.get("message", ""))

    return s


def screen(universe: list[str], top_n: int = 10) -> list[StockScore]:
    """Screen stocks with technical + news + industry analysis."""
    # Phase 1: Technical scoring (parallel)
    tech_scores: list[StockScore] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_score_stock, sym): sym for sym in universe}
        for fut in as_completed(futures):
            s = fut.result()
            if not s.error:
                tech_scores.append(s)

    tech_scores.sort(key=lambda x: x.tech_score, reverse=True)
    # Keep top 15 for deeper analysis
    candidates = tech_scores[:15]

    # Phase 2: News sentiment (parallel)
    with ThreadPoolExecutor(max_workers=3) as pool:
        news_futures = {pool.submit(_fetch_news, s.symbol, s.name): s for s in candidates}
        for fut in as_completed(news_futures):
            s = news_futures[fut]
            s.news_score, s.news_headlines = fut.result()

    # Phase 3: Industry scoring
    industry_scores = _calc_industry_scores(candidates)
    for s in candidates:
        s.industry_score = industry_scores.get(s.industry, 10.0)

    # Phase 4: Composite score (technical 60% + news 25% + industry 15%)
    for s in candidates:
        s.total_score = round(s.tech_score * 0.6 + s.news_score * 1.25 + s.industry_score * 0.75, 1)

    candidates.sort(key=lambda x: x.total_score, reverse=True)
    return candidates[:top_n]


def get_universe(name: str) -> list[str]:
    name = name.lower()
    if name in ("hk", "港股", "hk_top"):
        return HK_TOP
    if name in ("csi300", "沪深300", "a股"):
        return CSI300_TOP
    if name in ("us", "美股", "us_top"):
        return US_TOP
    return []

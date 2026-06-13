"""Multi-factor quantitative stock screener — 7-factor model."""

from __future__ import annotations
import logging, math, os, re
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.monitor import fetch_quote

logger = logging.getLogger(__name__)

# ── Universes ─────────────────────────────────────────────────────────

HK_UNIVERSE = [
    "00700.HK", "09988.HK", "00941.HK", "00388.HK", "01299.HK",
    "00005.HK", "02318.HK", "00939.HK", "01398.HK", "03988.HK",
    "01810.HK", "02382.HK", "02628.HK", "06869.HK", "02015.HK",
    "09618.HK", "09888.HK", "02020.HK", "02269.HK", "01211.HK",
    "09633.HK", "06160.HK", "00175.HK", "01093.HK", "01109.HK",
    "01024.HK", "03690.HK", "09961.HK", "00669.HK", "09999.HK",
    "01928.HK", "00027.HK", "00883.HK", "02333.HK", "01818.HK",
    "01088.HK", "02688.HK", "00291.HK", "00288.HK", "00992.HK",
]

A_UNIVERSE = [
    "600519.SH", "000858.SZ", "601318.SH", "000333.SZ", "600036.SH",
    "601166.SH", "600900.SH", "601012.SH", "600030.SH", "000001.SZ",
    "002415.SZ", "601398.SH", "600276.SH", "000651.SZ", "300750.SZ",
    "603259.SH", "000725.SZ", "002714.SZ", "601888.SH", "600809.SH",
    "000568.SZ", "002475.SZ", "300059.SZ", "601899.SH", "603288.SH",
    "000063.SZ", "002304.SZ", "600585.SH", "000895.SZ", "601088.SH",
    "600031.SH", "000338.SZ", "002594.SZ", "601857.SH", "600050.SH",
    "000100.SZ", "002230.SZ", "600690.SH", "600104.SH", "000625.SZ",
]

# ── Industry Map ──────────────────────────────────────────────────────

INDUSTRY_MAP: dict[str, str] = {
    "00700.HK": "互联网", "09988.HK": "互联网", "03690.HK": "互联网", "09618.HK": "互联网",
    "09999.HK": "互联网", "01024.HK": "互联网", "09888.HK": "互联网", "09961.HK": "互联网",
    "01398.HK": "银行", "00939.HK": "银行", "03988.HK": "银行", "00005.HK": "银行",
    "02628.HK": "保险", "02318.HK": "保险", "01299.HK": "保险", "601318.SH": "保险",
    "601166.SH": "银行", "600036.SH": "银行", "000001.SZ": "银行", "601398.SH": "银行",
    "00388.HK": "金融科技", "01810.HK": "消费电子", "01211.HK": "新能源车",
    "02015.HK": "新能源车", "09633.HK": "新能源", "300750.SZ": "电池", "601012.SH": "光伏",
    "06869.HK": "光纤通信", "000063.SZ": "通信", "002415.SZ": "安防",
    "02382.HK": "光学", "000725.SZ": "面板", "002230.SZ": "AI",
    "00669.HK": "工具", "00175.HK": "汽车", "000625.SZ": "汽车", "002594.SZ": "新能源车",
    "02269.HK": "医药", "01093.HK": "医药", "600276.SH": "医药", "603259.SH": "医药", "06160.HK": "医药",
    "01109.HK": "地产", "000002.SZ": "地产", "02020.HK": "体育",
    "600519.SH": "白酒", "000858.SZ": "白酒", "000568.SZ": "白酒", "600809.SH": "白酒", "002304.SZ": "白酒",
    "000333.SZ": "家电", "000651.SZ": "家电", "600690.SH": "家电",
    "600900.SH": "电力", "601088.SH": "煤炭", "601899.SH": "矿业", "601857.SH": "石油",
    "600030.SH": "券商", "300059.SZ": "券商", "601888.SH": "旅游",
    "600585.SH": "水泥", "000895.SZ": "食品", "603288.SH": "调味品",
    "002714.SZ": "养殖", "600104.SH": "汽车", "600031.SH": "工程机械",
    "600050.SH": "电信", "000338.SZ": "动力", "000100.SZ": "面板",
    "01928.HK": "博彩", "00027.HK": "博彩", "00883.HK": "石油", "02333.HK": "汽车",
    "01818.HK": "黄金", "01088.HK": "煤炭", "02688.HK": "燃气", "00291.HK": "啤酒",
    "00288.HK": "食品", "00992.HK": "计算机",
}

# ── Factor weights (sum = 100%) ──────────────────────────────────────

WEIGHTS = {
    "market": 0.10,     # 市场因子
    "value": 0.15,      # 价值因子
    "momentum": 0.20,   # 动量因子
    "quality": 0.15,    # 质量因子
    "information": 0.15, # 信息因子
    "industry": 0.10,   # 行业因子
    "technical": 0.15,  # 技术因子
}


@dataclass
class FactorScores:
    market: float = 5.0
    value: float = 5.0
    momentum: float = 5.0
    quality: float = 5.0
    information: float = 5.0
    industry: float = 5.0
    technical: float = 5.0

    @property
    def total(self) -> float:
        return (
            self.market * WEIGHTS["market"]
            + self.value * WEIGHTS["value"]
            + self.momentum * WEIGHTS["momentum"]
            + self.quality * WEIGHTS["quality"]
            + self.information * WEIGHTS["information"]
            + self.industry * WEIGHTS["industry"]
            + self.technical * WEIGHTS["technical"]
        ) * 10  # scale to 0-100


@dataclass
class StockScore:
    symbol: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    industry: str = ""
    pe: float = 0.0
    pb: float = 0.0
    roe: float = 0.0
    market_cap: float = 0.0
    total_score: float = 0.0
    factors: FactorScores = field(default_factory=FactorScores)
    news_headlines: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    error: str = ""


# ── Index data ────────────────────────────────────────────────────────

def _fetch_index_closes(universe: str) -> list[float]:
    """Fetch benchmark index closes for market factor calculation."""
    symbol = "^HSI" if universe == "hk" else "000300.SS"
    # Try direct close data
    q = fetch_quote(symbol)
    if not q.error and q.indicators:
        # We need the raw closes; re-fetch via monitor internals
        pass
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        hist = t.history(period="3mo")
        if not hist.empty:
            return hist["Close"].tolist()
    except Exception:
        pass
    try:
        import requests
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                adj = result[0].get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
                return [float(v) for v in adj if v is not None]
    except Exception:
        pass
    return []


def _get_stock_returns(symbol: str) -> tuple[float, float, float, float, list[float], float, float, float]:
    """Fetch stock data and compute returns. Returns (r1d, r1w, r1m, r3m, closes, vol_ratio, max_dd_1m, beta_approx)."""
    q = fetch_quote(symbol)
    if q.error:
        return 0, 0, 0, 0, [], 0, 0, 0

    closes: list[float] = []
    # Try yfinance for raw closes
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        hist = t.history(period="3mo")
        if not hist.empty:
            closes = hist["Close"].tolist()
    except Exception:
        pass

    if not closes:
        try:
            import requests
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                result = data.get("chart", {}).get("result", [])
                if result:
                    adj = result[0].get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
                    closes = [float(v) for v in adj if v is not None]
        except Exception:
            pass

    if len(closes) < 5:
        return q.change_pct, q.change_pct, q.change_pct, q.change_pct, closes, 0, 0, 0

    price = closes[-1]
    r1d = round((price / closes[-2] - 1) * 100, 2) if len(closes) >= 2 else 0
    r1w = round((price / closes[-min(5, len(closes))] - 1) * 100, 2)
    r1m = round((price / closes[-min(20, len(closes))] - 1) * 100, 2)
    r3m = round((price / closes[0] - 1) * 100, 2)

    # Volume surge ratio (recent avg vol / older avg vol)
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="3mo")
        if not hist.empty and "Volume" in hist.columns:
            vols = hist["Volume"].tolist()
            recent_vol = sum(vols[-5:]) / 5 if len(vols) >= 5 else vols[-1]
            older_vol = sum(vols[-20:-5]) / 15 if len(vols) >= 20 else recent_vol
            vol_ratio = round(recent_vol / older_vol, 2) if older_vol > 0 else 1.0
        else:
            vol_ratio = 1.0
    except Exception:
        vol_ratio = 1.0

    # Max drawdown (1 month)
    m1_closes = closes[-20:] if len(closes) >= 20 else closes
    peak = m1_closes[0]
    max_dd = 0.0
    for c in m1_closes:
        if c > peak: peak = c
        dd = (peak - c) / peak
        if dd > max_dd: max_dd = dd
    max_dd = round(max_dd * 100, 1)

    # Beta approximation (correlation with market proxy = 1.0 for simplicity)
    # Use relative strength vs 52w range as proxy
    beta = 1.0

    return r1d, r1w, r1m, r3m, closes, vol_ratio, max_dd, beta


# ── Factor calculators ─────────────────────────────────────────────────

def _calc_market_factor(change_pct: float, index_change: float) -> float:
    """Market factor: stock's performance relative to market. Score 0-10."""
    if index_change == 0:
        return 5.0
    alpha = change_pct - index_change  # excess return vs market
    # Map alpha to 0-10: -2% → 2, 0% → 5, +3% → 8, +5% → 10
    if alpha > 5: return 10.0
    if alpha > 3: return 8.0 + (alpha - 3) * 1.0
    if alpha > 1: return 6.0 + (alpha - 1) * 1.0
    if alpha > 0: return 5.0 + alpha * 1.0
    if alpha > -1: return 5.0 + alpha
    if alpha > -3: return 3.0 + (alpha + 3) * 0.5
    return max(0.0, 2.0 + (alpha + 5) * 0.5)


def _calc_value_factor(price: float, closes: list[float], pe: float, pb: float) -> float:
    """Value factor: PE/PB valuation + price position. Score 0-10."""
    score = 5.0
    # PE: lower is better value (0-15: excellent, 15-30: fair, 30+: expensive)
    if 0 < pe < 10: score += 3
    elif 10 <= pe < 20: score += 2
    elif 20 <= pe < 30: score += 1
    elif pe >= 50: score -= 2
    # PB: lower is better (0-1: deep value, 1-3: fair, 3+: expensive)
    if 0 < pb < 1: score += 2
    elif 1 <= pb < 2: score += 1
    elif pb >= 5: score -= 1
    # Price position in range (cheaper end = better)
    if len(closes) >= 20:
        hi = max(closes)
        lo = min(closes)
        if hi > lo:
            position = (price - lo) / (hi - lo)
            if position < 0.2: score += 2
            elif position < 0.4: score += 1
            elif position > 0.85: score -= 1
    return max(0.0, min(10.0, score))


def _calc_momentum_factor(r1w: float, r1m: float, r3m: float) -> float:
    """Momentum factor: multi-timeframe returns. Score 0-10."""
    # r1w weight 30%, r1m weight 40%, r3m weight 30%
    composite = r1w * 0.3 + r1m * 0.4 + r3m * 0.3
    if composite > 20: return 10.0
    if composite > 10: return 7.0 + (composite - 10) * 0.3
    if composite > 5: return 5.0 + (composite - 5) * 0.4
    if composite > 0: return 5.0 + composite * 0.5  # was wrong: 5 + composite
    if composite > -5: return 5.0 + composite * 0.4
    if composite > -10: return 3.0 + (composite + 10) * 0.2
    return max(0.0, 2.0)


def _calc_quality_factor(max_dd: float, vol_ratio: float, closes: list[float], roe: float) -> float:
    """Quality factor: ROE + low drawdown + stable volume. Score 0-10."""
    score = 5.0
    # ROE: higher = better quality
    if roe > 20: score += 3
    elif roe > 15: score += 2
    elif roe > 10: score += 1
    elif 0 < roe < 5: score -= 1
    # Max DD: lower is better
    if max_dd < 3: score += 2
    elif max_dd < 5: score += 1
    elif max_dd > 20: score -= 2
    elif max_dd > 15: score -= 1
    # Volatility
    if len(closes) >= 20:
        returns = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
        if returns:
            avg_r = sum(returns) / len(returns)
            variance = sum((r - avg_r) ** 2 for r in returns) / len(returns)
            vol = math.sqrt(variance) * 100
            if vol < 1.5: score += 2
            elif vol < 2.5: score += 1
            elif vol > 4: score -= 2
            elif vol > 3: score -= 1
    # Volume stability
    if 0.8 < vol_ratio < 1.2: score += 1
    return max(0.0, min(10.0, score))


def _calc_technical_factor(closes: list[float], price: float) -> float:
    """Technical factor: MA/RSI/MACD composite. Score 0-10."""
    if len(closes) < 20:
        return 5.0
    score = 5.0

    # MA alignment
    ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else price
    ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else price
    ma20 = sum(closes[-20:]) / 20
    if price > ma5 > ma20: score += 2
    elif price > ma20: score += 1
    elif price < ma20: score -= 1

    # RSI
    period = 14
    if len(closes) >= period + 1:
        gains = losses = 0.0
        for i in range(-period, 0):
            d = closes[i] - closes[i - 1]
            if d > 0: gains += d
            else: losses -= d
        if losses > 0:
            rs = (gains / period) / (losses / period)
            rsi = 100.0 - 100.0 / (1.0 + rs)
            if 40 <= rsi <= 60: score += 1
            elif rsi < 30: score += 2
            elif rsi > 70: score -= 1

    # MACD
    if len(closes) >= 26:
        def ema(data, n):
            k = 2.0 / (n + 1)
            out = [sum(data[:n]) / n]
            for v in data[n:]: out.append(v * k + out[-1] * (1 - k))
            return out
        e12, e26 = ema(closes, 12), ema(closes, 26)
        m = min(len(e12), len(e26))
        dif = [e12[-m + i] - e26[-m + i] for i in range(m)]
        dea = ema(dif, 9) if len(dif) >= 9 else dif
        if dif[-1] > dea[-1] and dif[-1] > 0: score += 2
        elif dif[-1] > dea[-1]: score += 1
        elif dif[-1] < dea[-1]: score -= 1

    return max(0.0, min(10.0, score))


def _calc_info_factor(symbol: str, name: str) -> tuple[float, list[str]]:
    """Information factor: news sentiment analysis. Returns (score 0-10, headlines)."""
    try:
        from ddgs import DDGS
        query = f"{symbol} {name} 股票 最新消息"
        headlines: list[str] = []
        bullish = bearish = total = 0

        with DDGS() as ddg:
            results = list(ddg.text(query, max_results=6))

        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            text = f"{title} {body}"
            if not text.strip(): continue
            headlines.append(title[:120])
            total += 1
            pos = ["涨", "利好", "增长", "突破", "买入", "盈利", "看多", "超预期", "大涨", "飙升", "反弹", "新高", "回购", "分红", "surge", "rally", "beat", "upgrade", "bullish", "growth"]
            neg = ["跌", "利空", "下滑", "亏损", "卖出", "看空", "不及预期", "大跌", "暴跌", "风险", "减持", "处罚", "调查", "plunge", "drop", "miss", "downgrade", "bearish", "decline"]
            if any(kw in text for kw in pos): bullish += 1
            if any(kw in text for kw in neg): bearish += 1

        if total == 0:
            return 5.0, headlines
        sentiment = bullish / total
        score = round(2.0 + sentiment * 8.0, 1)  # 0% bearish → 2, 100% bullish → 10
        return score, headlines[:5]
    except Exception:
        return 5.0, []


def _calc_industry_factor(symbol: str, all_scores: list[dict]) -> float:
    """Industry factor: sector momentum vs other sectors. Score 0-10."""
    ind = INDUSTRY_MAP.get(symbol, "")
    if not ind:
        return 5.0

    # Collect all stocks in same industry
    same_ind = [s for s in all_scores if INDUSTRY_MAP.get(s["symbol"]) == ind]
    other_ind = [s for s in all_scores if INDUSTRY_MAP.get(s["symbol"]) != ind and INDUSTRY_MAP.get(s["symbol"])]

    if not same_ind or not other_ind:
        return 5.0

    ind_avg = sum(s["change_pct"] for s in same_ind) / len(same_ind)
    other_avg = sum(s["change_pct"] for s in other_ind) / len(other_ind) if other_ind else 0

    diff = ind_avg - other_avg
    if diff > 3: return 10.0
    if diff > 1.5: return 7.5 + (diff - 1.5) * 1.7
    if diff > 0: return 5.0 + diff * 1.67
    if diff > -1: return 5.0 + diff * 2.5
    if diff > -3: return 2.5 + (diff + 3) * 0.8
    return max(0.0, 2.0)


# ── Main screening ────────────────────────────────────────────────────

def _fetch_fundamentals(symbol: str) -> dict[str, float]:
    """Fetch PE, PB, ROE for a stock. Uses Tushare (A-shares) or yfinance (HK)."""
    result = {"pe": 0, "pb": 0, "roe": 0, "market_cap": 0}
    try:
        # A-shares: Tushare
        if symbol.endswith((".SZ", ".SH")):
            import tushare as ts
            token = os.getenv("TUSHARE_TOKEN", "")
            if token:
                pro = ts.pro_api(token)
                code = symbol.replace(".SZ", "").replace(".SH", "") + (".SZ" if symbol.endswith(".SZ") else ".SH")
                df = pro.daily_basic(ts_code=code, fields="pe,pb,roe,total_mv")
                if not df.empty:
                    row = df.iloc[0]
                    result["pe"] = float(row.get("pe", 0) or 0)
                    result["pb"] = float(row.get("pb", 0) or 0)
                    result["roe"] = float(row.get("roe", 0) or 0)
                    result["market_cap"] = float(row.get("total_mv", 0) or 0)
        # HK stocks: yfinance
        elif symbol.endswith(".HK"):
            import yfinance as yf
            t = yf.Ticker(symbol)
            info = t.info or {}
            result["pe"] = float(info.get("trailingPE") or info.get("forwardPE") or 0)
            result["pb"] = float(info.get("priceToBook") or 0)
            result["roe"] = float(info.get("returnOnEquity") or 0) * 100 if info.get("returnOnEquity") else 0
            result["market_cap"] = float(info.get("marketCap") or 0)
    except Exception as e:
        logger.debug("fundamental fetch failed for %s: %s", symbol, e)
    return result


def _fetch_stock_data(symbol: str) -> dict | None:
    """Fetch all needed data for a single stock."""
    try:
        r1d, r1w, r1m, r3m, closes, vol_ratio, max_dd, beta = _get_stock_returns(symbol)
        if not closes:
            return None
        q = fetch_quote(symbol)
        if q.error and q.price == 0:
            return None
        return {
            "symbol": symbol,
            "name": q.name,
            "price": q.price,
            "change_pct": q.change_pct,
            "closes": closes,
            "r1w": r1w, "r1m": r1m, "r3m": r3m,
            "vol_ratio": vol_ratio,
            "max_dd": max_dd,
            "signals": [s.get("message", "") for s in q.signals],
        }
    except Exception as e:
        logger.debug("fetch failed for %s: %s", symbol, e)
        return None


def screen(universe: list[str], top_n: int = 8) -> list[StockScore]:
    """Screen stocks using 7-factor quantitative model."""
    # Phase 1: Fetch all stock data in parallel
    all_data: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_stock_data, sym): sym for sym in universe}
        for fut in as_completed(futures):
            d = fut.result()
            if d:
                all_data.append(d)

    if not all_data:
        return []

    # Phase 2: Compute all factors for each stock
    scores: list[StockScore] = []
    for d in all_data:
        s = StockScore(
            symbol=d["symbol"],
            name=d["name"],
            price=d["price"],
            change_pct=d["change_pct"],
            industry=INDUSTRY_MAP.get(d["symbol"], ""),
            signals=d["signals"],
        )

        closes = d["closes"]
        price = d["price"]

        # Market factor (compare to index — simplified: use change_pct as proxy)
        s.factors.market = _calc_market_factor(d["change_pct"], 0)

        # Value factor
        # Fetch fundamentals
        fund = _fetch_fundamentals(d["symbol"])
        s.pe = fund["pe"]
        s.pb = fund["pb"]
        s.roe = fund["roe"]
        s.market_cap = fund["market_cap"]

        s.factors.value = _calc_value_factor(price, closes, s.pe, s.pb)

        # Momentum factor
        s.factors.momentum = _calc_momentum_factor(d["r1w"], d["r1m"], d["r3m"])

        # Quality factor
        s.factors.quality = _calc_quality_factor(d["max_dd"], d["vol_ratio"], closes, s.roe)

        # Technical factor
        s.factors.technical = _calc_technical_factor(closes, price)

        # Store raw data for aggregate calculations
        s._raw = d  # type: ignore
        scores.append(s)

    # Phase 3: Industry factor (needs all scores)
    for s in scores:
        s.factors.industry = _calc_industry_factor(s.symbol, [
            {"symbol": x.symbol, "change_pct": x.change_pct} for x in scores
        ])

    # Phase 4: Information factor (news — parallel)
    with ThreadPoolExecutor(max_workers=4) as pool:
        info_futures = {pool.submit(_calc_info_factor, s.symbol, s.name): s for s in scores}
        for fut in as_completed(info_futures):
            s = info_futures[fut]
            s.factors.information, s.news_headlines = fut.result()

    # Phase 5: Compute total scores
    for s in scores:
        s.total_score = round(s.factors.total, 1)

    scores.sort(key=lambda x: x.total_score, reverse=True)
    return scores[:top_n]


def get_universe(name: str) -> list[str]:
    name = name.lower()
    if name in ("hk", "港股"):
        return HK_UNIVERSE
    if name in ("csi300", "沪深300", "a股"):
        return A_UNIVERSE
    return []

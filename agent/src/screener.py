"""Fast multi-factor screener — THS heat rank pool + weekend support."""

from __future__ import annotations
import logging, math, os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ── Heat rank pools via direct Eastmoney API ──────────────────────────

def _fetch_a_hot_pool(max_stocks: int = 50) -> list[str]:
    """Fetch top N A-shares from 东方财富 heat rank. Direct HTTP, no akshare."""
    try:
        import requests
        # Step 1: Get ranked stock codes
        r = requests.post(
            "https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
            json={"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38",
                  "marketType": "", "pageNo": 1, "pageSize": min(max_stocks, 100)},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://guba.eastmoney.com/"},
            timeout=15
        )
        data = r.json()
        if not data.get("data"):
            return []
        codes = [item["sc"] for item in data["data"]]

        # Step 2: Get price details
        marks = [("0." + c[2:] if "SZ" in c else "1." + c[2:]) for c in codes]
        r2 = requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={"ut": "f057cbcbce2a86e2866ab8877db1d059", "fltt": "2", "invt": "2",
                    "fields": "f12", "secids": ",".join(marks)},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        items = r2.json().get("data", {}).get("diff", [])
        symbols = []
        for item in items:
            code = item.get("f12", "")
            if code.startswith("6"):
                symbols.append(f"{code}.SH")
            else:
                symbols.append(f"{code}.SZ")
            if len(symbols) >= max_stocks:
                break
        return symbols
    except Exception as e:
        logger.warning("A hot rank failed: %s", e)
        return []


def _fetch_hk_hot_pool(max_stocks: int = 50) -> list[str]:
    """Fetch top N HK stocks from 东方财富 HK heat rank."""
    try:
        import requests
        r = requests.post(
            "https://emappdata.eastmoney.com/stockrank/getAllCurrHkUsList",
            json={"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38",
                  "marketType": "000003", "pageNo": 1, "pageSize": min(max_stocks, 100)},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://guba.eastmoney.com/"},
            timeout=15
        )
        data = r.json()
        if not data.get("data"):
            return []
        codes = [item["sc"] for item in data["data"]]

        marks = ["116." + c[3:] for c in codes]
        r2 = requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={"ut": "f057cbcbce2a86e2866ab8877db1d059", "fltt": "2", "invt": "2",
                    "fields": "f12", "secids": ",".join(marks)},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        items = r2.json().get("data", {}).get("diff", [])
        symbols = []
        for item in items:
            code = str(item.get("f12", "")).zfill(5)
            symbols.append(f"{code}.HK")
            if len(symbols) >= max_stocks:
                break
        return symbols
    except Exception as e:
        logger.warning("HK hot rank failed: %s", e)
        return []

# ── Factor config ─────────────────────────────────────────────────────

WEIGHTS = {"momentum": 0.25, "technical": 0.20, "volume": 0.10, "trend": 0.10,
           "catalyst": 0.10, "industry": 0.10, "news_sentiment": 0.10, "value": 0.05}

@dataclass
class FactorScores:
    momentum: float = 5.0; technical: float = 5.0; volume: float = 5.0
    trend: float = 5.0; catalyst: float = 5.0; industry: float = 5.0
    news_sentiment: float = 5.0; value: float = 5.0

    @property
    def total(self) -> float:
        return (self.momentum * 0.25 + self.technical * 0.20 + self.volume * 0.10
                + self.trend * 0.10 + self.catalyst * 0.10 + self.industry * 0.10
                + self.news_sentiment * 0.10 + self.value * 0.05) * 10

@dataclass
class StockScore:
    symbol: str; name: str = ""; price: float = 0.0; change_pct: float = 0.0
    pe: float = 0.0; pb: float = 0.0; roe: float = 0.0; market_cap: float = 0.0
    industry: str = ""; total_score: float = 0.0
    factors: FactorScores = field(default_factory=FactorScores)
    signals: list[str] = field(default_factory=list)

# ── Weekend helper ────────────────────────────────────────────────────

def _tushare_date() -> str:
    """Return last trading day for Tushare queries."""
    today = datetime.now()
    if today.weekday() >= 5:  # Sat/Sun
        today = today - timedelta(days=today.weekday() - 4)  # Friday
    return today.strftime("%Y%m%d")

# ── Heat rank pools ───────────────────────────────────────────────────

def _fetch_ths_hot_pool(max_stocks: int = 50) -> list[str]:
    """Fetch top N hottest A-stocks from 同花顺 heat rank (东方财富)."""
    try:
        import akshare as ak
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            return []
        symbols = []
        for _, row in df.iterrows():
            code = str(row.iloc[1])
            if code.startswith("SH"):
                symbols.append(code[2:] + ".SH")
            elif code.startswith("SZ"):
                symbols.append(code[2:] + ".SZ")
            if len(symbols) >= max_stocks:
                break
        return symbols
    except Exception as e:
        logger.warning("THS hot rank fetch failed: %s", e)
        return []


def _fetch_hk_hot_pool(max_stocks: int = 50) -> list[str]:
    """Fetch top N hottest HK stocks from 东方财富 HK heat rank."""
    try:
        import akshare as ak
        # Try hot rank first
        df = ak.stock_hk_hot_rank_em()
        if df is not None and not df.empty:
            symbols = []
            for _, row in df.iterrows():
                code = str(row.iloc[0])  # First column should be code
                # Normalize: might be "00700" or "700" or "HK.00700"
                code = code.replace("HK.", "").replace("HK", "").strip()
                if code.isdigit():
                    code = code.zfill(5)
                    symbols.append(f"{code}.HK")
                if len(symbols) >= max_stocks:
                    break
            if symbols:
                return symbols
    except Exception as e:
        logger.debug("HK hot rank failed: %s", e)

    # Fallback: spot market sorted by turnover
    try:
        import akshare as ak
        df = ak.stock_hk_spot_em()
        if df is not None and not df.empty:
            # Sort by 成交额 (turnover) descending
            turnover_col = None
            for col in df.columns:
                if "成交额" in str(col) or "turnover" in str(col).lower():
                    turnover_col = col
                    break
            if turnover_col:
                df = df.sort_values(turnover_col, ascending=False)
            symbols = []
            for _, row in df.iterrows():
                code = str(row.iloc[0])  # 代码
                code = code.strip().zfill(5)
                if code.isdigit():
                    symbols.append(f"{code}.HK")
                if len(symbols) >= max_stocks:
                    break
            return symbols
    except Exception as e:
        logger.debug("HK spot fallback failed: %s", e)

    return []


# ── Data fetching ─────────────────────────────────────────────────────

def _get_data(symbol: str) -> tuple[dict | None, float, float, float, float]:
    """Get monitor quote + fundamentals. Returns (indicator_dict, price, pe, pb, mv)."""
    from src.monitor import fetch_quote
    q = fetch_quote(symbol)
    if q.error or q.price <= 0:
        return None, 0, 0, 0, 0

    pe = pb = mv = 0.0
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        pe = float(info.get("trailingPE") or info.get("forwardPE") or 0)
        pb = float(info.get("priceToBook") or 0)
        mv = float(info.get("marketCap") or 0)
    except Exception:
        pass

    return (q.indicators or {}), q.price, pe, pb, mv

def _calc_returns(closes: list[float]) -> tuple:
    price = closes[-1]
    r1w = round((price / closes[-min(5, len(closes))] - 1) * 100, 2)
    r1m = round((price / closes[-min(20, len(closes))] - 1) * 100, 2)
    r3m = round((price / closes[0] - 1) * 100, 2)
    chg = round((price / closes[-2] - 1) * 100, 2) if len(closes) >= 2 else 0
    m1 = closes[-20:] if len(closes) >= 20 else closes
    peak = m1[0]; max_dd = 0.0
    for c in m1:
        if c > peak: peak = c
        dd = (peak - c) / peak
        if dd > max_dd: max_dd = dd
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
    vol = math.sqrt(sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / len(rets)) * 100 if rets else 2
    return r1w, r1m, r3m, round(max_dd * 100, 1), round(vol, 2), price, chg

def _score_from_indicator(symbol: str, ind: dict, price: float, pe: float, pb: float, mv: float) -> StockScore:
    """Score stock using monitor's pre-computed indicators."""
    ma = ind.get("ma", {}) or {}
    rsi = ind.get("rsi")
    macd = ind.get("macd", {}) or {}

    s = StockScore(symbol=symbol, name="", price=round(price, 2), change_pct=0,
                   pe=round(pe, 1), pb=round(pb, 1), roe=0, market_cap=mv)

    # Momentum: infer from MA alignment (proxy for trend strength)
    mom = 5.0
    if ma.get("ma5") and ma.get("ma20"):
        if price > ma["ma5"] > ma["ma20"]: mom = 9
        elif price > ma["ma20"]: mom = 7
        elif price > ma["ma60"]: mom = 5
        else: mom = 3
    s.factors.momentum = mom

    # Technical: RSI + MACD + MA
    tech = 5.0
    if rsi is not None:
        if 40 <= rsi <= 60: tech += 2
        elif rsi < 30: tech += 3
        elif rsi > 70: tech -= 1
    if macd.get("macd") and macd["macd"] > 0: tech += 2
    if macd.get("dif") and macd.get("dea"):
        if macd["dif"] > macd["dea"]: tech += 1
    if ma.get("ma5") and ma.get("ma20") and price > ma["ma5"] > ma["ma20"]: tech += 1
    s.factors.technical = max(0, min(10, tech))

    # Volume: approximated from price vs MA spread
    spread = abs(price - ma.get("ma20", price)) / price * 100 if ma.get("ma20") else 0
    s.factors.volume = min(10, 5 + spread)

    # Trend
    trend = 5.0
    if ma.get("ma5") and ma.get("ma20") and price > ma["ma5"] > ma["ma20"]: trend = 8
    elif ma.get("ma20") and price > ma["ma20"]: trend = 6
    else: trend = 4
    s.factors.trend = trend

    # Catalyst
    cat = 5.0
    if 0 < pe < 15: cat += 2
    elif 0 < pe < 25: cat += 1
    if rsi and rsi < 35: cat += 2
    s.factors.catalyst = max(0, min(10, cat))

    # Value
    v = 5.0
    if 0 < pe < 15: v += 2
    elif 0 < pe < 25: v += 1
    if 0 < pb < 1.5: v += 1
    s.factors.value = max(0, min(10, v))

    # Defaults
    s.factors.industry = 5.0
    s.factors.news_sentiment = 5.0

    s.total_score = round(s.factors.total, 1)

    if s.factors.momentum >= 7: s.signals.append("强动量")
    if s.factors.technical >= 7: s.signals.append("技术突破")
    if s.factors.trend >= 7: s.signals.append("趋势向好")
    if rsi and rsi < 35: s.signals.append("RSI超卖反弹")
    return s


def _score(closes: list[float], name: str, pe: float, pb: float, roe: float, mv: float, symbol: str) -> StockScore:
    r1w, r1m, r3m, max_dd, vol, price, chg = _calc_returns(closes)
    s = StockScore(symbol=symbol, name=name, price=round(price, 2),
                   change_pct=chg, pe=round(pe, 1), pb=round(pb, 1),
                   roe=round(roe, 1), market_cap=mv)

    # Momentum 0-10 (short-term heavy + acceleration)
    composite = r1w * 0.5 + r1m * 0.3 + r3m * 0.2
    accel = r1w - r1m if r1m != 0 else 0
    composite += max(0, accel * 0.2)
    if composite > 15: s.factors.momentum = 10
    elif composite > 10: s.factors.momentum = 8 + (composite - 10) * 0.4
    elif composite > 5: s.factors.momentum = 6 + (composite - 5) * 0.4
    elif composite > 2: s.factors.momentum = 5 + (composite - 2) * 0.5
    elif composite >= 0: s.factors.momentum = 4 + composite
    else: s.factors.momentum = max(0, 3 + composite * 0.5)

    # Technical 0-10
    tech = 5.0
    if len(closes) >= 20:
        ma5 = sum(closes[-5:]) / 5; ma10 = sum(closes[-10:]) / 10; ma20 = sum(closes[-20:]) / 20
        if price > ma5 > ma10 > ma20: tech += 3
        elif price > ma5 > ma20: tech += 2
        elif price > ma20: tech += 1
        elif price < ma20: tech -= 2
        recent_max = max(closes[-20:-1])
        if price > recent_max: tech += 2
        period = 14
        if len(closes) >= period + 1:
            gains = losses = 0.0
            for i in range(-period, 0):
                d = closes[i] - closes[i - 1]
                if d > 0: gains += d
                else: losses -= d
            if losses > 0:
                rsi = 100.0 - 100.0 / (1.0 + (gains / period) / (losses / period))
                if 50 <= rsi <= 65: tech += 2
                elif 40 <= rsi < 50: tech += 1
                elif rsi < 30: tech += 2
                elif rsi > 75: tech -= 1
        if len(closes) >= 26:
            def ema(data, n):
                k = 2 / (n + 1); out = [sum(data[:n]) / n]
                for v in data[n:]: out.append(v * k + out[-1] * (1 - k))
                return out
            e12, e26 = ema(closes, 12), ema(closes, 26)
            m = min(len(e12), len(e26))
            dif = [e12[-m + i] - e26[-m + i] for i in range(m)]
            dea = ema(dif, 9) if len(dif) >= 9 else dif
            if dif[-1] > dea[-1] and dif[-1] > 0: tech += 2
            elif dif[-1] > dea[-1]: tech += 1
    s.factors.technical = max(0, min(10, tech))

    # Volume 0-10
    if abs(chg) > 5: s.factors.volume = 10
    elif abs(chg) > 3: s.factors.volume = 8
    elif abs(chg) > 2: s.factors.volume = 7
    elif abs(chg) > 1: s.factors.volume = 6
    else: s.factors.volume = 5

    # Trend 0-10
    if len(closes) >= 5:
        up_days = sum(1 for i in range(-5, 0) if closes[i] > closes[i - 1])
        s.factors.trend = 10 if up_days >= 4 else 8 if up_days >= 3 else 6 if up_days >= 2 else 5 if up_days >= 1 else 3
        if len(closes) >= 2 and price > closes[-2] * 1.02:
            s.factors.trend = min(10, s.factors.trend + 2)

    # Catalyst 0-10
    catalyst = 5.0
    if 0 < pe < 15 and abs(chg) > 2: catalyst = 9
    elif 0 < pe < 20 and abs(chg) > 1: catalyst = 7
    elif abs(chg) > 3: catalyst = 8
    s.factors.catalyst = catalyst

    # Value 0-10
    v = 5.0
    if 0 < pe < 15: v += 2
    elif 0 < pe < 25: v += 1
    if 0 < pb < 1.5: v += 1
    s.factors.value = max(0, min(10, v))

    # Defaults for enrichment
    s.factors.industry = 5.0
    s.factors.news_sentiment = 5.0

    s.total_score = round(s.factors.total, 1)

    if s.factors.momentum >= 8: s.signals.append("强动量")
    if s.factors.technical >= 7: s.signals.append("技术突破")
    if s.factors.trend >= 8: s.signals.append("连阳")
    if abs(chg) > 3: s.signals.append(f"{'+' if chg>0 else ''}{chg:.1f}%")
    return s


# ── Industry & News enrichment ────────────────────────────────────────

_INDUSTRY_KW = {
    "银行": ["银行","工行","建行","招行","农行","中行","交行","ICBC","CCB","BANK"],
    "保险": ["保险","人寿","平安","太保","LIFE","INSURANCE"],
    "互联网": ["腾讯","阿里","美团","京东","网易","百度","快手","TENCENT","MEITUAN","JD","BILIBILI"],
    "白酒": ["茅台","五粮液","泸州老窖","汾酒","洋河","MOUTAI"],
    "医药": ["医药","药明","百济","恒瑞","生物","医疗","PHARMA","BIOTECH"],
    "新能源": ["新能源","宁德","比亚迪","光伏","锂电","储能","BYD","CATL"],
    "半导体": ["半导体","芯片","中芯","华虹","韦尔","SMIC"],
    "汽车": ["汽车","长城","吉利","理想","小鹏","蔚来","LI AUTO","NIO","XPENG"],
    "消费电子": ["小米","电子","立讯","歌尔","XIAOMI"],
}

def _enrich_top(scores: list[StockScore]) -> None:
    """Add industry trend and news sentiment to top candidates."""
    if len(scores) < 2: return

    # Industry detection
    for s in scores:
        for ind, kws in _INDUSTRY_KW.items():
            for kw in kws:
                if kw.lower() in s.name.lower():
                    s.industry = ind
                    break
            if s.industry: break

    # Industry scoring
    ind_mom: dict[str, list[float]] = {}
    for s in scores:
        if s.industry:
            ind_mom.setdefault(s.industry, []).append(s.factors.momentum)
    if ind_mom:
        all_avg = sum(sum(v) / len(v) for v in ind_mom.values()) / len(ind_mom)
        for s in scores:
            if s.industry and s.industry in ind_mom:
                ia = sum(ind_mom[s.industry]) / len(ind_mom[s.industry])
                s.factors.industry = max(0, min(10, 5 + (ia - all_avg) * 1.5))

    # News sentiment (top 10 only, parallel)
    top10 = scores[:10]
    with ThreadPoolExecutor(max_workers=3) as pool:
        def news(s: StockScore):
            try:
                from ddgs import DDGS
                with DDGS() as ddg:
                    results = list(ddg.text(f"{s.symbol} {s.name} stock news", max_results=4))
                bull = bear = total = 0
                for r in results:
                    txt = f"{r.get('title','')} {r.get('body','')}".lower()
                    total += 1
                    if any(k in txt for k in ["涨","利好","增长","突破","买入","大涨","飙升","新高","surge","rally","beat","upgrade","bullish"]): bull += 1
                    if any(k in txt for k in ["跌","利空","下滑","亏损","大跌","暴跌","风险","减持","plunge","drop","downgrade","bearish"]): bear += 1
                s.factors.news_sentiment = round(2.0 + (bull / total) * 8.0, 1) if total else 5.0
                if s.factors.news_sentiment >= 7: s.signals.append("利好催化")
            except Exception: pass
        futures = [pool.submit(news, s) for s in top10]
        for f in as_completed(futures, timeout=15):
            try: f.result(timeout=10)
            except Exception: pass

    # Recalculate total scores
    for s in scores:
        s.total_score = round(s.factors.total, 1)
    scores.sort(key=lambda x: x.total_score, reverse=True)


# ── Main ──────────────────────────────────────────────────────────────

def screen(universe: str = "hk", top_n: int = 6, symbols: list[str] | None = None) -> list[StockScore]:
    """Screen stocks with 8-factor model. Uses provided symbols if given."""
    if symbols:
        stocks = symbols
    elif universe in ("hk", "港股"):
        stocks = _fetch_hk_hot_pool(50)
    else:
        stocks = _fetch_a_hot_pool(50)

    if not stocks:
        return []

    scores: list[StockScore] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        def process(sym):
            ind, price, pe, pb, mv = _get_data(sym)
            if ind is None:
                return None
            return _score_from_indicator(sym, ind, price, pe, pb, mv)
        futures = {pool.submit(process, s): s for s in stocks}
        for fut in as_completed(futures, timeout=60):
            try:
                r = fut.result(timeout=12)
                if r: scores.append(r)
            except Exception: pass
        futures = {pool.submit(process, s): s for s in stocks}
        for fut in as_completed(futures, timeout=60):
            try:
                r = fut.result(timeout=12)
                if r: scores.append(r)
            except Exception: pass

    if not scores: return []

    scores.sort(key=lambda x: x.total_score, reverse=True)
    _enrich_top(scores)
    return scores[:top_n]

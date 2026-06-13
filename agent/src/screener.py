"""Multi-factor stock screener — screens ALL stocks, returns top picks."""

from __future__ import annotations
import logging, math, os
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

WEIGHTS = {"market": 0.10, "value": 0.15, "momentum": 0.20, "quality": 0.15, "information": 0.15, "industry": 0.10, "technical": 0.15}

INDUSTRY_MAP: dict[str, str] = {
    "银行": "银行", "保险": "保险", "券商": "券商", "互联网": "互联网", "白酒": "白酒",
    "医药": "医药", "新能源": "新能源", "半导体": "半导体", "消费电子": "消费电子",
    "家电": "家电", "汽车": "汽车", "地产": "地产", "电力": "电力", "通信": "通信",
    "食品": "食品", "光伏": "光伏", "电池": "电池", "煤炭": "煤炭", "石油": "石油",
}


@dataclass
class FactorScores:
    market: float = 5.0; value: float = 5.0; momentum: float = 5.0; quality: float = 5.0
    information: float = 5.0; industry: float = 5.0; technical: float = 5.0

    @property
    def total(self) -> float:
        return (self.market * 0.10 + self.value * 0.15 + self.momentum * 0.20
                + self.quality * 0.15 + self.information * 0.15 + self.industry * 0.10
                + self.technical * 0.15) * 10


@dataclass
class StockScore:
    symbol: str; name: str = ""; price: float = 0.0; change_pct: float = 0.0
    industry: str = ""; pe: float = 0.0; pb: float = 0.0; roe: float = 0.0
    market_cap: float = 0.0; total_score: float = 0.0
    factors: FactorScores = field(default_factory=FactorScores)
    signals: list[str] = field(default_factory=list); error: str = ""


# ── Step 1: Fetch full universe ──────────────────────────────────────

def _fetch_a_universe() -> list[dict]:
    """Fetch all A-shares with fundamental data via Tushare."""
    results = []
    try:
        import tushare as ts
        token = os.getenv("TUSHARE_TOKEN", "")
        if not token: return []
        pro = ts.pro_api(token)

        # Get today's daily_basic for all stocks
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y%m%d")
        df = pro.daily_basic(trade_date=today, fields="ts_code,pe,pb,roe,total_mv,close")
        if df is None or df.empty:
            # Try yesterday
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            df = pro.daily_basic(trade_date=yesterday, fields="ts_code,pe,pb,roe,total_mv,close")
        if df is None or df.empty:
            return []

        for _, row in df.iterrows():
            pe = float(row.get("pe", 0) or 0)
            pb = float(row.get("pb", 0) or 0)
            roe = float(row.get("roe", 0) or 0)
            mv = float(row.get("total_mv", 0) or 0)
            price = float(row.get("close", 0) or 0)

            # Filter: basic quality
            if pe <= 0 or pe > 80: continue
            if pb <= 0 or pb > 8: continue
            if mv < 10 * 1e8: continue  # >10B market cap
            if price < 3: continue  # skip penny stocks

            ts_code = str(row["ts_code"])
            code = ts_code.split(".")[0]
            suffix = ".SZ" if ts_code.endswith(".SZ") else ".SH"
            symbol = code + suffix

            results.append({"symbol": symbol, "name": "", "price": price, "pe": pe, "pb": pb, "roe": roe, "market_cap": mv})
    except Exception as e:
        logger.warning("A-share universe fetch failed: %s", e)
    return results


def _fetch_hk_universe() -> list[dict]:
    """Fetch all HK stocks with real-time data via akshare."""
    results = []
    try:
        import akshare as ak
        df = ak.stock_hk_spot_em()
        if df is None or df.empty: return []

        for _, row in df.iterrows():
            try:
                code = str(row.get("代码", "")).strip()
                name = str(row.get("名称", "")).strip()
                price = float(row.get("最新价", 0) or 0)
                chg = float(row.get("涨跌幅", 0) or 0)
                pe = float(row.get("市盈率", 0) or 0)
                mv = float(row.get("总市值", 0) or 0) * 1e8 if row.get("总市值") else 0

                if price < 1: continue
                if pe <= 0 or pe > 80: continue
                if mv < 10 * 1e8: continue
                if not code: continue

                code = code.zfill(5)
                symbol = f"{code}.HK"
                results.append({"symbol": symbol, "name": name, "price": price,
                                "pe": pe, "pb": 0, "roe": 0, "market_cap": mv,
                                "change_pct": chg})
            except (ValueError, TypeError):
                pass
    except Exception as e:
        logger.warning("HK universe fetch failed: %s", e)
    return results


# ── Step 2: Get price history and compute technical factors ──────────

def _get_history(symbol: str) -> list[float] | None:
    """Get closing prices for last 3 months."""
    try:
        import requests
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                ind = result[0].get("indicators", {})
                adj = ind.get("adjclose", [{}])[0].get("adjclose") or ind.get("quote", [{}])[0].get("close")
                if adj:
                    return [float(v) for v in adj if v is not None]
    except Exception:
        pass
    return None


def _calc_returns(closes: list[float]) -> tuple[float, float, float, float, float, float, float]:
    """(r1w, r1m, r3m, max_dd, vol, price, change_pct)."""
    price = closes[-1]
    r1w = round((price / closes[-min(5, len(closes))] - 1) * 100, 2)
    r1m = round((price / closes[-min(20, len(closes))] - 1) * 100, 2)
    r3m = round((price / closes[0] - 1) * 100, 2)
    chg = round((price / closes[-2] - 1) * 100, 2) if len(closes) >= 2 else 0

    # max drawdown
    m1 = closes[-20:] if len(closes) >= 20 else closes
    peak = m1[0]; max_dd = 0.0
    for c in m1:
        if c > peak: peak = c
        dd = (peak - c) / peak
        if dd > max_dd: max_dd = dd

    # volatility
    returns = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
    vol = math.sqrt(sum((r - sum(returns) / len(returns)) ** 2 for r in returns) / len(returns)) * 100 if returns else 2

    return r1w, r1m, r3m, round(max_dd * 100, 1), round(vol, 2), price, chg


def _calc_tech(closes: list[float], price: float) -> float:
    """Technical factor 0-10."""
    if len(closes) < 20: return 5.0
    s = 5.0
    ma5 = sum(closes[-5:]) / 5; ma20 = sum(closes[-20:]) / 20
    if price > ma5 > ma20: s += 2
    elif price > ma20: s += 1
    elif price < ma20: s -= 1

    period = 14
    if len(closes) >= period + 1:
        gains = losses = 0.0
        for i in range(-period, 0):
            d = closes[i] - closes[i - 1]
            if d > 0: gains += d
            else: losses -= d
        if losses > 0:
            rsi = 100.0 - 100.0 / (1.0 + (gains / period) / (losses / period))
            if 40 <= rsi <= 60: s += 1
            elif rsi < 30: s += 2
            elif rsi > 70: s -= 1

    if len(closes) >= 26:
        def ema(data, n):
            k = 2 / (n + 1); out = [sum(data[:n]) / n]
            for v in data[n:]: out.append(v * k + out[-1] * (1 - k))
            return out
        e12, e26 = ema(closes, 12), ema(closes, 26)
        m = min(len(e12), len(e26))
        dif = [e12[-m + i] - e26[-m + i] for i in range(m)]
        dea = ema(dif, 9) if len(dif) >= 9 else dif
        if dif[-1] > dea[-1]: s += 1
    return max(0.0, min(10.0, s))


# ── Step 3: Score and rank ────────────────────────────────────────────

def _score(stock: dict, closes: list[float]) -> StockScore:
    r1w, r1m, r3m, max_dd, vol, price, chg = _calc_returns(closes)
    s = StockScore(symbol=stock["symbol"], name=stock.get("name", ""), price=price,
                   change_pct=chg, pe=stock.get("pe", 0), pb=stock.get("pb", 0),
                   roe=stock.get("roe", 0), market_cap=stock.get("market_cap", 0))

    # Momentum (0-10)
    composite = r1w * 0.3 + r1m * 0.4 + r3m * 0.3
    if composite > 20: s.factors.momentum = 10
    elif composite > 10: s.factors.momentum = 7 + (composite - 10) * 0.3
    elif composite > 5: s.factors.momentum = 5 + (composite - 5) * 0.4
    elif composite > 0: s.factors.momentum = 5 + composite * 0.3
    else: s.factors.momentum = max(0, 4 + composite * 0.3)

    # Value (0-10): PE + PB
    v = 5.0
    if 0 < s.pe < 10: v += 3
    elif 10 <= s.pe < 20: v += 2
    elif 20 <= s.pe < 35: v += 1
    if 0 < s.pb < 1: v += 2
    elif 1 <= s.pb < 2: v += 1
    s.factors.value = max(0, min(10, v))

    # Quality (0-10)
    q = 5.0
    if s.roe > 20: q += 2
    elif s.roe > 15: q += 1
    if max_dd < 5: q += 1
    if vol < 2: q += 2
    elif vol < 3: q += 1
    s.factors.quality = max(0, min(10, q))

    # Technical
    s.factors.technical = _calc_tech(closes, price)

    # Market (simplified)
    m = 5.0
    if chg > 3: m = 8
    elif chg > 1: m = 7
    elif chg > 0: m = 6
    elif chg > -2: m = 5
    else: m = 3
    s.factors.market = m

    # Industry + Information (defaults, enriched later)
    s.factors.industry = 5.0
    s.factors.information = 5.0

    s.total_score = round(s.factors.total, 1)
    return s


# ── Main API ──────────────────────────────────────────────────────────

def screen(universe: str, max_stocks: int = 60, top_n: int = 6) -> list[StockScore]:
    """Full market screening: universe → fundamentals filter → technical score → rank."""
    # 1. Fetch universe
    if universe in ("hk", "港股"):
        pool_raw = _fetch_hk_universe()
    else:
        pool_raw = _fetch_a_universe()

    if not pool_raw:
        return []

    logger.info("Screener: %d stocks passed fundamental filter for %s", len(pool_raw), universe)

    # 2. Sort by PE*PB (rough value ranking) and take top N for technical analysis
    pool_raw.sort(key=lambda x: abs(x["pe"] * x.get("pb", 1)) if x["pe"] > 0 else 999)
    candidates = pool_raw[:max_stocks]

    # 3. Get history + score in parallel
    scores: list[StockScore] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        def process(stock):
            closes = _get_history(stock["symbol"])
            if closes and len(closes) >= 20:
                return _score(stock, closes)
            return None
        futures = {pool.submit(process, s): s for s in candidates}
        for fut in as_completed(futures, timeout=60):
            try:
                result = fut.result(timeout=15)
                if result: scores.append(result)
            except Exception:
                pass

    # 4. Rank and return top
    scores.sort(key=lambda x: x.total_score, reverse=True)
    return scores[:top_n]


def get_universe(name: str) -> str:
    return "hk" if name.lower() in ("hk", "港股") else "csi300"

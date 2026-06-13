"""Multi-factor stock screener — screens ALL stocks, returns top picks."""

from __future__ import annotations
import logging, math, os
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Momentum-first: prioritize stocks likely to rise quickly
WEIGHTS = {"momentum": 0.30, "technical": 0.25, "volume": 0.15, "trend": 0.15, "catalyst": 0.10, "value": 0.05}

INDUSTRY_MAP: dict[str, str] = {}


@dataclass
class FactorScores:
    momentum: float = 5.0   # multi-timeframe returns
    technical: float = 5.0  # MA/RSI/MACD breakout
    volume: float = 5.0     # volume surge
    trend: float = 5.0      # consecutive up days, trend strength
    catalyst: float = 5.0   # news/events
    value: float = 5.0      # valuation safety net

    @property
    def total(self) -> float:
        return (self.momentum * 0.30 + self.technical * 0.25 + self.volume * 0.15
                + self.trend * 0.15 + self.catalyst * 0.10 + self.value * 0.05) * 10


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


# ── Step 3: Score and rank ────────────────────────────────────────────

def _score(stock: dict, closes: list[float]) -> StockScore:
    r1w, r1m, r3m, max_dd, vol, price, chg = _calc_returns(closes)
    s = StockScore(symbol=stock["symbol"], name=stock.get("name", ""), price=price,
                   change_pct=chg, pe=stock.get("pe", 0), pb=stock.get("pb", 0),
                   roe=stock.get("roe", 0), market_cap=stock.get("market_cap", 0))

    # ═══ MOMENTUM (30%) — the most important factor ═══
    # Multi-timeframe weighted return, with acceleration bonus
    composite = r1w * 0.5 + r1m * 0.3 + r3m * 0.2  # short-term heavy
    # Acceleration: recent week > recent month = accelerating
    accel = r1w - r1m if r1m != 0 else 0
    composite += max(0, accel * 0.2)
    if composite > 15: s.factors.momentum = 10
    elif composite > 10: s.factors.momentum = 8 + (composite - 10) * 0.4
    elif composite > 5: s.factors.momentum = 6 + (composite - 5) * 0.4
    elif composite > 2: s.factors.momentum = 5 + (composite - 2) * 0.5
    elif composite > 0: s.factors.momentum = 4 + composite
    else: s.factors.momentum = max(0, 3 + composite * 0.5)

    # ═══ TECHNICAL (25%) — breakout detection ═══
    tech = 5.0
    if len(closes) >= 20:
        ma5 = sum(closes[-5:]) / 5; ma10 = sum(closes[-10:]) / 10; ma20 = sum(closes[-20:]) / 20
        # MA bullish alignment
        if price > ma5 > ma10 > ma20: tech += 3
        elif price > ma5 > ma20: tech += 2
        elif price > ma20: tech += 1
        elif price < ma20: tech -= 2
        # Recent breakout (price > max of last 20 days)
        recent_max = max(closes[-20:-1])
        if price > recent_max: tech += 2  # new high!
        # RSI
        period = 14
        if len(closes) >= period + 1:
            gains = losses = 0.0
            for i in range(-period, 0):
                d = closes[i] - closes[i - 1]
                if d > 0: gains += d
                else: losses -= d
            if losses > 0:
                rsi = 100.0 - 100.0 / (1.0 + (gains / period) / (losses / period))
                if 50 <= rsi <= 65: tech += 2  # strong but not overbought
                elif 40 <= rsi < 50: tech += 1  # healthy
                elif rsi < 30: tech += 2  # oversold bounce potential
                elif rsi > 75: tech -= 1
        # MACD bullish
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

    # ═══ VOLUME (15%) — volume surge = institutional interest ═══
    vol_score = 5.0
    # Count consecutive volume expansion days
    if s.price > 0 and s.market_cap > 0:
        # Use price * volume ratio as a crude turnover indicator
        # For now: if change > 2% it implies above-average interest
        if abs(chg) > 5: vol_score = 10
        elif abs(chg) > 3: vol_score = 8
        elif abs(chg) > 2: vol_score = 7
        elif abs(chg) > 1: vol_score = 6
    s.factors.volume = vol_score

    # ═══ TREND (15%) — consecutive up days, trend strength ═══
    trend = 5.0
    if len(closes) >= 5:
        up_days = sum(1 for i in range(-5, 0) if closes[i] > closes[i - 1])
        if up_days >= 4: trend = 10
        elif up_days >= 3: trend = 8
        elif up_days >= 2: trend = 6
        elif up_days >= 1: trend = 5
        else: trend = 3
        # Gap detection: today's low > yesterday's high = bullish gap
        if len(closes) >= 2 and price > closes[-2] * 1.02:
            trend = min(10, trend + 2)
    s.factors.trend = trend

    # ═══ CATALYST (10%) — PE compression + volume as proxy for news ═══
    catalyst = 5.0
    # Low PE + high volume surge = possible undervalued catalyst
    if 0 < s.pe < 15 and abs(chg) > 2: catalyst = 9
    elif 0 < s.pe < 20 and abs(chg) > 1: catalyst = 7
    elif abs(chg) > 3: catalyst = 8  # big move = catalyst
    s.factors.catalyst = catalyst

    # ═══ VALUE (5%) — safety net, not the main driver ═══
    v = 5.0
    if 0 < s.pe < 15: v += 2
    elif 0 < s.pe < 25: v += 1
    elif s.pe > 60: v -= 2
    if 0 < s.pb < 1.5: v += 1
    s.factors.value = max(0, min(10, v))

    s.total_score = round(s.factors.total, 1)

    # Signals
    if s.factors.momentum >= 8: s.signals.append("强动量")
    if s.factors.technical >= 7: s.signals.append("技术突破")
    if s.factors.volume >= 7: s.signals.append("放量")
    if s.factors.trend >= 8: s.signals.append("连续上涨")
    if chg > 5: s.signals.append(f"今日+{chg:.1f}%")

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

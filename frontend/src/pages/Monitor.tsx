import { useState, useCallback, useEffect, useRef } from "react";
import { Plus, TrendingUp, Activity, RefreshCw, X } from "lucide-react";

interface Quote {
  symbol: string; name: string; price: number; change_pct: number;
  high_52w: number; low_52w: number; volume: number;
  signals: Array<{ type: string; message: string }>;
  indicators: Record<string, unknown>;
  error: string;
}

function loadWatchlist(): string[] {
  try {
    const raw = localStorage.getItem("ot_watchlist");
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveWatchlist(list: string[]) {
  localStorage.setItem("ot_watchlist", JSON.stringify(list));
}

const SUGGESTIONS = ["00700.HK", "09988.HK", "06869.HK", "600519.SH", "000001.SZ", "AAPL"];

export function Monitor() {
  const [symbols, setSymbols] = useState<string[]>(loadWatchlist);
  const [input, setInput] = useState("");
  const [data, setData] = useState<Record<string, Quote>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const autoRef = useRef(false);

  const fetchAll = useCallback(async (list: string[]) => {
    if (!list.length) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/monitor", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("ot_user_token")}` },
        body: JSON.stringify({ symbols: list }),
      });
      if (res.ok) {
        const quotes: Quote[] = await res.json();
        const map: Record<string, Quote> = {};
        for (const q of quotes) map[q.symbol] = q;
        setData(map);
      } else {
        setError("获取数据失败");
      }
    } catch { setError("网络错误"); }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (autoRef.current) return;
    autoRef.current = true;
    fetchAll(symbols);
  }, []);

  // Auto-refresh every 30s
  useEffect(() => {
    if (!symbols.length) return;
    const t = setInterval(() => fetchAll(symbols), 30_000);
    return () => clearInterval(t);
  }, [symbols, fetchAll]);

  const add = () => {
    const s = input.trim().toUpperCase();
    if (!s || symbols.includes(s)) return;
    const next = [...symbols, s];
    setSymbols(next);
    saveWatchlist(next);
    setInput("");
    fetchAll(next);
  };

  const remove = (s: string) => {
    const next = symbols.filter((x) => x !== s);
    setSymbols(next);
    saveWatchlist(next);
    setData((prev) => { const n = { ...prev }; delete n[s]; return n; });
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-border/40 shrink-0">
        <div className="max-w-5xl mx-auto space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <Activity className="h-5 w-5 text-orange-500" />
              实时监控
            </h2>
            <button
              onClick={() => fetchAll(symbols)}
              disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs hover:bg-muted transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              刷新
            </button>
          </div>

          <form onSubmit={(e) => { e.preventDefault(); add(); }} className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入股票代码... (例: 00700.HK, 600519.SH, AAPL)"
              className="flex-1 rounded-xl border bg-card px-4 py-2.5 text-sm outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500/40"
            />
            <button
              type="submit"
              disabled={!input.trim()}
              className="px-4 py-2.5 rounded-xl bg-orange-500 text-white text-sm font-medium hover:bg-orange-600 disabled:opacity-40"
            >
              <Plus className="h-4 w-4" />
            </button>
          </form>

          {/* Suggestions */}
          {symbols.length === 0 && (
            <div className="flex flex-wrap gap-1.5">
              <span className="text-xs text-muted-foreground">试试：</span>
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => { setInput(s); }}
                  className="text-xs px-2 py-0.5 rounded-md border hover:bg-muted transition-colors">
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <div className="max-w-5xl mx-auto space-y-3">
          {error && <p className="text-sm text-red-500 text-center py-8">{error}</p>}

          {!error && symbols.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <Activity className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">添加股票代码开始监控</p>
              <p className="text-xs mt-1 opacity-60">数据每 30 秒自动刷新</p>
            </div>
          )}

          {symbols.map((sym) => {
            const q = data[sym];
            return (
              <div key={sym} className="rounded-xl border border-border/40 bg-card/60 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3 min-w-0">
                    {q ? (
                      <TrendingUp className={`h-5 w-5 shrink-0 ${q.change_pct >= 0 ? "text-emerald-500" : "text-red-500"}`} />
                    ) : (
                      <div className="h-5 w-5 rounded-full bg-muted animate-pulse shrink-0" />
                    )}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm">{sym}</span>
                        {q?.name && <span className="text-xs text-muted-foreground truncate">{q.name}</span>}
                      </div>
                      {q?.error && <span className="text-xs text-red-500">{q.error}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-4">
                    {q ? (
                      <>
                        <div className="text-right">
                          <div className="font-mono font-bold">{q.price.toFixed(2)}</div>
                          <div className={`text-xs font-medium ${q.change_pct >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                            {q.change_pct >= 0 ? "+" : ""}{q.change_pct.toFixed(2)}%
                          </div>
                        </div>
                        <button onClick={() => remove(sym)} className="p-1 hover:text-red-500 transition-colors">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </>
                    ) : (
                      <span className="text-xs text-muted-foreground">加载中...</span>
                    )}
                  </div>
                </div>

                {/* Signals */}
                {q && q.signals.length > 0 && (
                  <div className="flex gap-1.5 px-4 pb-3 flex-wrap">
                    {q.signals.map((sig, i) => (
                      <span key={i}
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          sig.type === "bullish"
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            : "bg-red-500/10 text-red-600 dark:text-red-400"
                        }`}
                      >
                        {sig.message}
                      </span>
                    ))}
                  </div>
                )}

                {/* Indicator strip */}
                {q && q.indicators && !q.error && (
                  <div className="flex gap-3 px-4 pb-3 text-xs text-muted-foreground border-t border-border/20 pt-2 flex-wrap">
                    {(() => {
                      const ind = q.indicators as Record<string, unknown>;
                      const ma = ind.ma as Record<string, number> | undefined;
                      const rsi = ind.rsi as number | undefined;
                      const macd = ind.macd as Record<string, number> | undefined;
                      return (
                        <>
                          {ma && <span>MA20:{ma.ma20?.toFixed(2) ?? "-"}</span>}
                          {rsi != null && (
                            <span className={rsi > 70 ? "text-red-500" : rsi < 30 ? "text-emerald-500" : ""}>RSI:{rsi}</span>
                          )}
                          {macd && <span>MACD:{macd.macd?.toFixed(3)}</span>}
                        </>
                      );
                    })()}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

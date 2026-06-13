import { useState, useCallback } from "react";
import { Trophy, RefreshCw, Newspaper } from "lucide-react";

interface Pick {
  symbol: string; name: string; price: number; change_pct: number;
  industry: string;
  total_score: number;
  breakdown: { technical: number; news_sentiment: number; industry_trend: number };
  news: string[];
  signals: string[];
}

const UNIVERSES = [
  { key: "hk", label: "港股", desc: "恒生科技+蓝筹" },
  { key: "csi300", label: "A股", desc: "沪深300大盘" },
];

export function Screener() {
  const [universe, setUniverse] = useState("hk");
  const [picks, setPicks] = useState<Pick[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(async (uni: string) => {
    setLoading(true);
    setError("");
    try {
      const token = localStorage.getItem("ot_user_token") || "";
      const res = await fetch(`/screener/${uni}?top=10`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setPicks(data.picks || []);
      } else {
        setError("筛选失败");
      }
    } catch {
      setError("网络错误");
    }
    setLoading(false);
  }, []);

  const scoreColor = (s: number) => {
    if (s >= 70) return "text-emerald-500";
    if (s >= 50) return "text-amber-500";
    return "text-muted-foreground";
  };

  const barColor = (val: number, max: number) => {
    if (val >= max * 0.7) return "bg-emerald-500";
    if (val >= max * 0.4) return "bg-amber-500";
    return "bg-muted-foreground/30";
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-border/40 shrink-0">
        <div className="max-w-5xl mx-auto space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <Trophy className="h-5 w-5 text-orange-500" />
              每日选股
              <span className="text-xs font-normal text-muted-foreground ml-2">技术面 60% · 消息面 25% · 行业 15%</span>
            </h2>
            <button onClick={() => run(universe)} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs hover:bg-muted transition-colors">
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              筛选
            </button>
          </div>
          <div className="flex gap-2">
            {UNIVERSES.map((u) => (
              <button key={u.key} onClick={() => { setUniverse(u.key); run(u.key); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  universe === u.key ? "bg-orange-500 text-white" : "bg-muted hover:bg-muted/60"}`}>
                {u.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <div className="max-w-5xl mx-auto space-y-3">
          {error && <p className="text-sm text-red-500 text-center py-8">{error}</p>}

          {!error && !loading && picks.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <Trophy className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">点击上方板块开始智能选股</p>
              <p className="text-xs mt-1 opacity-60">结合技术面 + 消息面 + 行业趋势</p>
            </div>
          )}

          {loading && (
            <div className="text-center py-8 text-muted-foreground text-sm">
              <RefreshCw className="h-5 w-5 mx-auto mb-2 animate-spin" />
              正在全面扫描... 技术分析 → 消息面 → 行业趋势
            </div>
          )}

          {picks.map((pick, idx) => (
            <div key={pick.symbol} className="rounded-xl border border-border/40 bg-card/60 overflow-hidden">
              {/* Header */}
              <div className="flex items-center gap-3 px-4 py-3">
                <div className={`text-lg font-bold w-8 text-center ${
                  idx < 3 ? "text-orange-500" : "text-muted-foreground"}`}>
                  {idx === 0 ? "🥇" : idx === 1 ? "🥈" : idx === 2 ? "🥉" : `#${idx + 1}`}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm">{pick.symbol}</span>
                    <span className="text-xs text-muted-foreground truncate">{pick.name}</span>
                    {pick.industry && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-500 font-medium shrink-0">
                        {pick.industry}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="font-mono text-xs">{pick.price.toFixed(2)}</span>
                    <span className={`text-xs font-medium ${pick.change_pct >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                      {pick.change_pct >= 0 ? "+" : ""}{pick.change_pct.toFixed(2)}%
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-lg font-bold ${scoreColor(pick.total_score)}`}>
                    {pick.total_score.toFixed(0)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">综合评分</div>
                </div>
              </div>

              {/* Factor bars */}
              <div className="grid grid-cols-3 gap-3 px-4 pb-3 text-[10px]">
                <div className="space-y-0.5">
                  <div className="flex justify-between text-muted-foreground">
                    <span>📊 技术面</span><span>{pick.breakdown.technical}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${barColor(pick.breakdown.technical, 60)}`}
                      style={{ width: `${(pick.breakdown.technical / 60) * 100}%` }} />
                  </div>
                </div>
                <div className="space-y-0.5">
                  <div className="flex justify-between text-muted-foreground">
                    <span>📰 消息面</span><span>{pick.breakdown.news_sentiment.toFixed(1)}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${barColor(pick.breakdown.news_sentiment, 20)}`}
                      style={{ width: `${(pick.breakdown.news_sentiment / 20) * 100}%` }} />
                  </div>
                </div>
                <div className="space-y-0.5">
                  <div className="flex justify-between text-muted-foreground">
                    <span>🏭 行业</span><span>{pick.breakdown.industry_trend.toFixed(1)}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${barColor(pick.breakdown.industry_trend, 20)}`}
                      style={{ width: `${(pick.breakdown.industry_trend / 20) * 100}%` }} />
                  </div>
                </div>
              </div>

              {/* News headlines */}
              {pick.news.length > 0 && (
                <div className="border-t border-border/20 px-4 py-2 space-y-0.5">
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground mb-1">
                    <Newspaper className="h-3 w-3" /> 相关消息
                  </div>
                  {pick.news.slice(0, 3).map((h, i) => (
                    <p key={i} className="text-[11px] text-muted-foreground truncate">· {h}</p>
                  ))}
                </div>
              )}

              {/* Signals */}
              {pick.signals.length > 0 && (
                <div className="flex gap-1 px-4 pb-3 flex-wrap border-t border-border/20 pt-2">
                  {pick.signals.map((sig, i) => (
                    <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                      sig.includes("📈") ? "bg-emerald-500/10 text-emerald-600" : "bg-red-500/10 text-red-600"
                    }`}>{sig}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

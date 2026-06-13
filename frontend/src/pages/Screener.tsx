import { useState, useCallback } from "react";
import { Trophy, RefreshCw } from "lucide-react";

interface Pick {
  symbol: string; name: string; price: number; change_pct: number;
  industry: string; pe: number; pb: number; roe: number; market_cap: number;
  total_score: number;
  factors: {
    market: number; value: number; momentum: number;
    quality: number; information: number; industry: number; technical: number;
  };
  news: string[]; signals: string[];
}

const FACTORS = [
  { key: "momentum", label: "动量", desc: "1周/1月/3月收益" },
  { key: "value", label: "价值", desc: "价格在52周位置" },
  { key: "information", label: "信息", desc: "新闻情感分析" },
  { key: "technical", label: "技术", desc: "MA/RSI/MACD" },
  { key: "quality", label: "质量", desc: "回撤/波动率" },
  { key: "industry", label: "行业", desc: "行业相对强度" },
  { key: "market", label: "市场", desc: "超额收益Alpha" },
] as const;

const UNIVERSES = [
  { key: "hk", label: "港股", desc: "恒生科技+蓝筹" },
  { key: "csi300", label: "A股", desc: "沪深300" },
];

export function Screener() {
  const [universe, setUniverse] = useState("hk");
  const [picks, setPicks] = useState<Pick[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(async (uni: string) => {
    setLoading(true); setError("");
    try {
      const token = localStorage.getItem("ot_user_token") || "";
      const res = await fetch(`/screener/${uni}?top=8`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setPicks((await res.json()).picks || []);
      else setError("筛选失败");
    } catch { setError("网络错误"); }
    setLoading(false);
  }, []);

  const scoreColor = (s: number) => s >= 70 ? "text-emerald-500" : s >= 55 ? "text-amber-500" : "text-muted-foreground";

  const barColor = (val: number) => {
    if (val >= 8) return "bg-emerald-500";
    if (val >= 6) return "bg-lime-500";
    if (val >= 4) return "bg-amber-500";
    return "bg-red-400";
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-border/40 shrink-0">
        <div className="max-w-4xl mx-auto space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Trophy className="h-5 w-5 text-orange-500" /> 每日选股
              </h2>
              <p className="text-[10px] text-muted-foreground mt-0.5">七因子量化模型 · 动量20% · 价值15% · 信息15% · 技术15% · 质量15% · 行业10% · 市场10%</p>
            </div>
            <button onClick={() => run(universe)} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs hover:bg-muted transition-colors">
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> 筛选
            </button>
          </div>
          <div className="flex gap-2">
            {UNIVERSES.map((u) => (
              <button key={u.key} onClick={() => { setUniverse(u.key); run(u.key); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  universe === u.key ? "bg-orange-500 text-white" : "bg-muted hover:bg-muted/60"}`}>{u.label}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <div className="max-w-4xl mx-auto space-y-3">
          {error && <p className="text-sm text-red-500 text-center py-8">{error}</p>}
          {!error && !loading && picks.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <Trophy className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">点击上方板块开始智能选股</p>
            </div>
          )}
          {loading && (
            <div className="text-center py-8 text-sm text-muted-foreground">
              <RefreshCw className="h-5 w-5 mx-auto mb-2 animate-spin" />
              正在计算七因子模型... 市场/价值/动量/质量/信息/行业/技术
            </div>
          )}

          {picks.map((pick, idx) => (
            <div key={pick.symbol} className="rounded-xl border border-border/40 bg-card/60 overflow-hidden">
              {/* Header */}
              <div className="flex items-center gap-3 px-4 py-3">
                <div className={`text-lg font-bold w-8 text-center ${idx < 3 ? "text-orange-500" : "text-muted-foreground"}`}>
                  {idx === 0 ? "🥇" : idx === 1 ? "🥈" : idx === 2 ? "🥉" : `#${idx + 1}`}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm">{pick.symbol}</span>
                    <span className="text-xs text-muted-foreground truncate">{pick.name}</span>
                    {pick.industry && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-500 font-medium shrink-0">{pick.industry}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-0.5 text-xs">
                    <span className="font-mono">{pick.price.toFixed(2)}</span>
                    <span className={`font-medium ${pick.change_pct >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                      {pick.change_pct >= 0 ? "+" : ""}{pick.change_pct.toFixed(2)}%
                    </span>
                    {pick.pe > 0 && <span className="text-muted-foreground">PE <span className="text-foreground font-medium">{pick.pe.toFixed(1)}</span></span>}
                    {pick.pb > 0 && <span className="text-muted-foreground">PB <span className="text-foreground font-medium">{pick.pb.toFixed(1)}</span></span>}
                    {pick.roe > 0 && <span className="text-muted-foreground">ROE <span className="text-foreground font-medium">{pick.roe.toFixed(1)}%</span></span>}
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-lg font-bold ${scoreColor(pick.total_score)}`}>{pick.total_score.toFixed(0)}</div>
                  <div className="text-[10px] text-muted-foreground">综合评分</div>
                </div>
              </div>

              {/* 7-factor bars */}
              <div className="grid grid-cols-7 gap-1.5 px-4 pb-3">
                {FACTORS.map((f) => {
                  const val = pick.factors[f.key as keyof typeof pick.factors];
                  return (
                    <div key={f.key} className="space-y-0.5 text-center" title={f.desc}>
                      <div className={`text-[10px] font-bold ${barColor(val)}`}>{val.toFixed(1)}</div>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div className={`h-full rounded-full ${barColor(val)}`} style={{ width: `${val * 10}%` }} />
                      </div>
                      <div className="text-[9px] text-muted-foreground">{f.label}</div>
                    </div>
                  );
                })}
              </div>

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

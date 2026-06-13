import { useState, useCallback } from "react";
import { Trophy, RefreshCw, ChevronRight } from "lucide-react";

interface Pick {
  symbol: string; name: string; price: number; change_pct: number;
  total_score: number;
  breakdown: { trend: number; momentum: number; volume: number; rsi: number; macd: number };
  signals: string[];
}

const UNIVERSES = [
  { key: "hk", label: "港股 Top30", desc: "恒生科技+蓝筹" },
  { key: "csi300", label: "A股 沪深300", desc: "大盘蓝筹" },
  { key: "us", label: "美股 Top25", desc: "科技+金融龙头" },
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
    if (val >= max * 0.8) return "bg-emerald-500";
    if (val >= max * 0.5) return "bg-amber-500";
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
            </h2>
            <button
              onClick={() => run(universe)}
              disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs hover:bg-muted transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              刷新
            </button>
          </div>

          <div className="flex gap-2">
            {UNIVERSES.map((u) => (
              <button
                key={u.key}
                onClick={() => { setUniverse(u.key); run(u.key); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  universe === u.key
                    ? "bg-orange-500 text-white"
                    : "bg-muted hover:bg-muted/60"
                }`}
              >
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
              <p className="text-sm">点击上方板块开始筛选</p>
              <p className="text-xs mt-1 opacity-60">基于技术面多因子评分模型</p>
            </div>
          )}

          {loading && (
            <div className="text-center py-8 text-muted-foreground text-sm">
              <RefreshCw className="h-5 w-5 mx-auto mb-2 animate-spin" />
              正在扫描 {universe === "hk" ? "港股" : universe === "csi300" ? "A股" : "美股"}...
            </div>
          )}

          {picks.map((pick, idx) => (
            <div key={pick.symbol} className="rounded-xl border border-border/40 bg-card/60 overflow-hidden">
              <div className="flex items-center gap-4 px-4 py-3">
                {/* Rank */}
                <div className={`text-lg font-bold w-8 text-center ${
                  idx < 3 ? "text-orange-500" : "text-muted-foreground"
                }`}>
                  {idx === 0 ? "🥇" : idx === 1 ? "🥈" : idx === 2 ? "🥉" : `#${idx + 1}`}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm">{pick.symbol}</span>
                    <span className="text-xs text-muted-foreground truncate">{pick.name}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="font-mono text-xs">{pick.price.toFixed(2)}</span>
                    <span className={`text-xs font-medium ${pick.change_pct >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                      {pick.change_pct >= 0 ? "+" : ""}{pick.change_pct.toFixed(2)}%
                    </span>
                  </div>
                </div>

                {/* Score */}
                <div className="text-right">
                  <div className={`text-lg font-bold ${scoreColor(pick.total_score)}`}>
                    {pick.total_score.toFixed(0)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">综合评分</div>
                </div>

                <ChevronRight className="h-4 w-4 text-muted-foreground/40" />
              </div>

              {/* Factor bars */}
              <div className="grid grid-cols-5 gap-2 px-4 pb-3 text-[10px]">
                {[
                  { label: "趋势", val: pick.breakdown.trend, max: 25 },
                  { label: "动量", val: pick.breakdown.momentum, max: 25 },
                  { label: "量能", val: pick.breakdown.volume, max: 20 },
                  { label: "RSI", val: pick.breakdown.rsi, max: 15 },
                  { label: "MACD", val: pick.breakdown.macd, max: 15 },
                ].map((f) => (
                  <div key={f.label} className="space-y-0.5">
                    <div className="flex justify-between text-muted-foreground">
                      <span>{f.label}</span>
                      <span>{f.val}</span>
                    </div>
                    <div className="h-1 rounded-full bg-muted overflow-hidden">
                      <div className={`h-full rounded-full ${barColor(f.val, f.max)}`}
                        style={{ width: `${(f.val / f.max) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              {/* Signals */}
              {pick.signals.length > 0 && (
                <div className="flex gap-1 px-4 pb-3 flex-wrap border-t border-border/20 pt-2">
                  {pick.signals.map((sig, i) => (
                    <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                      sig.includes("📈") ? "bg-emerald-500/10 text-emerald-600" : "bg-red-500/10 text-red-600"
                    }`}>
                      {sig}
                    </span>
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

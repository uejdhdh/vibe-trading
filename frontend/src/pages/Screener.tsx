import { useState, useCallback } from "react";
import { Trophy, RefreshCw } from "lucide-react";

interface Pick {
  symbol: string; name: string; price: number; change_pct: number;
  pe: number; pb: number; roe: number; market_cap: number; total_score: number;
  factors: Record<string, number>; signals: string[];
}

const FACTORS = [
  { key: "momentum", label: "动量" }, { key: "technical", label: "突破" },
  { key: "news_sentiment", label: "消息" }, { key: "industry", label: "行业" },
  { key: "trend", label: "趋势" }, { key: "catalyst", label: "催化" },
  { key: "volume", label: "放量" }, { key: "value", label: "估值" },
];

async function fetchHeatRank(market: "hk" | "a"): Promise<string[]> {
  const url = market === "hk"
    ? "https://emappdata.eastmoney.com/stockrank/getAllCurrHkUsList"
    : "https://emappdata.eastmoney.com/stockrank/getAllCurrentList";
  const body = market === "hk"
    ? { appId: "appId01", globalId: "786e4c21-70dc-435a-93bb-38", marketType: "000003", pageNo: 1, pageSize: 50 }
    : { appId: "appId01", globalId: "786e4c21-70dc-435a-93bb-38", marketType: "", pageNo: 1, pageSize: 50 };

  const r1 = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d1 = await r1.json();
  if (!d1.data) throw new Error("热度榜请求失败");
  const codes: string[] = d1.data.map((item: any) => item.sc);

  // Step 2: get actual symbols
  const marks = market === "hk"
    ? codes.map((c: string) => "116." + c.slice(3))
    : codes.map((c: string) => (c.includes("SZ") ? "0." + c.slice(2) : "1." + c.slice(2)));
  const params = new URLSearchParams({
    ut: "f057cbcbce2a86e2866ab8877db1d059", fltt: "2", invt: "2",
    fields: "f12", secids: marks.join(","),
  });
  const r2 = await fetch(`https://push2.eastmoney.com/api/qt/ulist.np/get?${params}`);
  const d2 = await r2.json();
  const items = d2?.data?.diff || [];
  return items.map((item: any) => {
    const code = item.f12;
    if (market === "hk") return code.toString().padStart(5, "0") + ".HK";
    return code.startsWith("6") ? code + ".SH" : code + ".SZ";
  });
}

export function Screener() {
  const [universe, setUniverse] = useState<"hk" | "a">("hk");
  const [picks, setPicks] = useState<Pick[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const run = useCallback(async (market: "hk" | "a") => {
    setLoading(true); setError(""); setPicks([]); setStatus("正在获取东方财富热度榜...");
    try {
      // Step 1: Fetch heat rank from Eastmoney (client-side, works from China)
      const symbols = await fetchHeatRank(market);
      if (!symbols.length) throw new Error("热度榜为空");
      setStatus(`获取到 ${symbols.length} 只热度股票，正在量化评分...`);

      // Step 2: Send to our server for scoring
      const token = localStorage.getItem("ot_user_token") || "";
      const res = await fetch("/screener/score", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ symbols, universe: market }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "评分失败");
      }
      const data = await res.json();
      setPicks(data.picks || []);
      if (data.weekend_note) setStatus(data.weekend_note);
      else setStatus("");
    } catch (e: any) {
      setError(e.message || "网络错误");
    }
    setLoading(false);
  }, []);

  const barColor = (val: number) => val >= 8 ? "bg-emerald-500" : val >= 6 ? "bg-lime-500" : val >= 4 ? "bg-amber-500" : "bg-red-400";

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-neutral-800/50 shrink-0">
        <div className="max-w-4xl mx-auto space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Trophy className="h-5 w-5 text-orange-500" /> 每日选股
              </h2>
              <p className="text-[10px] text-neutral-400 mt-0.5">东方财富热度榜 → 八因子量化精排</p>
            </div>
            <button onClick={() => run(universe)} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-40 transition-colors">
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> 筛选
            </button>
          </div>
          <div className="flex gap-2">
            {[{ key: "hk", label: "港股" }, { key: "a", label: "A股" }].map((u: any) => (
              <button key={u.key} onClick={() => { setUniverse(u.key); run(u.key); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${universe === u.key ? "bg-orange-500 text-white" : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"}`}>{u.label}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <div className="max-w-4xl mx-auto space-y-3">
          {error && <p className="text-sm text-red-400 text-center py-8">{error}</p>}
          {status && !error && <p className="text-xs text-neutral-400 text-center pt-4">{status}</p>}

          {!error && !loading && picks.length === 0 && !status && (
            <div className="text-center py-16 text-neutral-500">
              <Trophy className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">点击上方板块开始选股</p>
            </div>
          )}

          {loading && (
            <div className="text-center py-8 text-sm text-neutral-400">
              <RefreshCw className="h-5 w-5 mx-auto mb-2 animate-spin" />
              {status}
            </div>
          )}

          {picks.map((pick, idx) => (
            <div key={pick.symbol} className="rounded-xl border border-neutral-800/50 bg-neutral-900/60 overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-3">
                <div className={`text-lg font-bold w-8 text-center ${idx < 3 ? "text-orange-500" : "text-neutral-500"}`}>
                  {idx === 0 ? "🥇" : idx === 1 ? "🥈" : idx === 2 ? "🥉" : `#${idx + 1}`}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-neutral-100">{pick.symbol}</span>
                    <span className="text-xs text-neutral-400 truncate">{pick.name}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5 text-xs">
                    <span className="font-mono text-neutral-200">{pick.price.toFixed(2)}</span>
                    <span className={`font-medium ${pick.change_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {pick.change_pct >= 0 ? "+" : ""}{pick.change_pct.toFixed(2)}%
                    </span>
                    {pick.pe > 0 && <span className="text-neutral-500">PE <span className="text-neutral-300">{pick.pe.toFixed(1)}</span></span>}
                    {pick.pb > 0 && <span className="text-neutral-500">PB <span className="text-neutral-300">{pick.pb.toFixed(1)}</span></span>}
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-lg font-bold ${pick.total_score >= 70 ? "text-emerald-400" : pick.total_score >= 55 ? "text-amber-400" : "text-neutral-400"}`}>
                    {pick.total_score.toFixed(0)}
                  </div>
                  <div className="text-[10px] text-neutral-500">综合评分</div>
                </div>
              </div>

              <div className="grid grid-cols-8 gap-1 px-4 pb-3">
                {FACTORS.map((f) => {
                  const val = pick.factors[f.key] || 5;
                  return (
                    <div key={f.key} className="space-y-0.5 text-center" title={f.label}>
                      <div className={`text-[10px] font-bold ${barColor(val)}`}>{val.toFixed(1)}</div>
                      <div className="h-1 rounded-full bg-neutral-800 overflow-hidden">
                        <div className={`h-full rounded-full ${barColor(val)}`} style={{ width: `${val * 10}%` }} />
                      </div>
                      <div className="text-[9px] text-neutral-500">{f.label}</div>
                    </div>
                  );
                })}
              </div>

              {pick.signals.length > 0 && (
                <div className="flex gap-1 px-4 pb-3 flex-wrap border-t border-neutral-800/30 pt-2">
                  {pick.signals.map((sig, i) => (
                    <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${sig.includes("📈") || sig.includes("利好") || sig.includes("强") || sig.includes("突破") ? "bg-emerald-500/10 text-emerald-400" : sig.includes("+") ? "bg-orange-500/10 text-orange-400" : "bg-red-500/10 text-red-400"}`}>{sig}</span>
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

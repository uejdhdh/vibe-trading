import { useState, useEffect, type ReactNode } from "react";
import { getApiAuthKey, setApiAuthKey } from "@/lib/apiAuth";

interface Props { children: ReactNode; }

export function AuthGuard({ children }: Props) {
  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const existing = getApiAuthKey();
    if (existing) {
      fetch("/health", { headers: { Authorization: `Bearer ${existing}` } })
        .then((r) => { if (r.ok) setUnlocked(true); else setApiAuthKey(""); })
        .catch(() => setUnlocked(true))
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
  }, []);

  const submit = async () => {
    const t = password.trim();
    if (!t) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/health", { headers: { Authorization: `Bearer ${t}` } });
      if (res.ok) { setApiAuthKey(t); setUnlocked(true); }
      else setError("密码错误，请重试");
    } catch {
      setApiAuthKey(t);
      setUnlocked(true);
    }
    setLoading(false);
  };

  if (checking) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground text-sm">Loading…</div>
      </div>
    );
  }

  if (!unlocked) {
    return (
      <div className="flex h-screen items-center justify-center bg-background p-4">
        <div className="w-full max-w-sm space-y-5">
          <div className="text-center space-y-3">
            <div className="mx-auto h-14 w-14 rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-md">
              <svg viewBox="0 0 24 24" className="h-7 w-7 text-white" fill="none">
                <circle cx="9" cy="11" r="2.5" fill="white" opacity="0.9"/>
                <circle cx="15" cy="11" r="2.5" fill="white" opacity="0.9"/>
                <path d="M6 9a5 5 0 0 0 7 0" stroke="white" strokeWidth="1" strokeLinecap="round" opacity="0.5"/>
              </svg>
            </div>
            <h1 className="text-xl font-bold tracking-tight">Orange Trade</h1>
            <p className="text-sm text-muted-foreground">请输入访问密码</p>
          </div>
          <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="space-y-3">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="访问密码"
              className="w-full rounded-xl border bg-card px-4 py-2.5 text-sm outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500/40 transition-all"
              autoFocus
            />
            {error && <p className="text-xs text-red-500 text-center">{error}</p>}
            <button
              type="submit"
              disabled={loading || !password.trim()}
              className="w-full rounded-xl bg-orange-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-orange-600 disabled:opacity-40 transition-colors"
            >
              {loading ? "验证中…" : "进入 Orange Trade"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

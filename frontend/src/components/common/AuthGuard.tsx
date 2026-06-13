import { useState, useEffect, type ReactNode, type FormEvent } from "react";
import { isLoggedIn, setUserAuth, clearUserAuth, getUserToken } from "@/lib/userAuth";

export function AuthGuard({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isLoggedIn()) {
      fetch("/health", { headers: { Authorization: `Bearer ${getUserToken()}` } })
        .then((r) => { if (r.ok) setUnlocked(true); else clearUserAuth(); })
        .catch(() => setUnlocked(true))
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password) return;
    setLoading(true); setError("");
    try {
      const res = await fetch("/auth/admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_key: password }),
      });
      if (res.ok) {
        const data = await res.json();
        setUserAuth(data.token, data.username, data.is_admin);
        setUnlocked(true);
      } else {
        setError("密码错误");
      }
    } catch { setError("无法连接服务器"); }
    setLoading(false);
  };

  if (checking) return null;

  if (!unlocked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a0b] p-4">
        <div className="w-full max-w-sm space-y-6">
          <div className="text-center space-y-3">
            <div className="mx-auto h-16 w-16 rounded-2xl bg-gradient-to-br from-orange-500 via-orange-600 to-red-500 flex items-center justify-center shadow-lg shadow-orange-500/20">
              <svg viewBox="0 0 24 24" className="h-8 w-8 text-white" fill="none" stroke="white" strokeWidth="0.5">
                <circle cx="8" cy="10" r="2.5" fill="white" opacity="0.95"/>
                <circle cx="16" cy="10" r="2.5" fill="white" opacity="0.95"/>
                <path d="M5 8a6 6 0 0 0 8 0" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
              </svg>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Orange Trade</h1>
            <p className="text-sm text-neutral-400">AI 量化交易助手</p>
          </div>
          <form onSubmit={submit} className="space-y-3">
            <input
              type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="管理员密码"
              className="w-full rounded-xl border border-neutral-800 bg-neutral-900/50 px-4 py-3 text-sm text-white placeholder:text-neutral-500 outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/30 transition-all"
              autoFocus autoComplete="off"
            />
            {error && <p className="text-xs text-red-400 text-center">{error}</p>}
            <button type="submit" disabled={loading || !password}
              className="w-full rounded-xl bg-gradient-to-r from-orange-500 to-orange-600 px-4 py-3 text-sm font-medium text-white hover:from-orange-600 hover:to-orange-700 disabled:opacity-40 transition-all shadow-lg shadow-orange-500/10">
              {loading ? "验证中…" : "进入"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

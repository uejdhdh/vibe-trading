import { useState, useEffect, type ReactNode, type FormEvent } from "react";
import { isLoggedIn, setUserAuth, clearUserAuth, getUserToken } from "@/lib/userAuth";

interface Props { children: ReactNode; }

export function AuthGuard({ children }: Props) {
  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isLoggedIn()) {
      // Verify token is still valid
      fetch("/health", { headers: { Authorization: `Bearer ${getUserToken()}` } })
        .then((r) => {
          if (r.ok) setUnlocked(true);
          else clearUserAuth();
        })
        .catch(() => setUnlocked(true))  // allow offline
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const u = username.trim();
    const p = password;
    if (!u || !p) return;
    setLoading(true);
    setError("");

    try {
      const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p }),
      });
      if (res.ok) {
        const data = await res.json();
        setUserAuth(data.token, data.username);
        setUnlocked(true);
      } else {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || (mode === "login" ? "用户名或密码错误" : "注册失败，可能用户名已被占用"));
      }
    } catch {
      setError("无法连接服务器，请检查网络");
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
          {/* Logo */}
          <div className="text-center space-y-3">
            <div className="mx-auto h-14 w-14 rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-md">
              <svg viewBox="0 0 24 24" className="h-7 w-7 text-white" fill="none">
                <circle cx="9" cy="11" r="2.5" fill="white" opacity="0.9"/>
                <circle cx="15" cy="11" r="2.5" fill="white" opacity="0.9"/>
                <path d="M6 9a5 5 0 0 0 7 0" stroke="white" strokeWidth="1" strokeLinecap="round" opacity="0.5"/>
              </svg>
            </div>
            <h1 className="text-xl font-bold tracking-tight">Orange Trade</h1>
            <p className="text-sm text-muted-foreground">
              {mode === "login" ? "登录你的账号" : "创建新账号"}
            </p>
          </div>

          <form onSubmit={submit} className="space-y-3">
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="用户名"
              className="w-full rounded-xl border bg-card px-4 py-2.5 text-sm outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500/40 transition-all"
              autoFocus
              autoComplete="username"
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="密码"
              className="w-full rounded-xl border bg-card px-4 py-2.5 text-sm outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500/40 transition-all"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
            {error && (
              <p className="text-xs text-red-500 text-center">{error}</p>
            )}
            <button
              type="submit"
              disabled={loading || !username.trim() || !password}
              className="w-full rounded-xl bg-orange-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-orange-600 disabled:opacity-40 transition-colors"
            >
              {loading ? "请稍候…" : mode === "login" ? "登录" : "注册"}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground">
            {mode === "login" ? (
              <>没有账号？<button onClick={() => { setMode("register"); setError(""); }} className="text-orange-500 hover:underline">注册</button></>
            ) : (
              <>已有账号？<button onClick={() => { setMode("login"); setError(""); }} className="text-orange-500 hover:underline">登录</button></>
            )}
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

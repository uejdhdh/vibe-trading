import { useState, useEffect, type ReactNode } from "react";
import { getApiAuthKey, setApiAuthKey } from "@/lib/apiAuth";

interface Props {
  children: ReactNode;
}

export function AuthGuard({ children }: Props) {
  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // On first load, check if we already have a key
    const existing = getApiAuthKey();
    if (existing) {
      // Verify it still works
      fetch("/health", {
        headers: { Authorization: `Bearer ${existing}` },
      })
        .then((r) => {
          if (r.ok) {
            setUnlocked(true);
          } else {
            // Key is invalid, clear it
            setApiAuthKey("");
          }
        })
        .catch(() => {
          // Network error, but we have a key — let them in
          setUnlocked(true);
        })
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
  }, []);

  const submit = async () => {
    const trimmed = password.trim();
    if (!trimmed) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/health", {
        headers: { Authorization: `Bearer ${trimmed}` },
      });
      if (res.ok) {
        setApiAuthKey(trimmed);
        setUnlocked(true);
      } else {
        setError("密码错误，请重试");
      }
    } catch {
      // If backend is unreachable, still allow in and store the key
      setApiAuthKey(trimmed);
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
          <div className="text-center space-y-2">
            <h1 className="text-xl font-bold tracking-tight">Vibe-Trading</h1>
            <p className="text-sm text-muted-foreground">
              请输入访问密码
            </p>
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); submit(); }}
            className="space-y-3"
          >
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="访问密码"
              className="w-full rounded-lg border bg-card px-4 py-2.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              autoFocus
            />
            {error && (
              <p className="text-xs text-danger text-center">{error}</p>
            )}
            <button
              type="submit"
              disabled={loading || !password.trim()}
              className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {loading ? "验证中…" : "进入"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

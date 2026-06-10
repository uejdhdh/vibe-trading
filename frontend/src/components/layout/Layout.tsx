import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { Plus, Settings, Trash2, Pencil, PanelLeftClose, PanelLeftOpen, MessageSquare, LogOut, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type SessionItem } from "@/lib/api";
import { useAgentStore } from "@/stores/agent";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";
import { getUsername, clearUserAuth, isAdmin } from "@/lib/userAuth";

export function Layout() {
  const { pathname } = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const isSettings = pathname.startsWith("/settings");
  const sseStatus = useAgentStore((s) => s.sseStatus);
  const sseRetryAttempt = useAgentStore((s) => s.sseRetryAttempt);

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("ot-sidebar") === "collapsed");
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameVal, setRenameVal] = useState("");

  const activeId = searchParams.get("session");

  const load = () => {
    api.listSessions()
      .then((list) => setSessions(Array.isArray(list) ? list : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    localStorage.setItem("ot-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  useEffect(() => { load(); }, [pathname, activeId]);

  const newChat = () => {
    setSearchParams({}, { replace: true });
    useAgentStore.getState().reset();
  };

  const del = async (sid: string) => {
    try {
      await api.deleteSession(sid);
      setSessions((p) => p.filter((s) => s.session_id !== sid));
      if (activeId === sid) newChat();
    } catch { /* ignore */ }
  };

  const confirmRename = async (sid: string) => {
    if (!renameVal.trim()) { setRenameId(null); return; }
    try {
      await api.renameSession(sid, renameVal.trim());
      setSessions((p) => p.map((s) => s.session_id === sid ? { ...s, title: renameVal.trim() } : s));
    } catch { /* ignore */ }
    setRenameId(null);
  };

  const settingsUrl = isSettings
    ? (activeId ? `/agent?session=${activeId}` : "/agent")
    : "/settings";

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className={cn(
        "flex flex-col shrink-0 border-r border-border/40 bg-card/40 transition-all duration-200",
        collapsed ? "w-0 overflow-hidden border-0" : "w-64"
      )}>
        {/* Brand */}
        <div className="px-3 pt-3 pb-1">
          <Link to="/agent" className="flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shrink-0">
              <svg viewBox="0 0 24 24" className="h-4 w-4 text-white" fill="none">
                <circle cx="9" cy="11" r="2" fill="white" opacity="0.9"/>
                <circle cx="15" cy="11" r="2" fill="white" opacity="0.9"/>
                <path d="M6 9a4 4 0 0 0 6 0" stroke="white" strokeWidth="1.2" strokeLinecap="round" opacity="0.6"/>
              </svg>
            </div>
            <span className="text-sm font-bold tracking-tight">Orange Trade</span>
          </Link>
        </div>

        <div className="px-3 pb-1">
          <button
            onClick={newChat}
            className="flex items-center gap-2 w-full rounded-lg border border-border/60 px-3 py-2 text-sm hover:bg-muted/60 transition-colors"
          >
            <Plus className="h-4 w-4" />
            新对话
          </button>
        </div>
        <div className="px-3 pb-3">
          <Link
            to="/monitor"
            className="flex items-center gap-2 w-full rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
          >
            <Activity className="h-4 w-4" />
            实时监控
          </Link>
        </div>

        <div className="flex-1 overflow-auto px-2 pb-2">
          {loading ? (
            <div className="space-y-1 px-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-8 rounded-lg bg-muted/40 animate-pulse" />
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground/50">暂无对话</p>
          ) : (
            <div className="space-y-0.5">
              {sessions.map((s) => {
                const isActive = s.session_id === activeId;
                return (
                  <div key={s.session_id} className="group relative">
                    {renameId === s.session_id ? (
                      <input
                        autoFocus
                        value={renameVal}
                        onChange={(e) => setRenameVal(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") confirmRename(s.session_id);
                          if (e.key === "Escape") setRenameId(null);
                        }}
                        onBlur={() => confirmRename(s.session_id)}
                        className="w-full rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-orange-500/40"
                      />
                    ) : (
                      <button
                        onClick={() => setSearchParams({ session: s.session_id }, { replace: true })}
                        className={cn(
                          "w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-left transition-colors",
                          isActive
                            ? "bg-orange-500/10 text-orange-600 dark:text-orange-400 font-medium"
                            : "hover:bg-muted/60"
                        )}
                      >
                        <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
                        <span className="flex-1 truncate">{s.title || s.session_id.slice(0, 12)}</span>
                        {isAdmin() && s.user_id && (
                          <span className="text-[9px] text-muted-foreground/50 font-mono shrink-0" title={s.user_id}>
                            {s.user_id.slice(0, 6)}
                          </span>
                        )}
                        <div className="hidden group-hover:flex items-center gap-0.5 ml-1">
                          <span
                            onClick={(e) => { e.stopPropagation(); setRenameId(s.session_id); setRenameVal(s.title || ""); }}
                            className="p-0.5 hover:text-foreground rounded"
                          >
                            <Pencil className="h-3 w-3" />
                          </span>
                          <span
                            onClick={(e) => { e.stopPropagation(); del(s.session_id); }}
                            className="p-0.5 hover:text-red-500 rounded"
                          >
                            <Trash2 className="h-3 w-3" />
                          </span>
                        </div>
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="border-t border-border/40 p-3 space-y-1">
          {/* Current user */}
          <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-muted-foreground">
            <div className="h-5 w-5 rounded-full bg-orange-500/20 text-orange-500 flex items-center justify-center text-[10px] font-bold">
              {getUsername().charAt(0).toUpperCase()}
            </div>
            <span className="flex-1 truncate">{getUsername()}</span>
            <button
              onClick={() => { clearUserAuth(); window.location.reload(); }}
              className="p-1 hover:text-red-500 rounded transition-colors"
              title="退出登录"
            >
              <LogOut className="h-3 w-3" />
            </button>
          </div>
          <Link
            to={settingsUrl}
            className="flex items-center gap-2 w-full rounded-lg px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
          >
            <Settings className="h-3.5 w-3.5" />
            设置
          </Link>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="flex items-center shrink-0 border-b border-border/40 px-3 py-2">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            title={collapsed ? "展开" : "收起"}
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
          <div className="flex-1" />
        </header>

        <ConnectionBanner status={sseStatus} retryAttempt={sseRetryAttempt} />

        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

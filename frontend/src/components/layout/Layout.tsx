import { useEffect, useState, useCallback } from "react";
import { Link, Outlet, useSearchParams } from "react-router-dom";
import { Plus, Settings, Trash2, Pencil, PanelLeft, MessageSquare, LogOut, Trophy } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type SessionItem } from "@/lib/api";
import { useAgentStore } from "@/stores/agent";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";
import { getUsername, clearUserAuth } from "@/lib/userAuth";

export function Layout() {
  const [searchParams, setSearchParams] = useSearchParams();
  const sseStatus = useAgentStore((s) => s.sseStatus);
  const sseRetryAttempt = useAgentStore((s) => s.sseRetryAttempt);

  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameVal, setRenameVal] = useState("");

  const activeId = searchParams.get("session");

  const load = useCallback(() => {
    setLoading(true);
    api.listSessions().then((list) => setSessions(Array.isArray(list) ? list : [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [activeId, load]);
  useEffect(() => { const onFocus = () => load(); window.addEventListener("focus", onFocus); return () => window.removeEventListener("focus", onFocus); }, [load]);

  const newChat = () => {
    setSearchParams({}, { replace: true });
    useAgentStore.getState().reset();
    setOpen(false);
  };

  const del = async (sid: string) => {
    try { await api.deleteSession(sid); setSessions((p) => p.filter((s) => s.session_id !== sid)); if (activeId === sid) newChat(); } catch {}
  };

  const confirmRename = async (sid: string) => {
    if (!renameVal.trim()) { setRenameId(null); return; }
    try { await api.renameSession(sid, renameVal.trim()); setSessions((p) => p.map((s) => s.session_id === sid ? { ...s, title: renameVal.trim() } : s)); } catch {}
    setRenameId(null);
  };

  return (
    <div className="flex h-screen bg-[#0a0a0b] text-neutral-100 overflow-hidden">
      {/* Mobile overlay */}
      {open && <div className="fixed inset-0 z-40 bg-black/60 md:hidden" onClick={() => setOpen(false)} />}

      {/* Sidebar */}
      <aside className={cn(
        "flex flex-col shrink-0 border-r border-neutral-800/50 bg-neutral-950/80 backdrop-blur-xl z-50",
        "fixed inset-y-0 left-0 w-72 md:relative md:w-64 transition-transform duration-200",
        !open && "-translate-x-full md:translate-x-0"
      )}>
        {/* Brand */}
        <div className="px-4 pt-4 pb-2">
          <Link to="/agent" onClick={() => setOpen(false)} className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-lg shadow-orange-500/20 shrink-0">
              <svg viewBox="0 0 24 24" className="h-4.5 w-4.5 text-white" fill="none" stroke="white" strokeWidth="0.5">
                <circle cx="8" cy="10" r="2" fill="white" opacity="0.9"/>
                <circle cx="16" cy="10" r="2" fill="white" opacity="0.9"/>
                <path d="M5 8a5 5 0 0 0 7.5 0" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
              </svg>
            </div>
            <span className="text-base font-bold tracking-tight">Orange Trade</span>
          </Link>
        </div>

        {/* New chat */}
        <div className="px-3 pb-1">
          <button onClick={newChat} className="flex items-center gap-2.5 w-full rounded-xl border border-neutral-800/60 px-3 py-2.5 text-sm text-neutral-300 hover:bg-neutral-800/50 hover:border-neutral-700 transition-all">
            <Plus className="h-4 w-4 text-neutral-400" /> 新对话
          </button>
        </div>

        {/* Nav */}
        <div className="px-3 pb-1 space-y-0.5">
          <Link to="/screener" onClick={() => setOpen(false)} className="flex items-center gap-2.5 w-full rounded-xl px-3 py-2 text-sm text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800/50 transition-all">
            <Trophy className="h-4 w-4" /> 每日选股
          </Link>
        </div>

        {/* Sessions */}
        <div className="flex-1 overflow-auto px-2 pb-2 mt-2 border-t border-neutral-800/30 pt-2">
          {loading ? (
            <div className="space-y-1 px-2">{[1,2,3,4].map((i) => <div key={i} className="h-8 rounded-lg bg-neutral-800/30 animate-pulse" />)}</div>
          ) : sessions.length === 0 ? (
            <p className="px-3 py-6 text-center text-xs text-neutral-500">暂无对话记录</p>
          ) : (
            <div className="space-y-0.5">
              {sessions.map((s) => {
                const isActive = s.session_id === activeId;
                return (
                  <div key={s.session_id} className="group relative">
                    {renameId === s.session_id ? (
                      <input autoFocus value={renameVal} onChange={(e) => setRenameVal(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") confirmRename(s.session_id); if (e.key === "Escape") setRenameId(null); }}
                        onBlur={() => confirmRename(s.session_id)}
                        className="w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-xs outline-none focus:border-orange-500/50" />
                    ) : (
                      <button onClick={() => { setSearchParams({ session: s.session_id }, { replace: true }); setOpen(false); }}
                        className={cn("w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-left transition-all",
                          isActive ? "bg-orange-500/10 text-orange-400 font-medium" : "text-neutral-400 hover:bg-neutral-800/40 hover:text-neutral-200")}>
                        <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-50" />
                        <span className="flex-1 truncate">{s.title || s.session_id.slice(0, 12)}</span>
                        <div className="hidden group-hover:flex items-center gap-0.5 ml-1">
                          <span onClick={(e) => { e.stopPropagation(); setRenameId(s.session_id); setRenameVal(s.title || ""); }} className="p-0.5 hover:text-neutral-200 rounded"><Pencil className="h-3 w-3" /></span>
                          <span onClick={(e) => { e.stopPropagation(); del(s.session_id); }} className="p-0.5 hover:text-red-400 rounded"><Trash2 className="h-3 w-3" /></span>
                        </div>
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-neutral-800/30 p-3 space-y-1">
          <div className="flex items-center gap-2 px-3 py-1 text-xs text-neutral-500">
            <div className="h-5 w-5 rounded-full bg-orange-500/20 text-orange-400 flex items-center justify-center text-[10px] font-bold">
              {getUsername().charAt(0).toUpperCase()}
            </div>
            <span className="flex-1 truncate">{getUsername()}</span>
            <button onClick={() => { clearUserAuth(); window.location.reload(); }} className="p-1 hover:text-red-400 rounded transition-colors" title="退出">
              <LogOut className="h-3 w-3" />
            </button>
          </div>
          <Link to="/settings" onClick={() => setOpen(false)} className="flex items-center gap-2.5 w-full rounded-xl px-3 py-2 text-xs text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/50 transition-all">
            <Settings className="h-3.5 w-3.5" /> 设置
          </Link>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="flex items-center shrink-0 border-b border-neutral-800/50 px-3 py-2.5 bg-neutral-950/50 backdrop-blur-xl">
          <button onClick={() => setOpen(!open)} className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800/50 transition-all md:hidden">
            <PanelLeft className="h-4 w-4" />
          </button>
          <span className="text-sm font-semibold tracking-tight ml-1 md:hidden">Orange Trade</span>
          <div className="flex-1" />
          <Link to="/settings" className="hidden md:flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/50 transition-all">
            <Settings className="h-3.5 w-3.5" /> 设置
          </Link>
        </header>

        <ConnectionBanner status={sseStatus} retryAttempt={sseRetryAttempt} />
        <main className="flex-1 overflow-hidden"><Outlet /></main>
      </div>
    </div>
  );
}

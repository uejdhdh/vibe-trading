import { Outlet, useLocation } from "react-router-dom";
import { Settings } from "lucide-react";
import { useAgentStore } from "@/stores/agent";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";

export function Layout() {
  const { pathname } = useLocation();
  const isSettings = pathname.startsWith("/settings");
  const sseStatus = useAgentStore((s) => s.sseStatus);
  const sseRetryAttempt = useAgentStore((s) => s.sseRetryAttempt);

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Minimal top bar — like ChatGPT */}
      <header className="flex items-center justify-between shrink-0 border-b border-border/40 px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
            <svg viewBox="0 0 24 24" className="h-4 w-4 text-white" fill="none">
              <circle cx="9" cy="11" r="2" fill="white" opacity="0.9"/>
              <circle cx="15" cy="11" r="2" fill="white" opacity="0.9"/>
              <path d="M6 9a4 4 0 0 0 6 0" stroke="white" strokeWidth="1.2" strokeLinecap="round" opacity="0.6"/>
            </svg>
          </div>
          <a href="/agent" className="text-sm font-semibold tracking-tight">
            Orange Trade
          </a>
        </div>
        <a
          href={isSettings ? "/agent" : "/settings"}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <Settings className="h-3.5 w-3.5" />
          {isSettings ? "返回对话" : "设置"}
        </a>
      </header>

      <ConnectionBanner status={sseStatus} retryAttempt={sseRetryAttempt} />

      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}

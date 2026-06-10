import { Outlet } from "react-router-dom";
import { Settings } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useAgentStore } from "@/stores/agent";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";

export function Layout() {
  const { pathname } = useLocation();
  const { dark, toggle } = useDarkMode();
  const sseStatus = useAgentStore((s) => s.sseStatus);
  const sseRetryAttempt = useAgentStore((s) => s.sseRetryAttempt);

  const isSettings = pathname.startsWith("/settings");

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Minimal header */}
      <header className="flex items-center justify-between shrink-0 border-b px-4 py-2.5">
        <div className="flex items-center gap-2">
          <a
            href="/agent"
            className="text-sm font-semibold tracking-tight hover:opacity-80"
          >
            Vibe-Trading
          </a>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={toggle}
            className="p-2 text-xs text-muted-foreground hover:text-foreground rounded transition-colors"
            title={dark ? "亮色模式" : "暗色模式"}
          >
            {dark ? "☀" : "☾"}
          </button>
          <a
            href={isSettings ? "/agent" : "/settings"}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <Settings className="h-3.5 w-3.5" />
            {isSettings ? "返回对话" : "设置"}
          </a>
        </div>
      </header>

      {/* Connection status */}
      <ConnectionBanner status={sseStatus} retryAttempt={sseRetryAttempt} />

      {/* Main */}
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}

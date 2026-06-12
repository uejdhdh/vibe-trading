import { useEffect, useRef, useState, useMemo, useCallback, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Send, Loader2, ArrowDown, Square } from "lucide-react";
import { toast } from "sonner";
import { useAgentStore } from "@/stores/agent";
import { useSSE } from "@/hooks/useSSE";
import { api } from "@/lib/api";
import type { AgentMessage } from "@/types/agent";
import { AgentAvatar } from "@/components/chat/AgentAvatar";
import { WelcomeScreen } from "@/components/chat/WelcomeScreen";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { ThinkingTimeline } from "@/components/chat/ThinkingTimeline";
import { ToolProgressIndicator } from "@/components/chat/ToolProgressIndicator";

/* ---------- Message grouping ---------- */
type MsgGroup =
  | { kind: "single"; msg: AgentMessage }
  | { kind: "timeline"; msgs: AgentMessage[] };

function groupMessages(msgs: AgentMessage[]): MsgGroup[] {
  const out: MsgGroup[] = [];
  let buf: AgentMessage[] = [];
  const flush = () => { if (buf.length) { out.push({ kind: "timeline", msgs: [...buf] }); buf = []; } };
  for (const m of msgs) {
    if (["thinking", "tool_call", "tool_result", "compact"].includes(m.type)) {
      buf.push(m);
    } else {
      flush();
      out.push({ kind: "single", msg: m });
    }
  }
  flush();
  return out;
}

const act = () => useAgentStore.getState();

export function Agent() {
  const [input, setInput] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isComposingRef = useRef(false);
  const lastCompositionEndRef = useRef(0);
  const sseSessionRef = useRef<string | null>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const lastEventRef = useRef(0);

  const messages = useAgentStore(s => s.messages);
  const streamingText = useAgentStore(s => s.streamingText);
  const status = useAgentStore(s => s.status);
  const sessionId = useAgentStore(s => s.sessionId);
  const toolCalls = useAgentStore(s => s.toolCalls);
  const sessionLoading = useAgentStore(s => s.sessionLoading);

  const { connect, disconnect } = useSSE();

  const urlSessionId = searchParams.get("session");

  const isNearBottom = useCallback(() => {
    const el = listRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  }, []);

  const scrollToBottom = useCallback(() => {
    if (!isNearBottom()) {
      setShowScrollBtn(true);
      return;
    }
    requestAnimationFrame(() => {
      if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    });
  }, [isNearBottom]);

  const forceScrollToBottom = useCallback(() => {
    setShowScrollBtn(false);
    requestAnimationFrame(() => {
      if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    });
  }, []);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const onScroll = () => {
      if (isNearBottom()) setShowScrollBtn(false);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isNearBottom]);

  const doDisconnect = useCallback(() => {
    disconnect();
    sseSessionRef.current = null;
  }, [disconnect]);

  const loadSessionMessages = useCallback(async (sid: string) => {
    try {
      const msgs = await api.getSessionMessages(sid);
      const agentMsgs: AgentMessage[] = [];
      for (const m of msgs) {
        const meta = m.metadata as Record<string, unknown> | undefined;
        const runId = meta?.run_id as string | undefined;
        const metrics = meta?.metrics as Record<string, number> | undefined;
        const ts = new Date(m.created_at).getTime();
        if (m.role === "user") {
          agentMsgs.push({ id: m.message_id, type: "user", content: m.content, timestamp: ts });
        } else if (runId) {
          if (m.content && m.content !== "Strategy execution completed.") {
            agentMsgs.push({ id: m.message_id + "_ans", type: "answer", content: m.content, timestamp: ts });
          }
          if (metrics && Object.keys(metrics).length > 0) {
            agentMsgs.push({ id: m.message_id, type: "run_complete", content: "", runId, metrics, timestamp: ts + 1 });
          }
        } else {
          agentMsgs.push({ id: m.message_id, type: "answer", content: m.content, timestamp: ts });
        }
      }
      act().loadHistory(agentMsgs);
      act().setSessionLoading(false);
      act().cacheSession(sid, agentMsgs);
      setTimeout(() => forceScrollToBottom(), 50);
    } catch {
      act().setSessionLoading(false);
    }
  }, [forceScrollToBottom]);

  const setupSSE = useCallback((sid: string) => {
    if (sseSessionRef.current === sid) return;
    disconnect();
    sseSessionRef.current = sid;
    const touch = () => { lastEventRef.current = Date.now(); };

    connect(api.sseUrl(sid, { replay: "active" }), {
      text_delta: (d) => { touch(); act().appendDelta(String(d.delta || "")); scrollToBottom(); },
      thinking_done: () => { touch(); },

      tool_call: (d) => {
        touch();
        act().addToolCall({
          id: String(d.tool || ""), tool: String(d.tool || ""),
          arguments: (d.arguments as Record<string, string>) ?? {},
          status: "running", timestamp: Date.now(),
        });
        scrollToBottom();
      },

      tool_result: (d) => {
        touch();
        act().updateToolCall(String(d.tool || ""), {
          status: d.status === "ok" ? "ok" : "error",
          preview: String(d.preview || ""),
          elapsed_ms: Number(d.elapsed_ms || 0),
          elapsed_s: undefined,
          progress: undefined,
        });
      },

      "attempt.completed": async (d) => {
        touch();
        const s = act();
        const completedTools = s.toolCalls;
        if (completedTools.length > 0) {
          for (const tc of completedTools) {
            s.addMessage({ id: tc.id + "_call", type: "tool_call", content: "", tool: tc.tool, args: tc.arguments, status: tc.status || "ok", timestamp: tc.timestamp });
            if (tc.elapsed_ms != null) {
              s.addMessage({ id: "", type: "tool_result", content: tc.preview || "", tool: tc.tool, status: tc.status || "ok", elapsed_ms: tc.elapsed_ms, timestamp: tc.timestamp + 1 });
            }
          }
        }
        s.clearStreaming();
        const summary = String(d.summary || "");
        if (summary) s.addMessage({ id: "", type: "answer", content: summary, timestamp: Date.now() });
        s.setStatus("idle");
        useAgentStore.setState({ toolCalls: [] });
        scrollToBottom();
      },

      "attempt.failed": (d) => {
        touch();
        act().clearStreaming();
        act().addMessage({ id: "", type: "error", content: String(d.error || "Execution failed"), timestamp: Date.now() });
        act().setStatus("idle");
        useAgentStore.setState({ toolCalls: [] });
        scrollToBottom();
      },

      heartbeat: () => {},
      reconnect: () => { act().setSseStatus("reconnecting"); },
    });
  }, [connect, disconnect, scrollToBottom]);

  useEffect(() => {
    const { sessionId: curSid, messages: curMsgs, cacheSession, reset, getCachedSession, switchSession } = act();

    if (urlSessionId && urlSessionId !== curSid) {
      doDisconnect();
      if (curSid && curMsgs.length > 0) cacheSession(curSid, curMsgs);
      const cached = getCachedSession(urlSessionId);
      switchSession(urlSessionId, cached);
      if (cached) {
        setTimeout(() => forceScrollToBottom(), 50);
      } else {
        loadSessionMessages(urlSessionId);
      }
      setupSSE(urlSessionId);
    } else if (!urlSessionId && curSid) {
      doDisconnect();
      if (curSid && curMsgs.length > 0) cacheSession(curSid, curMsgs);
      reset();
    }
  }, [urlSessionId, doDisconnect, loadSessionMessages, setupSSE, forceScrollToBottom]);

  useEffect(() => () => doDisconnect(), [doDisconnect]);

  const runPrompt = async (prompt: string) => {
    if (!prompt.trim() || status === "streaming") return;
    setInput("");
    act().addMessage({ id: "", type: "user", content: prompt, timestamp: Date.now() });
    act().setStatus("streaming");
    forceScrollToBottom();
    inputRef.current?.focus();

    try {
      let sid = act().sessionId;
      if (!sid) {
        const session = await api.createSession(prompt.slice(0, 50));
        sid = session.session_id;
        act().setSessionId(sid);
        setSearchParams({ session: sid }, { replace: true });
      }
      setupSSE(sid);
      await api.sendMessage(sid, prompt);
    } catch {
      act().setStatus("error");
      toast.error("发送失败，请重试");
      act().addMessage({ id: "", type: "error", content: "发送失败，请重试", timestamp: Date.now() });
    }
  };

  const handleSubmit = (e: FormEvent) => { e.preventDefault(); runPrompt(input.trim()); };

  const handleCancel = async () => {
    if (!sessionId) {
      act().setStatus("idle");
      return;
    }
    try {
      await api.cancelSession(sessionId);
      act().setStatus("idle");
      act().clearStreaming();
      useAgentStore.setState({ toolCalls: [] });
      toast.info("已取消");
    } catch {
      toast.error("取消失败");
    }
  };

  const groups = useMemo(() => groupMessages(messages), [messages]);

  /* Safety timeout: if streaming but no SSE event for 180s, reset to idle */
  useEffect(() => {
    if (status !== "streaming") return;
    const timer = setInterval(() => {
      if (lastEventRef.current && Date.now() - lastEventRef.current > 180_000 && act().status === "streaming") {
        act().setStatus("idle");
        useAgentStore.setState({ toolCalls: [] });
        toast.error("请求超时，请简化问题后重试");
      }
    }, 15_000);
    return () => clearInterval(timer);
  }, [status]);

  return (
    <div className="flex flex-col flex-1 min-w-0 overflow-hidden h-full">
      {/* Message list */}
      <div ref={listRef} className="flex-1 overflow-auto scroll-smooth relative">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
          {sessionLoading && (
            <div className="space-y-4 py-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="flex gap-3 animate-pulse">
                  <div className="h-7 w-7 rounded-full bg-muted shrink-0" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 bg-muted rounded w-3/4" />
                    <div className="h-3 bg-muted/60 rounded w-1/2" />
                  </div>
                </div>
              ))}
            </div>
          )}
          {!sessionLoading && messages.length === 0 && <WelcomeScreen />}

          {groups.map((g, i) => {
            if (g.kind === "timeline") {
              const isLast = i === groups.length - 1;
              return <ThinkingTimeline key={i} messages={g.msgs} isLatest={isLast && status === "streaming"} />;
            }
            return <MessageBubble key={g.msg.id || i} msg={g.msg} />;
          })}

          {/* Pre-stream placeholder */}
          {status === "streaming" && !streamingText && toolCalls.length === 0 && (
            <div className="flex gap-3">
              <AgentAvatar />
              <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
                <Loader2 className="h-3 w-3 animate-spin text-orange-500 shrink-0" />
                <span>思考中…</span>
              </div>
            </div>
          )}

          {/* Live streaming: text + tool progress */}
          {(streamingText || (status === "streaming" && toolCalls.length > 0)) && (
            <div className="flex gap-3">
              <AgentAvatar />
              <div className="flex-1 min-w-0 space-y-1.5">
                {streamingText && (
                  <div className="text-sm leading-relaxed">
                    {streamingText}
                    <span className="inline-block w-0.5 h-4 bg-orange-500 ml-0.5 animate-pulse align-middle" />
                  </div>
                )}
                {status === "streaming" && toolCalls.length > 0 && (
                  <ToolProgressIndicator toolCalls={toolCalls} />
                )}
              </div>
            </div>
          )}
        </div>

        {showScrollBtn && (
          <button
            onClick={forceScrollToBottom}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1 px-3 py-1.5 rounded-full bg-orange-500 text-white text-xs font-medium shadow-lg hover:bg-orange-600 transition-colors z-10"
          >
            <ArrowDown className="h-3 w-3" /> 新消息
          </button>
        )}
      </div>

      {/* Input area — ChatGPT/Claude style */}
      <div className="border-t bg-background/80 backdrop-blur-sm px-4 py-3">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="flex items-end gap-2 bg-card border rounded-2xl px-4 py-2 focus-within:border-orange-500/50 focus-within:ring-1 focus-within:ring-orange-500/20 transition-all">
            <textarea
              ref={inputRef}
              value={input}
              rows={1}
              onChange={(e) => {
                setInput(e.target.value);
                const el = e.target as HTMLTextAreaElement;
                el.style.height = "auto";
                el.style.height = Math.min(el.scrollHeight, 200) + "px";
              }}
              onCompositionStart={() => { isComposingRef.current = true; }}
              onCompositionEnd={() => {
                isComposingRef.current = false;
                lastCompositionEndRef.current = Date.now();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  const justFinished = Date.now() - lastCompositionEndRef.current < 80;
                  if (isComposingRef.current || justFinished) return;
                  e.preventDefault();
                  runPrompt(input.trim());
                }
              }}
              placeholder="输入你想分析的内容…"
              className="flex-1 bg-transparent text-sm resize-none outline-none placeholder:text-muted-foreground/60 py-1.5 max-h-[200px] overflow-y-auto"
              disabled={status === "streaming"}
            />
            {status === "streaming" ? (
              <button
                type="button"
                onClick={handleCancel}
                className="shrink-0 h-8 w-8 rounded-lg bg-orange-500 text-white flex items-center justify-center hover:bg-orange-600 transition-colors"
                title="停止"
              >
                <Square className="h-3.5 w-3.5" fill="currentColor" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="shrink-0 h-8 w-8 rounded-lg bg-orange-500 text-white flex items-center justify-center hover:bg-orange-600 transition-colors disabled:opacity-40"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <p className="text-[10px] text-muted-foreground/50 text-center mt-2">
            Orange Trade 仅供参考，不构成投资建议
          </p>
        </form>
      </div>
    </div>
  );
}

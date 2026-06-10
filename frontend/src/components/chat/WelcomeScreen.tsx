import { Bot } from "lucide-react";

export function WelcomeScreen() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] px-4">
      <div className="mb-6 h-14 w-14 rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-md">
        <Bot className="h-7 w-7 text-white" />
      </div>
      <h2 className="text-xl font-semibold tracking-tight mb-1">Orange Trade</h2>
      <p className="text-sm text-muted-foreground max-w-xs text-center leading-relaxed">
        你的 AI 量化交易助手。直接描述你想分析的股票或策略，我会帮你研究。
      </p>
    </div>
  );
}

export function AgentAvatar() {
  return (
    <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shrink-0 mt-0.5 select-none">
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none">
        <circle cx="9" cy="11" r="2" fill="white" opacity="0.9"/>
        <circle cx="15" cy="11" r="2" fill="white" opacity="0.9"/>
        <path d="M6 9a4 4 0 0 0 6 0" stroke="white" strokeWidth="1.2" strokeLinecap="round" opacity="0.6"/>
      </svg>
    </div>
  );
}

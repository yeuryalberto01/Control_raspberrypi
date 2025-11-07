interface StatCardProps {
  title: string;
  value: string;
  hint?: string;
  status?: "default" | "warn" | "alert";
  color?: string;
  onClick?: () => void;
  onDoubleClick?: () => void;
}

const STATUS_STYLES: Record<NonNullable<StatCardProps["status"]>, string> = {
  default: "border-slate-800",
  warn: "border-amber-500/60",
  alert: "border-rose-500/60",
};

export default function StatCard({
  title,
  value,
  hint,
  status = "default",
  color = "bg-slate-900/70",
  onClick,
  onDoubleClick,
}: StatCardProps) {
  return (
    <div
      className={`rounded-xl border p-4 transition cursor-pointer hover:scale-[1.01] ${STATUS_STYLES[status]} ${color}`}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          if (onClick) {
            onClick();
          }
          if (onDoubleClick) {
            onDoubleClick();
          }
        }
      }}
    >
      <div className="text-sm text-slate-300">{title}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-50">{value}</div>
      {hint ? <div className="mt-1 text-xs text-slate-400">{hint}</div> : null}
    </div>
  );
}

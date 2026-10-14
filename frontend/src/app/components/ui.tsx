import type { DocumentStatus } from "@/lib/api";

export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export const STATUS_META: Record<
  DocumentStatus,
  { label: string; text: string; ring: string; dot: string; bar: string; hex: string }
> = {
  uploaded: {
    label: "Uploaded",
    text: "text-amber-600 dark:text-amber-400",
    ring: "ring-amber-500/30",
    dot: "bg-amber-500",
    bar: "bg-amber-500",
    hex: "#f59e0b",
  },
  chunked: {
    label: "Chunked",
    text: "text-sky-600 dark:text-sky-400",
    ring: "ring-sky-500/30",
    dot: "bg-sky-500",
    bar: "bg-sky-500",
    hex: "#0ea5e9",
  },
  indexed: {
    label: "Indexed",
    text: "text-emerald-600 dark:text-emerald-400",
    ring: "ring-emerald-500/30",
    dot: "bg-emerald-500",
    bar: "bg-emerald-500",
    hex: "#10b981",
  },
  failed: {
    label: "Failed",
    text: "text-rose-600 dark:text-rose-400",
    ring: "ring-rose-500/30",
    dot: "bg-rose-500",
    bar: "bg-rose-500",
    hex: "#f43f5e",
  },
};

export function Card({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function StatusPill({ status }: { status: DocumentStatus }) {
  const m = STATUS_META[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full bg-white/60 px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset dark:bg-white/5",
        m.text,
        m.ring,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", m.dot)} />
      {m.label}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("animate-spin", className ?? "h-4 w-4")}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

export function ProgressBar({ value, total }: { value: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-200/80 dark:bg-zinc-800">
      <div
        className="h-full rounded-full bg-emerald-500 transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function Alert({
  kind,
  children,
}: {
  kind: "error" | "success" | "info";
  children: React.ReactNode;
}) {
  const styles = {
    error: "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
    success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    info: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  }[kind];
  return <div className={cn("rounded-xl border px-3 py-2 text-sm", styles)}>{children}</div>;
}

export function StatCard({
  label,
  value,
  sub,
  dot,
  tone,
}: {
  label: string;
  value: string | number;
  sub?: string;
  dot?: string;
  tone?: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        {dot && <span className={cn("h-2 w-2 rounded-full", dot)} />}
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      </div>
      <p
        className={cn(
          "mt-2 text-2xl font-semibold tabular-nums",
          tone ?? "text-zinc-900 dark:text-zinc-50",
        )}
      >
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-zinc-500">{sub}</p>}
    </Card>
  );
}

export function Donut({
  segments,
  total,
  center,
  caption,
}: {
  segments: { value: number; color: string }[];
  total: number;
  center: string | number;
  caption?: string;
}) {
  let acc = 0;
  const stops = segments
    .filter((s) => s.value > 0)
    .map((s) => {
      const start = (acc / total) * 360;
      acc += s.value;
      const end = (acc / total) * 360;
      return `${s.color} ${start}deg ${end}deg`;
    });
  const background =
    total > 0 && stops.length
      ? `conic-gradient(${stops.join(", ")})`
      : "conic-gradient(#d4d4d8 0deg 360deg)";

  return (
    <div className="relative grid h-36 w-36 place-items-center">
      <div className="h-36 w-36 rounded-full" style={{ background }} />
      <div className="absolute grid h-[6.5rem] w-[6.5rem] place-items-center rounded-full bg-white text-center shadow-inner dark:bg-zinc-900">
        <div>
          <p className="text-2xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
            {center}
          </p>
          {caption && <p className="text-[0.65rem] uppercase tracking-wide text-zinc-500">{caption}</p>}
        </div>
      </div>
    </div>
  );
}

"use client";

import type { DocumentStatus, Overview } from "@/lib/api";
import { Card, Donut, Spinner, StatCard, STATUS_META, cn } from "./ui";

const STATUS_ORDER: DocumentStatus[] = ["indexed", "chunked", "uploaded", "failed"];

export default function StatisticsPanel({ overview }: { overview: Overview | null }) {
  if (!overview) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-zinc-500">
        <Spinner /> Loading statistics…
      </div>
    );
  }

  const docs = overview.documents;
  const total = overview.total_documents || 0;
  const indexed = docs.indexed ?? 0;
  const progress = total > 0 ? Math.round((indexed / total) * 100) : 0;
  const chunkProgress =
    overview.total_chunks > 0
      ? Math.round((overview.indexed_chunks / overview.total_chunks) * 100)
      : 0;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="mb-4 text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Pipeline status
          </h3>
          <div className="flex items-center gap-6">
            <Donut
              total={total}
              center={total}
              caption="docs"
              segments={STATUS_ORDER.map((s) => ({
                value: docs[s] ?? 0,
                color: STATUS_META[s].hex,
              }))}
            />
            <ul className="flex-1 space-y-2.5">
              {STATUS_ORDER.map((s) => {
                const n = docs[s] ?? 0;
                const pct = total > 0 ? Math.round((n / total) * 100) : 0;
                return (
                  <li key={s} className="flex items-center gap-2 text-sm">
                    <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", STATUS_META[s].dot)} />
                    <span className="text-zinc-600 dark:text-zinc-400">{STATUS_META[s].label}</span>
                    <span className="ml-auto font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
                      {n}
                    </span>
                    <span className="w-9 text-right text-xs tabular-nums text-zinc-400">{pct}%</span>
                  </li>
                );
              })}
            </ul>
          </div>
        </Card>

        <div className="grid grid-cols-2 gap-3">
          <StatCard label="Documents" value={total} />
          <StatCard
            label="Indexed"
            value={indexed}
            sub={`${progress}% complete`}
            dot={STATUS_META.indexed.dot}
            tone={STATUS_META.indexed.text}
          />
          <StatCard label="Total chunks" value={overview.total_chunks} />
          <StatCard
            label="Vectors"
            value={overview.vectors ?? "—"}
            sub={overview.vectors === null ? "collecting…" : "in Qdrant"}
          />
          <div className="col-span-2">
            <StatCard
              label="Embedder"
              value={overview.embedder}
              sub={`dim ${overview.embedder_dim} · collection “${overview.collection}”`}
            />
          </div>
        </div>
      </div>

      <Card className="p-5">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Indexing progress</h3>
          <span className="text-sm font-medium tabular-nums text-zinc-500">{chunkProgress}%</span>
        </div>
        {overview.total_chunks === 0 ? (
          <p className="py-4 text-center text-sm text-zinc-500">Nothing has been chunked yet.</p>
        ) : (
          <>
            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200/80 dark:bg-zinc-800">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${Math.min(100, chunkProgress)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              {overview.indexed_chunks.toLocaleString()} of{" "}
              {overview.total_chunks.toLocaleString()} chunks embedded
            </p>
          </>
        )}
      </Card>
    </div>
  );
}

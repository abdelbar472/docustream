"use client";

import { memo } from "react";
import type { Document, DocumentStatus } from "@/lib/api";
import { Alert, Card, ProgressBar, Spinner, StatusPill, cn } from "./ui";

const FILTERS: (DocumentStatus | "all")[] = ["all", "uploaded", "chunked", "indexed", "failed"];

function timeAgo(iso: string) {
  const then = new Date(iso.replace(" ", "T") + "Z").getTime();
  if (Number.isNaN(then)) return iso;
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function DocumentList({
  documents,
  loading,
  error,
  filter,
  onFilterChange,
  onRefresh,
}: {
  documents: Document[];
  loading: boolean;
  error: string | null;
  filter: DocumentStatus | "all";
  onFilterChange: (f: DocumentStatus | "all") => void;
  onRefresh: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex flex-wrap gap-1 rounded-full border border-zinc-200/80 bg-white p-1 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => onFilterChange(f)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors",
                filter === f
                  ? "bg-zinc-900 text-white shadow-sm dark:bg-zinc-100 dark:text-zinc-900"
                  : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100",
              )}
            >
              {f}
            </button>
          ))}
        </div>
        <button
          onClick={onRefresh}
          className="inline-flex items-center gap-2 rounded-full border border-zinc-200/80 bg-white px-3.5 py-1.5 text-xs font-medium text-zinc-700 shadow-sm transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          {loading && <Spinner className="h-3 w-3" />}
          Refresh
        </button>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      {documents.length === 0 && !loading ? (
        <Card className="px-6 py-12 text-center">
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">No documents yet</p>
          <p className="mt-1 text-sm text-zinc-500">
            {filter !== "all"
              ? `Nothing with status “${filter}”.`
              : "Head to the Upload tab to add your first document."}
          </p>
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {documents.map((doc) => (
            <li key={doc.id}>
              <Card className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                      {doc.filename}
                    </p>
                    <p className="mt-0.5 font-mono text-xs text-zinc-400">{doc.id.slice(0, 12)}…</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="hidden text-xs text-zinc-400 sm:inline">
                      {timeAgo(doc.updated_at)}
                    </span>
                    <StatusPill status={doc.status} />
                  </div>
                </div>

                {doc.status !== "failed" && doc.total_chunks > 0 && (
                  <div className="mt-3">
                    <div className="mb-1 flex justify-between text-xs text-zinc-500">
                      <span>
                        {doc.indexed_chunks} / {doc.total_chunks} chunks indexed
                      </span>
                      <span className="tabular-nums">
                        {Math.round((doc.indexed_chunks / doc.total_chunks) * 100)}%
                      </span>
                    </div>
                    <ProgressBar value={doc.indexed_chunks} total={doc.total_chunks} />
                  </div>
                )}

                {doc.status === "uploaded" && (
                  <p className="mt-3 text-xs text-zinc-500">Waiting for the chunker…</p>
                )}

                {doc.error && (
                  <p className="mt-3 rounded-lg bg-rose-500/10 px-2.5 py-1.5 font-mono text-xs text-rose-600 dark:text-rose-400">
                    {doc.error}
                  </p>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default memo(DocumentList);

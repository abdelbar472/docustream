"use client";

import { useState } from "react";
import { search, type SearchResult } from "@/lib/api";
import { Alert, Card, Spinner } from "./ui";

const EXAMPLES = [
  "how do consumer groups share partitions",
  "dead letter topic retries",
  "idempotent processing",
];

const inputClass =
  "w-full rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-900 shadow-sm outline-none transition-colors placeholder:text-zinc-400 focus:border-zinc-400 focus:ring-4 focus:ring-zinc-900/5 dark:border-zinc-800 dark:bg-zinc-950/50 dark:text-zinc-100 dark:focus:border-zinc-600 dark:focus:ring-white/5";

export default function SearchPanel() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchedFor, setSearchedFor] = useState("");

  async function run(q: string) {
    const term = q.trim();
    if (!term) return;
    setBusy(true);
    setError(null);
    try {
      const res = await search(term, 5);
      setResults(res);
      setSearchedFor(term);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResults(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(query);
        }}
        className="flex gap-2"
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the indexed chunks…"
          className={inputClass}
        />
        <button
          type="submit"
          disabled={busy || !query.trim()}
          className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          {busy && <Spinner />}
          Search
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setQuery(ex);
              run(ex);
            }}
            className="rounded-full border border-zinc-200/80 bg-white px-3 py-1 text-xs text-zinc-600 shadow-sm transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            {ex}
          </button>
        ))}
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      {results && !error && (
        <div className="space-y-3">
          <p className="text-xs text-zinc-500">
            {results.length} result{results.length === 1 ? "" : "s"} for “{searchedFor}”
          </p>
          {results.length === 0 && (
            <Card className="px-6 py-10 text-center text-sm text-zinc-500">
              Nothing matched. Upload a document first.
            </Card>
          )}
          {results.map((r, i) => (
            <Card key={`${r.doc_id}-${r.chunk_index}`} className="p-4">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-zinc-900 text-[0.65rem] font-semibold text-white dark:bg-zinc-100 dark:text-zinc-900">
                    {i + 1}
                  </span>
                  <span className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    {r.filename}
                  </span>
                  <span className="shrink-0 text-xs text-zinc-400">chunk {r.chunk_index}</span>
                </div>
                <span className="shrink-0 rounded-full bg-emerald-500/10 px-2 py-0.5 font-mono text-xs text-emerald-600 ring-1 ring-inset ring-emerald-500/30 dark:text-emerald-400">
                  {r.score.toFixed(3)}
                </span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                {r.text.length > 480 ? `${r.text.slice(0, 480)}…` : r.text}
              </p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

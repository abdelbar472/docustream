"use client";

import { useEffect, useState } from "react";
import { search, type SearchResponse, type SearchResult } from "@/lib/api";
import { Alert, Card, Spinner, cn } from "./ui";

const EXAMPLES = [
  "how do consumer groups share partitions",
  "dead letter topic retries",
  "idempotent processing",
];

const LIMITS = [5, 10, 20];

const inputClass =
  "w-full rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-900 shadow-sm outline-none transition-colors placeholder:text-zinc-400 focus:border-zinc-400 focus:ring-4 focus:ring-zinc-900/5 dark:border-zinc-800 dark:bg-zinc-950/50 dark:text-zinc-100 dark:focus:border-zinc-600 dark:focus:ring-white/5";

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function Highlight({ text, terms }: { text: string; terms: string[] }) {
  if (terms.length === 0) return <>{text}</>;
  const re = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(re);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark
            key={i}
            className="rounded bg-amber-200/80 px-0.5 text-zinc-900 dark:bg-amber-300/30 dark:text-amber-100"
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

function pct(score: number) {
  return Math.max(0, Math.min(100, Math.round(score * 100)));
}

export default function SearchPanel() {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(5);
  const [facet, setFacet] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // Live search: debounce keystrokes, cancel any in-flight request when the
  // query/filter changes so late responses can't overwrite newer ones.
  useEffect(() => {
    const term = query.trim();
    if (!term) return;
    const controller = new AbortController();
    let cancelled = false;
    const timer = setTimeout(async () => {
      setBusy(true);
      try {
        const res = await search(term, limit, {
          filename: facet ?? undefined,
          signal: controller.signal,
        });
        if (!cancelled) {
          setData(res);
          setResults(res.results);
          setError(null);
        }
      } catch (e) {
        if (!cancelled && !controller.signal.aborted) {
          setError(e instanceof Error ? e.message : String(e));
          setData(null);
          setResults([]);
        }
      } finally {
        if (!cancelled) setBusy(false);
      }
    }, 320);
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [query, limit, facet, nonce]);

  function updateQuery(value: string) {
    setQuery(value);
    setFacet(null);
    if (!value.trim()) {
      setData(null);
      setResults([]);
      setError(null);
      setBusy(false);
    }
  }

  async function loadMore() {
    const term = query.trim();
    if (!term || !data || results.length >= data.total) return;
    setLoadingMore(true);
    try {
      const res = await search(term, limit, { filename: facet ?? undefined, offset: results.length });
      setData(res);
      setResults((prev) => [...prev, ...res.results]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMore(false);
    }
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const terms = data?.terms ?? [];
  const facets = data?.facets ?? [];
  const corrections = data?.corrections ?? [];
  const term = query.trim();
  const hasMore = !!data && results.length < data.total;

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setNonce((n) => n + 1);
        }}
        className="flex gap-2"
      >
        <div className="relative flex-1">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.6" />
            <path d="m20 20-3.2-3.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <input
            value={query}
            onChange={(e) => updateQuery(e.target.value)}
            placeholder="Search the indexed chunks…"
            className={cn(inputClass, "pl-9 pr-9")}
          />
          {query && (
            <button
              type="button"
              onClick={() => updateQuery("")}
              className="absolute right-2.5 top-1/2 grid h-5 w-5 -translate-y-1/2 place-items-center rounded-full text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800"
              aria-label="Clear search"
            >
              <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5">
                <path
                  d="M6 6l12 12M18 6 6 18"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          )}
        </div>
        <button
          type="submit"
          disabled={busy || !term}
          className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          {busy && <Spinner />}
          Search
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-zinc-500">Results</span>
        <div className="inline-flex gap-1 rounded-full border border-zinc-200/80 bg-white p-0.5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60">
          {LIMITS.map((n) => (
            <button
              key={n}
              onClick={() => setLimit(n)}
              className={cn(
                "rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
                limit === n
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                  : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100",
              )}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {!term && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => updateQuery(ex)}
              className="rounded-full border border-zinc-200/80 bg-white px-3 py-1 text-xs text-zinc-600 shadow-sm transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-400 dark:hover:bg-zinc-800"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      {error && <Alert kind="error">{error}</Alert>}

      {!error && term && data && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-zinc-500">
              {data.total} result{data.total === 1 ? "" : "s"} for “{data.query}”
            </p>
            {corrections.length > 0 && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                auto-corrected: {corrections.map((c) => `“${c}”`).join(", ")}
              </p>
            )}
          </div>

          {facets.length > 1 && (
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => setFacet(null)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                  facet === null
                    ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                    : "border-zinc-200/80 bg-white text-zinc-600 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-400 dark:hover:bg-zinc-800",
                )}
              >
                All files
              </button>
              {facets.map((f) => (
                <button
                  key={f.filename}
                  onClick={() => setFacet(facet === f.filename ? null : f.filename)}
                  className={cn(
                    "inline-flex max-w-[16rem] items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                    facet === f.filename
                      ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                      : "border-zinc-200/80 bg-white text-zinc-600 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-400 dark:hover:bg-zinc-800",
                  )}
                  title={f.filename}
                >
                  <span className="truncate">{f.filename}</span>
                  <span className="shrink-0 opacity-60">{f.count}</span>
                </button>
              ))}
            </div>
          )}

          {results.length === 0 && (
            <Card className="px-6 py-10 text-center text-sm text-zinc-500">
              Nothing matched. Try different words or upload a document first.
            </Card>
          )}

          {results.map((r) => {
            const key = `${r.doc_id}-${r.chunk_index}`;
            const isOpen = expanded.has(key);
            return (
              <Card key={key} className="p-4">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                      {r.filename}
                    </span>
                    <span className="shrink-0 text-xs text-zinc-400">chunk {r.chunk_index}</span>
                    {terms.length > 0 && r.match > 0 && (
                      <span className="shrink-0 rounded-full bg-zinc-100 px-1.5 py-0.5 text-[0.65rem] font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                        {pct(r.match)}% match
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <div className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-zinc-200/80 sm:block dark:bg-zinc-800">
                      <div className="h-full rounded-full bg-emerald-500" style={{ width: `${pct(r.score)}%` }} />
                    </div>
                    <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 font-mono text-xs text-emerald-600 ring-1 ring-inset ring-emerald-500/30 dark:text-emerald-400">
                      {r.score.toFixed(3)}
                    </span>
                  </div>
                </div>

                <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                  {isOpen ? <Highlight text={r.text} terms={terms} /> : <Highlight text={r.snippet} terms={terms} />}
                </p>

                <button
                  onClick={() => toggle(key)}
                  className="mt-2 text-xs font-medium text-zinc-500 transition-colors hover:text-zinc-800 dark:hover:text-zinc-200"
                >
                  {isOpen ? "Show less" : "Show full chunk"}
                </button>
              </Card>
            );
          })}

          {hasMore && (
            <div className="flex justify-center pt-1">
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="inline-flex items-center gap-2 rounded-xl border border-zinc-200/80 bg-white px-4 py-2 text-sm font-medium text-zinc-700 shadow-sm transition-colors hover:bg-zinc-50 disabled:opacity-60 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                {loadingMore && <Spinner />}
                Load more ({data.total - results.length})
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

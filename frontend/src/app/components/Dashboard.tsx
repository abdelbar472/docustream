"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getHealth,
  getOverview,
  listDocuments,
  type Document,
  type DocumentStatus,
  type Health,
  type Overview,
} from "@/lib/api";
import { cn, Spinner, StatCard, STATUS_META } from "./ui";
import UploadPanel from "./UploadPanel";
import DocumentList from "./DocumentList";
import SearchPanel from "./SearchPanel";
import StatisticsPanel from "./StatisticsPanel";

type Tab = "documents" | "upload" | "search" | "stats";

const TABS: { id: Tab; label: string }[] = [
  { id: "documents", label: "Documents" },
  { id: "upload", label: "Upload" },
  { id: "search", label: "Search" },
  { id: "stats", label: "Statistics" },
];

// While something is still moving through the pipeline, poll quickly; otherwise back off.
const ACTIVE_MS = 1500;
const IDLE_MS = 8000;

function usePageVisible() {
  const [visible, setVisible] = useState(
    () => typeof document === "undefined" || !document.hidden,
  );
  useEffect(() => {
    const onVisibility = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);
  return visible;
}

function BrandMark() {
  return (
    <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-zinc-900 text-white shadow-sm dark:bg-zinc-100 dark:text-zinc-900">
      <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
        <path
          d="M4 7.5 12 3l8 4.5M4 7.5 12 12m-8-4.5v9L12 21m8-13.5L12 12m8-4.5v9L12 21m0-9v9"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("documents");
  const [health, setHealth] = useState<Health | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [docsError, setDocsError] = useState<string | null>(null);
  const [filter, setFilter] = useState<DocumentStatus | "all">("all");
  const [apiDown, setApiDown] = useState(false);

  const visible = usePageVisible();

  // Signatures let us skip state updates (and re-renders) when nothing changed.
  const docsSig = useRef("");
  const overviewSig = useRef("");
  const healthSig = useRef("");

  const fetchDocuments = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const docs = await listDocuments(filter, 50, signal);
        const sig = JSON.stringify(docs);
        if (sig !== docsSig.current) {
          docsSig.current = sig;
          setDocuments(docs);
        }
        setDocsError((prev) => (prev === null ? prev : null));
        setApiDown((prev) => (prev ? false : prev));
      } catch (e) {
        if (signal?.aborted) return;
        const msg = e instanceof Error ? e.message : String(e);
        setDocsError((prev) => (prev === msg ? prev : msg));
        setApiDown((prev) => (prev ? prev : true));
      } finally {
        if (!signal?.aborted) setDocsLoading((prev) => (prev ? false : prev));
      }
    },
    [filter],
  );

  const handleRefresh = useCallback(() => {
    setDocsLoading(true);
    void fetchDocuments();
  }, [fetchDocuments]);

  const handleFilterChange = useCallback((next: DocumentStatus | "all") => {
    setDocsLoading(true);
    setFilter(next);
  }, []);

  const uploaded = overview?.documents.uploaded ?? 0;
  const chunked = overview?.documents.chunked ?? 0;
  const inFlight = uploaded + chunked;
  const total = overview?.total_documents ?? 0;

  // Document list: only while the Documents tab is visible. Faster cadence while
  // documents are still processing, slower once everything has settled.
  useEffect(() => {
    if (tab !== "documents" || !visible) return;
    const controller = new AbortController();
    let running = false;
    const tick = async () => {
      if (running) return;
      running = true;
      await fetchDocuments(controller.signal);
      running = false;
    };
    const interval = inFlight > 0 ? ACTIVE_MS : IDLE_MS;
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, interval);
    return () => {
      controller.abort();
      clearTimeout(first);
      clearInterval(id);
    };
  }, [tab, visible, inFlight, fetchDocuments]);

  // Header health + aggregate statistics.
  useEffect(() => {
    if (!visible) return;
    const controller = new AbortController();
    let running = false;
    const tick = async () => {
      if (running) return;
      running = true;
      try {
        const [h, o] = await Promise.all([
          getHealth(controller.signal),
          getOverview(controller.signal),
        ]);
        const oSig = JSON.stringify(o);
        if (oSig !== overviewSig.current) {
          overviewSig.current = oSig;
          setOverview(o);
        }
        const hSig = JSON.stringify(h);
        if (hSig !== healthSig.current) {
          healthSig.current = hSig;
          setHealth(h);
        }
        setApiDown((prev) => (prev ? false : prev));
      } catch {
        if (!controller.signal.aborted) setApiDown((prev) => (prev ? prev : true));
      } finally {
        running = false;
      }
    };
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 4000);
    return () => {
      controller.abort();
      clearTimeout(first);
      clearInterval(id);
    };
  }, [visible]);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6 sm:py-12">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <BrandMark />
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              DocuStream
            </h1>
            <p className="text-sm text-zinc-500">
              Real-time ingestion &amp; semantic search
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {health && !apiDown && (
            <span className="hidden rounded-full border border-zinc-200/80 bg-white px-3 py-1 text-xs text-zinc-600 sm:inline dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-400">
              embedder <span className="font-mono text-zinc-800 dark:text-zinc-200">{health.embedder}</span>
            </span>
          )}
          <span
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset",
              apiDown
                ? "bg-rose-500/10 text-rose-600 ring-rose-500/30 dark:text-rose-400"
                : "bg-emerald-500/10 text-emerald-600 ring-emerald-500/30 dark:text-emerald-400",
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                apiDown ? "bg-rose-500" : "animate-pulse bg-emerald-500",
              )}
            />
            {apiDown ? "Offline" : "Online"}
          </span>
        </div>
      </header>

      <section className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Documents" value={total} />
        <StatCard
          label="Indexed"
          value={overview?.documents.indexed ?? 0}
          dot={STATUS_META.indexed.dot}
          tone={STATUS_META.indexed.text}
        />
        <StatCard
          label="In flight"
          value={inFlight}
          dot={STATUS_META.chunked.dot}
          tone={STATUS_META.chunked.text}
        />
        <StatCard
          label="Failed"
          value={overview?.documents.failed ?? 0}
          dot={STATUS_META.failed.dot}
          tone={STATUS_META.failed.text}
        />
      </section>

      <div className="mb-6 flex items-center gap-3 overflow-x-auto">
        <nav className="inline-flex shrink-0 gap-1 rounded-full border border-zinc-200/80 bg-white p-1 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
                tab === t.id
                  ? "bg-zinc-900 text-white shadow-sm dark:bg-zinc-100 dark:text-zinc-900"
                  : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100",
              )}
            >
              {t.label}
            </button>
          ))}
        </nav>
        {docsLoading && tab === "documents" && (
          <Spinner className="h-4 w-4 text-zinc-400" />
        )}
      </div>

      <div>
        {tab === "documents" && (
          <DocumentList
            documents={documents}
            loading={docsLoading}
            error={docsError}
            filter={filter}
            onFilterChange={handleFilterChange}
            onRefresh={handleRefresh}
          />
        )}
        {tab === "upload" && (
          <UploadPanel
            onUploaded={() => {
              handleRefresh();
              setTab("documents");
            }}
          />
        )}
        {tab === "search" && <SearchPanel />}
        {tab === "stats" && <StatisticsPanel overview={overview} />}
      </div>

      <footer className="mt-16 text-center text-xs text-zinc-400">
        Kafka UI on <span className="font-mono">:8080</span> · Qdrant on{" "}
        <span className="font-mono">:6333</span>
      </footer>
    </div>
  );
}

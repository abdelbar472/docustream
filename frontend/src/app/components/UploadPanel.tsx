"use client";

import { useRef, useState } from "react";
import { uploadFile, uploadText } from "@/lib/api";
import { Alert, Card, Spinner, cn } from "./ui";

type Mode = "file" | "text";

const inputClass =
  "w-full rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-900 shadow-sm outline-none transition-colors placeholder:text-zinc-400 focus:border-zinc-400 focus:ring-4 focus:ring-zinc-900/5 dark:border-zinc-800 dark:bg-zinc-950/50 dark:text-zinc-100 dark:focus:border-zinc-600 dark:focus:ring-white/5";

export default function UploadPanel({ onUploaded }: { onUploaded: () => void }) {
  const [mode, setMode] = useState<Mode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("untitled.txt");
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setFile(null);
    setText("");
    setTitle("untitled.txt");
    if (inputRef.current) inputRef.current.value = "";
  }

  async function submit() {
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      if (mode === "file") {
        if (!file) throw new Error("Choose a .txt or .md file first.");
        const res = await uploadFile(file);
        setSuccess(`Queued “${res.filename}” (${res.doc_id.slice(0, 8)}…) — watch it move to indexed.`);
      } else {
        if (!text.trim()) throw new Error("Paste some text first.");
        const res = await uploadText(title.trim() || "untitled.txt", text);
        setSuccess(`Queued “${res.filename}” (${res.doc_id.slice(0, 8)}…) — watch it move to indexed.`);
      }
      reset();
      onUploaded();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <div className="mb-4 inline-flex gap-1 rounded-full bg-zinc-100 p-1 text-sm dark:bg-zinc-950/60">
        {(["file", "text"] as Mode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn(
              "rounded-full px-3.5 py-1.5 font-medium transition-colors",
              mode === m
                ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-zinc-100"
                : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100",
            )}
          >
            {m === "file" ? "Upload file" : "Paste text"}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        {mode === "file" ? (
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const dropped = e.dataTransfer.files?.[0];
              if (dropped) setFile(dropped);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors",
              dragging
                ? "border-zinc-900 bg-zinc-900/5 dark:border-zinc-300 dark:bg-white/5"
                : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-800 dark:hover:border-zinc-700",
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6 text-zinc-400" aria-hidden="true">
              <path
                d="M12 16V4m0 0L8 8m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {file ? file.name : "Drop a .txt / .md file here"}
            </span>
            <span className="text-xs text-zinc-500">
              {file
                ? `${(file.size / 1024).toFixed(1)} KB`
                : "or click to browse · max 500 KB"}
            </span>
          </label>
        ) : (
          <div className="space-y-3">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="title.txt"
              className={inputClass}
            />
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={8}
              placeholder="Paste document text…"
              className={cn(inputClass, "resize-y font-mono")}
            />
          </div>
        )}

        {error && <Alert kind="error">{error}</Alert>}
        {success && <Alert kind="success">{success}</Alert>}

        <button
          onClick={submit}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          {busy && <Spinner />}
          {busy ? "Uploading…" : "Upload"}
        </button>
      </div>
    </Card>
  );
}

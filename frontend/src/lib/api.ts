export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export type DocumentStatus = "uploaded" | "chunked" | "indexed" | "failed";

export interface Document {
  id: string;
  filename: string;
  status: DocumentStatus;
  total_chunks: number;
  error: string | null;
  created_at: string;
  updated_at: string;
  indexed_chunks: number;
}

export interface SearchResult {
  score: number;
  doc_id: string;
  filename: string;
  chunk_index: number;
  text: string;
}

export interface Health {
  status: string;
  bootstrap: string;
  embedder: string;
}

export interface Overview {
  documents: Record<DocumentStatus, number>;
  total_documents: number;
  total_chunks: number;
  indexed_chunks: number;
  vectors: number | null;
  embedder: string;
  embedder_dim: number;
  collection: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch (e) {
    if (init?.signal?.aborted) throw e;
    throw new Error(
      `Cannot reach the API at ${API_URL}. Is it running and is CORS_ORIGINS set?`,
    );
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = body.detail[0]?.msg ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function getHealth(signal?: AbortSignal) {
  return request<Health>("/health", { signal });
}

export function getStats(signal?: AbortSignal) {
  return request<Record<string, number>>("/stats", { signal });
}

export function getOverview(signal?: AbortSignal) {
  return request<Overview>("/stats/overview", { signal });
}

export async function listDocuments(
  status?: DocumentStatus | "all",
  limit = 50,
  signal?: AbortSignal,
) {
  const query = status && status !== "all" ? `?status=${status}&limit=${limit}` : `?limit=${limit}`;
  const data = await request<{ count: number; documents: Document[] }>(`/documents${query}`, {
    signal,
  });
  return data.documents;
}

export function uploadFile(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<{ doc_id: string; filename: string; status: string }>("/documents", {
    method: "POST",
    body: form,
  });
}

export function uploadText(title: string, text: string) {
  return request<{ doc_id: string; filename: string; status: string }>("/documents/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text }),
  });
}

export async function search(q: string, limit = 5) {
  const data = await request<{ query: string; count: number; results: SearchResult[] }>(
    `/search?q=${encodeURIComponent(q)}&limit=${limit}`,
  );
  return data.results;
}

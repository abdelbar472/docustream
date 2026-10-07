---
tags:
  - project
  - uses/groq
  - uses/sqlite
  - uses/rag
---
# AI Knowledge Base

A personal **RAG knowledge base** that turns a folder of Markdown notes into a searchable semantic index you can ask questions against — no note left unindexed.

Ask it "What is Khaled's preferred frontend framework?" and it answers from the notes (with sources) — **Next.js**.

---

## What it is

A single FastAPI app (no frontend) that:

- **Indexes** every `.md` note in `Portfolio/**`, splits it into chunks, embeds each chunk (`all-MiniLM-L6-v2`), and stores it in Qdrant.
- **Auto-re-ingests** on note add/edit/delete via a `watchfiles` watcher — only changed files are re-embedded.
- **Answers** with RAG: retrieves the most relevant chunks and lets Groq's `gpt-oss-20b` synthesize the answer from that context only.
- **Never asks the LLM the same question twice** — every Q→A is cached in local SQLite (`_local_qa_cache.sqlite3`), so a repeated question is answered instantly with no retrieval, no Qdrant, no LLM. A vector `qa_memory` collection catches near-duplicate re-asks.
- **Remembers what it can't do** — a capability gate cross-checks technologies named in "can X do Y?" questions against the notes and answers "No, not in the stack" instead of hallucinating.

---

## Architecture

`/ask` is a compiled **LangGraph** state graph. Each node reads/writes the shared `AskState` and short-circuits as early as possible:

`gate → local_cache → qa_memory → retrieve → (direct | llm)`

- **gate** — named tech absent from the KB → immediate "No", no retrieval, no LLM.
- **local_cache** — exact (normalized) question in SQLite → cached answer.
- **qa_memory** — vector-similar stored Q→A (score ≥ 0.82) → reused answer.
- **retrieve** — hybrid rerank: dense cosine + keyword boosts on body/source-path/frontmatter (category/summary/tech), so short notes like `React.md` beat generic hub pages.
- **direct_answer** — top chunk ≥ 0.90 → raw chunk, no LLM.
- **llm_answer** — otherwise Groq synthesizes from retrieved chunks, then the pair is stored for future reuse.

```
ai-knowledge-base/
├── main.py                  # entry point: `from api import app`
├── api.py                   # FastAPI app, lifespan, routes (/ingest /sync /ask /cache)
├── graph.py                 # LangGraph /ask StateGraph + capability detector
├── ingest.py                # notes, manifest, embedding cache, splitting, sync, watcher
├── store.py                 # Qdrant client, vector stores, QA memory
├── cache.py                 # SQLite exact-question Q→A cache (+list/analysis/clear)
├── embeddings.py            # lazy HuggingFace embedding singleton
├── config.py                # all tuning constants
└── Portfolio/               # the notes being indexed
```

---

## Why LangGraph

The pipeline is naturally a **decision graph**, not a linear chain — the same question should skip retrieval entirely when it's already answered in cache, but a confident top chunk shouldn't invoke the LLM. LangGraph models that as real nodes with conditional edges, so every short-circuit is explicit and the stored status (`local_hit`, `qa_hit`, `direct`, `llm`, `missing`, `none`, `error`) tells you exactly how an answer was produced.

**Extension** is a side-effect of the design: add a node with `graph.add_node("name", fn)`, wire a conditional edge, and the /ask pipeline gains a new behavior without touching the routes.

---

## Token savings of local caching

Repeated questions never touch the LLM twice. The SQLite cache keys on the normalized question string (versioned by `PIPELINE_VERSION`, so stale answers are automatically ignored after a retrieval/prompt change). `/cache/analysis` reports how often the cache saved an LLM call: answer mix by status, reuse counts, top questions, and top sources.
[[Docker]][[langgraph]][[FastAPI]][[Monolithic]][[Qdrant]][[REST]]
```markdown
# Cura — Clinical Decision Support (Multi-Agent Demo)

> **Status:** Design locked · Not started  
> **Framing:** Educational / portfolio demo on **synthetic data only**. **Not for clinical use.**

---

## One-line pitch

Backend + multi-agent clinical decision support: an orchestrator coordinates specialist agents (symptoms, labs, differential diagnosis, drug interactions) over Kafka, with full run auditing and ranked diagnoses with scores and reasoning.

---

## Goals

- Show **multi-agent** skills (LangGraph orchestration, specialist pipelines)
- Show **backend** skills (FastAPI, Postgres, audit, event-driven design, reliable messaging)
- Use **Kafka** as the async backbone and event log
- Prefer **dedicated ML / rules per agent** over one general LLM playing all roles
- Stay **free** (synthetic data, open tools)
- Stay honest: no clinical claims, no real PHI; use **score** not calibrated probability

---

## Architecture

```
Clinician / API
      │
      │  POST /cases
      │  POST /cases/{id}/analyze  → run_id (async)
      ▼
┌─────────────┐     produce      ┌──────────────────┐
│  FastAPI    │ ───────────────► │  Kafka           │
│  + Postgres │                  │  • case.analyze  │
│  + Audit    │                  │  • agent.events  │
│  + Outbox   │                  │  • run.completed │
└─────────────┘                  └────────┬─────────┘
      ▲                                   │
      │                            Agent workers
      │                            (LangGraph)
      └────────────────────────────┘
```

- **Postgres** = source of truth (cases, runs, reports, audit, outbox)
- **Kafka** = commands + agent event stream
- **LangGraph** = orchestrator + specialist flow inside the worker

---

## Agents (5)

| # | Agent | Responsibility | Dedicated approach (V1) |
|---|--------|----------------|-------------------------|
| 1 | **Orchestrator** | Route work, decide next agent, stop conditions, converge | LangGraph control logic (thin) |
| 2 | **Symptom analyzer** | Structure symptoms, red flags | Clinical NER (e.g. scispaCy) |
| 3 | **Lab interpreter** | Labs vs reference ranges, flag abnormalities | Rules + reference ranges |
| 4 | **Differential diagnosis** | Ranked candidate diagnoses + reasoning + **score** | Specialized medical model or ranker (not general chatbot) |
| 5 | **Drug interaction** | Safety check on **current meds** + **candidate drugs on the case** + condition rules (e.g. G6PD) | openFDA / RxNorm + static rules |

### Drug agent scope (V1) — locked

**Does**
- Check medications listed on the case
- Check any candidate drugs already present on the case
- Apply condition-based rules (e.g. G6PD ↔ unsafe drugs)
- Flag interactions / risks

**Does not**
- Map diagnoses → treatments
- Propose a drug plan from DiffDx output

DiffDx outputs diagnoses + scores + reasoning.  
Drug agent is a **safety / interaction checker**, not a prescribing agent.

### How they talk

- Shared **run state** (case + findings so far)
- Publish to **`agent.events`**
- Later agents **read** earlier findings (e.g. DiffDx uses symptoms + labs; Drug uses meds + case candidate drugs)
- Orchestrator runs **limited loops**, then **converge** → final report

Not a free-form group chat — a **controlled multi-agent workflow**.

---

## Scores (not confidence)

- Field name everywhere: **`score`**
- Do **not** label outputs as `confidence` or `probability` unless calibrated
- Model / ranker outputs are ranking scores, not true probabilities

Example report item:

```json
{
  "diagnosis": "Acute cystitis",
  "score": 0.74,
  "reasoning": "..."
}
```

---

## Kafka topics

| Topic | Purpose |
|-------|---------|
| `case.analyze` | API → worker: `{ run_id, case_id }` |
| `agent.events` | Each agent step: `{ run_id, agent, type, payload }` |
| `run.completed` | Final report: `{ run_id, diagnoses, scores, reasoning }` |

### Delivery guarantees (locked)

**Idempotent worker**
- On `case.analyze`: if `run_id` is already `running`, `completed`, or `failed` → **skip**
- Only claim runs in `queued` (e.g. conditional update / lock)

**Stuck `queued` runs**
- Risk: API writes run to Postgres, then Kafka produce fails → run never starts
- V1 mitigations:
  1. **Transactional outbox** (preferred): same DB transaction writes `runs` + `outbox`; publisher process sends to Kafka and marks outbox sent
  2. **Retry sweep**: periodic job re-publishes old `queued` runs

Minimum: idempotent consumer + retry sweep.  
Stronger backend story: outbox + idempotent consumer.

---

## Backend API (V1)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/cases` | Create case |
| `GET` | `/cases/{id}` | Get case |
| `POST` | `/cases/{id}/analyze` | Start run → returns `run_id` |
| `GET` | `/runs/{id}` | Status + final report |
| `GET` | `/runs/{id}/events` | Agent event history (audit / UI) |

---

## Data (Postgres)

- `cases` — symptoms, vitals, meds, labs, optional candidate_drugs (synthetic); flexible clinical fields as JSONB where useful
- `runs` — status: `queued` → `running` → `completed` / `failed`
- `agent_events` — full audit trail per step
- `reports` — ranked diagnoses, **scores**, reasoning
- `outbox` — pending Kafka messages (if using transactional outbox)

Optional later: FHIR-inspired resource shapes (Patient, Observation, Medication). **No full HAPI FHIR server in V1.**

**DB choice:** PostgreSQL only (users + cases + runs + audit). JSONB for flexible case payloads — not Mongo for V1.

---

## Stack (free)

| Layer | Choice |
|-------|--------|
| API | FastAPI |
| DB | PostgreSQL (+ JSONB) |
| Events | Kafka (Docker) |
| Orchestration | LangGraph |
| Symptom | scispaCy (or similar NER) |
| Labs | Rules + reference ranges |
| DiffDx | Specialized open medical model / ranker (scoped) |
| Drugs | openFDA / RxNorm + rules (incl. condition rules) |
| Data | Hand-written cases + optional Synthea exports |
| Deploy | Docker Compose |

---

## Explicit non-goals (V1)

- Real patient data / PHI
- HIPAA certification or BAA hosting claims
- Full EHR or full FHIR server
- Clinically validated diagnosis accuracy
- Training large models from scratch
- Unlimited agent debate loops
- Diagnosis → treatment mapping (prescribing)
- Calling scores “confidence” / “probability” without calibration

---

## Phased plan

### Phase 0 — Setup
- Repo name: **cura**
- Docker Compose: Postgres + Kafka
- FastAPI skeleton + config + disclaimer in README

### Phase 1 — Backend core
- Schema: cases, runs, agent_events, reports, outbox (if used)
- CRUD + `analyze` endpoint (write run + outbox / produce `case.analyze`)

### Phase 2 — Kafka path
- Produce/consume with **idempotent** worker
- Retry sweep and/or outbox publisher
- Worker writes `agent.events`, marks run complete

### Phase 3 — Agents
- Orchestrator + Symptom + Lab + DiffDx + Drug (scoped as above)
- Shared state + converge node
- Publish `agent.events` on each step; final report uses **score**

### Phase 4 — Polish
- 2–3 sample synthetic cases (include at least one drug-rule case, e.g. G6PD-style)
- README architecture + “not for clinical use”
- End-to-end demo path

### Later (optional)
- Live UI timeline (Next.js)
- Light RAG over public guideline snippets
- FHIR-ish input mapping
- Stronger DiffDx model if hardware allows
- Diagnosis → treatment suggestions (explicit separate feature)

---

## Decisions log

- Project name: **Cura**
- 5 agents (orchestrator + 4 specialists)
- Dedicated ML/rules per agent — not one general LLM for everything
- Drug agent = meds + case candidate drugs + condition rules; **no** diagnosis→treatment in V1
- Output field = **`score`**, not confidence/probability
- Kafka: idempotent consumer; outbox and/or queued-run retry sweep
- Backend owns data, API, audit, messaging reliability; agents own reasoning
- Postgres (+ JSONB) only for V1 — no Mongo
- Synthetic data only; honest medical framing

---

## Next step

Freeze **agent I/O contracts** (JSON in/out for each agent), then start Phase 0.
```
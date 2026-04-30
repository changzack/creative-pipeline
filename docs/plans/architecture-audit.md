# Creative Pipeline Architecture Audit
## Mapped against Agentic AI Reference Architecture

Date: 2026-04-30
Source: Reference architecture diagram (9-layer agentic AI system)

---

## 1. User / Client Layer

| Component | Status | What We Have |
|-----------|--------|-------------|
| Chat | ✅ HAVE | Telegram → OpenClaw gateway → Mira |
| Web/Mobile App | ❌ NONE | No web UI for pipeline management |
| API/SDK | ❌ NONE | No programmatic access to trigger pipelines |

**Gap:** Zack interacts ONLY via Telegram chat. No dashboard to see pipeline progress, view builds side-by-side, or trigger phases. Everything is conversational.

---

## 2. Orchestration / Control Plane

| Component | Status | What We Have |
|-----------|--------|-------------|
| Orchestrator / Workflow Engine | ⚠️ MANUAL | Mira (main session) + CREATIVE-PIPELINE.md doc. No actual workflow engine — Mira reads the doc and executes steps manually each time. |
| Task Decomposition | ⚠️ MANUAL | Mira reads the brief and decides which phases to run. No automated DAG. |
| Agent Selection | ⚠️ HARDCODED | Always Hermes via hermes-bridge. No agent routing or selection logic. |
| Plan & Execution Manager | ❌ MISSING | No execution state machine. Pipeline state lives in Mira's context window (decays over time). Cron jobs as makeshift state checks. |
| State & Context Manager | ❌ MISSING | No persistent pipeline state. If Mira's session compacts, pipeline progress is lost. Signal files (.done, .running) are primitive state, not a state machine. |
| Guardrails & Policy | ⚠️ PARTIAL | CREATIVE-PIPELINE.md has rules (deployment gate, phase transition rule) but enforcement is Mira remembering to follow them. She skipped phases in V1. |

**Gap:** This is our BIGGEST weakness. We have no workflow engine. Mira IS the orchestrator, but she:
- Loses state when context compacts
- Forgets to follow the pipeline doc
- Uses cron jobs as a hacky pub/sub system
- Can't parallelize phases properly (cron polling, not event-driven)

---

## 3. Agent Layer (Specialized Agents)

| Agent Role | Status | What We Have |
|------------|--------|-------------|
| Research Agent | ✅ HAVE | Hermes job `visual-research-v2` — does web search, screenshots, analysis |
| Designer Agent | ✅ HAVE | Hermes jobs `v2-designer-{1,2,3}` — writes approach docs |
| Builder Agent | ✅ HAVE | Hermes jobs `v2-builder-{print,mint,tower}` — builds HTML prototypes |
| Reviewer Agent | ✅ HAVE | Hermes job `v2-reviewer-r1` — opens builds in browser, scores them |
| Iterator Agent | ✅ HAVE | Hermes jobs `v2-fix-{print,mint,tower}` — applies surgical fixes |
| Communication Agent | ✅ HAVE | Mira sends results to Zack via Telegram |

**Gap:** Agents exist but have NO persistent identity. Each spawn is a blank Opus session. Just created `personas/` directory to fix this, but:
- Personas aren't being injected yet (V2 didn't use them)
- No agent memory across runs (a builder doesn't remember what failed last time)
- No specialization — every Hermes session is identical except for the task file

---

## 4. Tools & Integrations Layer

| Tool | Status | What We Have |
|------|--------|-------------|
| Web Search | ✅ | Hermes has browser + web search tools |
| Code Execution | ✅ | Hermes has terminal/shell tools |
| File Processing | ✅ | Hermes reads/writes files on disk |
| APIs | ⚠️ PARTIAL | fal.ai for image gen, Unsplash for images. No Figma API, no Cloudinary API in pipeline. |
| Databases | ❌ NONE | No database. Everything is files. |
| Deployment | ✅ | here-now for instant deploys |

**Gap:** Tools are functional but not coordinated. Each Hermes session discovers tools independently. No shared tool configuration or credential injection.

---

## 5. Memory & Knowledge Layer

| Component | Status | What We Have |
|-----------|--------|-------------|
| Short-term Memory (Context) | ⚠️ FRAGILE | Mira's context window. Compacts and loses pipeline state. Hermes sessions have zero cross-session memory. |
| Long-term Memory | ⚠️ PARTIAL | MEMORY.md + memory/*.md files. Manual curation. Not queryable by agents. |
| Knowledge Base (Docs) | ✅ HAVE | CREATIVE-PIPELINE.md, personas/, VISUAL-RESEARCH.md, approach docs, SMPLX design system |
| Episodic / Event Store | ❌ MISSING | No history of past pipeline runs. Can't query "what scored well last time" or "what techniques actually worked." Reviews exist as files but aren't indexed. |
| User Profile Store | ⚠️ PARTIAL | USER.md + SOUL.md + taste preferences in REVIEWER.md. Not structured data — just markdown. |

**Gap:** Memory is our second biggest weakness. Key problems:
- Pipeline run history is scattered across overnight-runs/ directories with no index
- Hermes agents can't access Mira's memory or past run learnings
- No structured "what worked / what failed" database
- Taste preferences are embedded in prose, not queryable

---

## 6. Monitoring & Observability

| Component | Status | What We Have |
|-----------|--------|-------------|
| Tracing & Logging | ⚠️ PRIMITIVE | Hermes .log files per job. No structured tracing. No correlation across pipeline phases. |
| Metrics & Dashboards | ❌ MISSING | No metrics. Don't know: avg build time, pass rate, cost per run, score trends. |
| Alerts & Notifications | ⚠️ PARTIAL | Cron jobs check for completion and alert Zack. But no anomaly detection (e.g., "this build took 3x longer than usual"). |
| Audit & Compliance | ⚠️ PARTIAL | Task files + review files create a paper trail. But no unified audit log. |

**Gap:** We're flying blind. Can't answer: "How much did V2 cost?" "What's our average review score?" "Which phase takes longest?" "What's the failure rate per builder?"

---

## 7. Reliability & Failure Management

| Component | Status | What We Have |
|-----------|--------|-------------|
| Error Detection | ⚠️ PARTIAL | hermes-status.sh checks .done/.failed/.killed signals. |
| Retry & Backoff | ❌ MISSING | If a Hermes job fails, Mira manually decides to retry. No automatic retry. |
| Fallback / Alternate Agents | ❌ MISSING | Only Hermes. If Hermes fails, no fallback to OpenClaw sub-agents or other models. |
| Human-in-the-loop | ✅ HAVE | Phase 7 Taste Gate is human review. Phase 2 Approach Gate has human checkpoint option. |
| Circuit Breaker | ❌ MISSING | No concept of "this pipeline is failing, stop spending money." V2 ran to completion even though quality was degrading. |

**Gap:** No automatic failure recovery. No cost circuit breaker. No fallback agents.

---

## 8. Governance & Security

| Component | Status | What We Have |
|-----------|--------|-------------|
| Authentication | ✅ | Telegram auth, API keys in .env files |
| Data Privacy | ⚠️ | Builds deployed to public here-now URLs (anyone with link can view) |
| Policy Enforcement | ⚠️ MANUAL | "Don't deploy without review" is a doc rule, not enforced by code |
| Model & Prompt Guardrails | ❌ MISSING | No guardrails on what Hermes agents can do. Full filesystem access. |

---

## 9. Foundation / Infrastructure Layer

| Component | Status | What We Have |
|-----------|--------|-------------|
| LLM Providers | ✅ | Anthropic (Opus) via direct API |
| Model Gateway | ⚠️ PARTIAL | OpenClaw gateway for Mira. Hermes uses direct Anthropic API (no routing, no rate limits, no cost tracking). |
| Vector DB | ❌ NONE | No embeddings, no semantic search over past builds/reviews |
| Data Storage | ✅ | Local filesystem (overnight-runs/, memory/, skills/) |
| Queue / Event Bus | ❌ MISSING | Using cron polling instead of events. This is why phase transitions are slow and unreliable. |
| Cache | ❌ NONE | Every Hermes session starts cold. No cached research, no cached font loads. |
| Secrets Manager | ❌ NONE | API keys in plaintext .env files |
| CI/CD & Deployment | ⚠️ PARTIAL | here-now for static deploys. No CI/CD for the pipeline itself. |

---

## Summary: Coverage Map

| Layer | Coverage | Grade |
|-------|----------|-------|
| 1. User/Client | Telegram only | C |
| 2. Orchestration | Manual (Mira + doc + crons) | D |
| 3. Agents | Functional but stateless | B- |
| 4. Tools | Adequate | B |
| 5. Memory | Fragile, unstructured | D+ |
| 6. Observability | Nearly blind | F |
| 7. Reliability | Manual recovery only | D |
| 8. Governance | Basic | C |
| 9. Infrastructure | Local-only, no event bus | C- |

## Top 3 Gaps (highest impact)

1. **No Workflow Engine (Layer 2)** — Pipeline state lives in Mira's context window, which decays. Cron polling is unreliable and slow. This is why phases get skipped and quality gates aren't enforced.

2. **No Pipeline Memory (Layer 5)** — Agents don't learn from past runs. The reviewer doesn't know V1 scored 7.0 but Zack said it was bad. Builders don't know which techniques actually rendered visibly. Each run starts from zero.

3. **No Observability (Layer 6)** — Can't measure cost, time, quality trends, or failure rates. Can't answer "is V2 better than V1" with data — only Zack's gut reaction (which is correct but unscalable).

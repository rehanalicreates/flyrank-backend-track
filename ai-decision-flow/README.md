# AI Decision Flow

An interactive AI workflow editor: build a flowchart of decision nodes, run it, and
watch an LLM answer each node's YES/NO question step by step. Every node is one
Inngest step, so the whole traversal is durable and retryable.

Built for the **Backend AI Engineering - Week 7 (Build+)** assignment: *"Build an AI
Decision Flow with React Flow + Inngest"*.

## How it works

1. Each **decision node** holds a question (prompt) and has two outgoing edges:
   YES and NO.
2. Press **Run flow** - the frontend posts the whole graph to the API and gets a
   `runId` back (202-style accept).
3. The API sends a `flow/execute` event to Inngest. The `executeFlow` function
   walks the graph: for each node it runs one `step.run("ask-...")` that calls the
   LLM, which must answer exactly `YES` or `NO`.
4. The traversal follows the matching edge (node with no outgoing edges is the
   terminal node). The visited path / execution order is stored and polled by the
   frontend, which paints visited nodes and animates the edges used.

## Stack

| Layer | Tech |
| --- | --- |
| Frontend | Vite + React, React Flow (@xyflow/react), shadcn/ui (Tailwind v4) |
| Orchestration | Inngest (event `flow/execute`, function `executeFlow`) |
| API server | Fastify (`server/server.js`), serves Inngest via `inngest/fastify` |
| LLM | OpenAI SDK against any OpenAI-compatible endpoint (Ollama by default) |

## Run it locally

Prerequisites: Node 20+, and a running LLM endpoint (Ollama by default, with
`qwen3:0.6b` pulled). Three terminals:

```bash
# 1. API server + Inngest handlers (http://127.0.0.1:8001)
npm run server

# 2. Inngest dev server (dashboard + local executor on http://localhost:8288)
npm run dev:inngest

# 3. Frontend (http://localhost:5173, proxies /api to the server)
npm run dev
```

Configure the LLM in `.env` (copy from `.env.example`):

```bash
OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama; any OpenAI-compatible provider works
OPENAI_API_KEY=ollama
OPENAI_MODEL=qwen3:0.6b
PORT=8001
INNGEST_DEV=1
INNGEST_EVENT_KEY=local
```

> Keep `max_tokens` in `server/inngest.js` comfortably high: reasoning-style
> models (qwen3, r1) spend tokens on thinking before the final answer.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/flow/execute` | Body `{ graph: { nodes, edges }, startNodeId }` -> `202 { runId }` |
| GET | `/api/flow/runs/:runId` | Poll run: `queued / running / succeeded / failed` + `path` (execution order) |

## Features (Phase 4 polish)

- Visual execution state: visited nodes get a highlight ring, used edges animate
- Execution logs/history panel (last 20 runs, per run click to view)
- Autosave the editor (400ms debounce) + named save slots
- Export / import the flow as JSON
- Error handling: failed runs surface an error toast; failed state has a Retry
- Custom node + edge components styled with shadcn tokens (YES = green, NO = red)

## Project structure

```
ai-decision-flow/
  server/
    server.js       Fastify: /api/flow/execute, /api/flow/runs/:id, /api/inngest
    inngest.js      Inngest client, executeFlow function, decision (LLM) step
  src/
    App.jsx         Editor: canvas, run/poll, save/load, export/import, logs
    nodes/DecisionNode.jsx   Custom node (prompt + YES/NO handles)
    edges/YesNoEdge.jsx      Custom edges (YES solid green / NO dashed red)
    api.js          startRun / getRun
    components/ui/  shadcn button + card
```
// Fastify API server hosting the Inngest function (Phase 1/3).
//
// - /api/inngest  -> Inngest dev runtime
// - POST /api/flow/execute -> 202-style accept: registers a run, sends the
//   flow/execute event, answers { runId } immediately
// - GET /api/flow/runs/:runId -> run record (status + path) for polling

import Fastify from "fastify";
import { randomUUID } from "node:crypto";
import { serve } from "inngest/fastify";
import { executeFlow, inngest, runs } from "./inngest.js";

const app = Fastify({ logger: process.env.LOG_LEVEL === "debug" });

app.all("/api/inngest", serve({ client: inngest, functions: [executeFlow] }));

app.post("/api/flow/execute", async (request, reply) => {
  const { graph, startNodeId } = request.body ?? {};
  if (!graph?.nodes?.length || !startNodeId) {
    return reply.code(400).send({ error: "graph and startNodeId are required" });
  }
  if (!graph.nodes.some((n) => n.id === startNodeId)) {
    return reply.code(400).send({ error: "startNodeId is not in the graph" });
  }

  const runId = randomUUID();
  runs.set(runId, { status: "queued", startedAt: null, finishedAt: null, path: [] });
  await inngest.send({
    name: "flow/execute",
    data: { runId, startNodeId, nodes: graph.nodes, edges: graph.edges },
  });
  return reply.code(202).send({ runId });
});

app.get("/api/flow/runs/:runId", async (request, reply) => {
  const run = runs.get(request.params.runId);
  if (!run) return reply.code(404).send({ error: "run not found" });
  return reply.send(run);
});

const PORT = Number(process.env.PORT || 8001);
await app.listen({ port: PORT, host: "127.0.0.1" });
console.log(`[server] workflow API + Inngest handlers on http://127.0.0.1:${PORT}`);
console.log("[server] Inngest dev server: npx inngest-cli dev");
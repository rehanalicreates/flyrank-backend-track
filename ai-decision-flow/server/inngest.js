// Inngest client + the workflow function (Phase 3 of the assignment).
//
// Every node in the flow maps to one Inngest step (`step.run`): the step asks
// the LLM the node's question, the model answers exactly YES or NO, and the
// traversal follows the matching outgoing edge until a node has no outgoing
// edges (the terminal node). The visited path (execution order) is returned.
//
// In dev, the function runs inside THIS process (served via inngest/fastify),
// so the run record is written to a shared in-memory store the REST layer and
// the frontend can poll.

import { Inngest } from "inngest";
import OpenAI from "openai";

export const inngest = new Inngest({ id: "ai-decision-flow" });

// Shared run store: runId -> { status, startedAt, finishedAt, path, error }
export const runs = new Map();

const openaiClient = new OpenAI({
  baseURL: process.env.OPENAI_BASE_URL || "http://localhost:11434/v1",
  apiKey: process.env.OPENAI_API_KEY || "ollama",
});
const MODEL = process.env.OPENAI_MODEL || "qwen3:0.6b";

export async function askYesNo(prompt) {
  const completion = await openaiClient.chat.completions.create({
    model: MODEL,
    temperature: 0,
    max_tokens: 256,
    messages: [
      {
        role: "system",
        content:
          "You are a decision gate in a workflow. Answer with exactly one word: YES or NO. Nothing else.",
      },
      { role: "user", content: prompt },
    ],
  });
  const answer = (completion.choices[0]?.message?.content ?? "").trim().toUpperCase();
  if (answer === "YES") return "yes";
  if (answer === "NO") return "no";
  throw new Error(
    `LLM answer was not YES/NO (got: ${answer ? JSON.stringify(answer) : "empty"})`
  );
}

export const executeFlow = inngest.createFunction(
  {
    id: "execute-flow",
    triggers: { event: "flow/execute" },
  },
  async ({ event, step }) => {
    const { runId, startNodeId, nodes, edges } = event.data;
    const nodesById = new Map(nodes.map((n) => [n.id, n]));
    const outgoing = (id) => edges.filter((e) => e.source === id);

    const startedAt = new Date();
    const path = [];
    let nodeId = startNodeId;
    let index = 0;

    try {
      while (nodeId) {
        const node = nodesById.get(nodeId);
        if (!node) throw new Error(`Unknown node: ${nodeId}`);

        const prompt = node.data.prompt;
        const answer = await step.run(`ask-${runId}-${node.id}`, () =>
          askYesNo(prompt)
        );
        path.push({
          index: index++,
          nodeId: node.id,
          label: node.data.label,
          prompt,
          answer,
        });

        // Follow the edge of the matching branch (YES/NO).
        const match =
          outgoing(nodeId).find((e) => e.sourceHandle === answer) ??
          outgoing(nodeId).find(
            (e) => (e.label ?? "").toLowerCase() === answer
          );
        nodeId = match ? match.target : null;
      }

      const record = {
        status: "succeeded",
        startedAt: startedAt.toISOString(),
        finishedAt: new Date().toISOString(),
        path,
      };
      runs.set(runId, record);
      return record;
    } catch (error) {
      const record = {
        status: "failed",
        startedAt: startedAt.toISOString(),
        finishedAt: new Date().toISOString(),
        path,
        error: String(error?.message ?? error),
      };
      runs.set(runId, record);
      throw error;
    }
  }
);
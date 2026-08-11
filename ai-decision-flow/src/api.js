// Thin client for the workflow API. Vite proxies /api -> the Fastify server.

export async function startRun(graph, startNodeId) {
  const res = await fetch('/api/flow/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graph, startNodeId }),
  })
  if (!res.ok) {
    let message = res.statusText
    try {
      message = (await res.json()).error || message
    } catch {
      /* keep statusText */
    }
    throw new Error(message)
  }
  return res.json()
}

export async function getRun(runId) {
  const res = await fetch(`/api/flow/runs/${runId}`)
  if (!res.ok) throw new Error('run not found')
  return res.json()
}
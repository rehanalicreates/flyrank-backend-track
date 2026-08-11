import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
} from '@xyflow/react'
import { Download, FolderOpen, Play, RotateCcw, Save, Trash2, Upload } from 'lucide-react'

import { Button } from '#/components/ui/button'
import DecisionNode from '#/nodes/DecisionNode'
import YesNoEdge from '#/edges/YesNoEdge'
import { getRun, startRun } from '#/api'

const AUTO_SAVE_KEY = 'adf:auto'
const SLOT_PREFIX = 'adf:slot:'

const nodeTypes = { decision: DecisionNode }
const edgeTypes = { yes: YesNoEdge, no: YesNoEdge }

function seedGraph() {
  return {
    nodes: [
      {
        id: 'start',
        type: 'decision',
        position: { x: 60, y: 180 },
        data: { label: 'Start', prompt: 'Is this a support request?' },
      },
      {
        id: 'support',
        type: 'decision',
        position: { x: 400, y: 40 },
        data: { label: 'Support', prompt: 'Does the customer want a refund?' },
      },
      {
        id: 'sales',
        type: 'decision',
        position: { x: 400, y: 300 },
        data: { label: 'Sales', prompt: 'Is the prospect ready to buy now?' },
      },
      {
        id: 'end',
        type: 'decision',
        position: { x: 740, y: 170 },
        data: { label: 'End', prompt: 'Conversation finished - route to CRM.' },
      },
    ],
    edges: [
      {
        id: 'e1',
        source: 'start',
        sourceHandle: 'yes',
        target: 'support',
        type: 'yes',
        label: 'YES',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#16a34a' },
      },
      {
        id: 'e2',
        source: 'start',
        sourceHandle: 'no',
        target: 'sales',
        type: 'no',
        label: 'NO',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#dc2626' },
      },
      {
        id: 'e3',
        source: 'support',
        sourceHandle: 'yes',
        target: 'end',
        type: 'yes',
        label: 'YES',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#16a34a' },
      },
      {
        id: 'e4',
        source: 'support',
        sourceHandle: 'no',
        target: 'sales',
        type: 'no',
        label: 'NO',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#dc2626' },
      },
      {
        id: 'e5',
        source: 'sales',
        sourceHandle: 'yes',
        target: 'end',
        type: 'yes',
        label: 'YES',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#16a34a' },
      },
      {
        id: 'e6',
        source: 'sales',
        sourceHandle: 'no',
        target: 'start',
        type: 'no',
        label: 'NO',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#dc2626' },
      },
    ],
  }
}

function branchMarker(branch) {
  return {
    type: MarkerType.ArrowClosed,
    color: branch === 'yes' ? '#16a34a' : '#dc2626',
  }
}

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedId, setSelectedId] = useState(null)
  const [error, setError] = useState(null)
  const [run, setRun] = useState(null) // { runId, status, path }
  const [history, setHistory] = useState([])
  const [slotName, setSlotName] = useState('')
  const fileInputRef = useRef(null)

  // --- init: seed once, then auto-save on every change --------------------
  const initialised = useRef(false)
  useEffect(() => {
    if (initialised.current) return
    initialised.current = true
    try {
      const saved = JSON.parse(localStorage.getItem(AUTO_SAVE_KEY) || 'null')
      if (saved?.nodes?.length) {
        setNodes(saved.nodes)
        setEdges(saved.edges ?? [])
        return
      }
    } catch {
      /* fall through to seed */
    }
    const seed = seedGraph()
    setNodes(seed.nodes)
    setEdges(seed.edges)
  }, [setNodes, setEdges])

  useEffect(() => {
    if (!initialised.current) return
    const timer = setTimeout(() => {
      localStorage.setItem(AUTO_SAVE_KEY, JSON.stringify({ nodes, edges }))
    }, 400)
    return () => clearTimeout(timer)
  }, [nodes, edges])

  // --- graph editing ------------------------------------------------------
  const onConnect = useCallback(
    (params) => {
      const branch = params.sourceHandle === 'no' ? 'no' : 'yes'
      setEdges((eds) =>
        addEdge(
          {
            ...params,
            type: branch,
            label: branch.toUpperCase(),
            markerEnd: branchMarker(branch),
          },
          eds,
        ),
      )
    },
    [setEdges],
  )

  const onNodeClick = useCallback((_, node) => setSelectedId(node.id), [])

  const addNode = useCallback(() => {
    const id = `node-${Date.now()}`
    const offset = nodes.length * 24
    const node = {
      id,
      type: 'decision',
      position: { x: 60 + offset, y: 180 + offset },
      data: { label: 'New decision', prompt: 'Ask a YES/NO question here?' },
    }
    setNodes((nds) => nds.concat(node))
    setSelectedId(id)
  }, [nodes.length, setNodes])

  const updateSelected = useCallback(
    (patch) => {
      if (!selectedId) return
      setNodes((nds) =>
        nds.map((n) => (n.id === selectedId ? { ...n, data: { ...n.data, ...patch } } : n)),
      )
    },
    [selectedId, setNodes],
  )

  const deleteSelected = useCallback(() => {
    if (!selectedId) return
    setNodes((nds) => nds.filter((n) => n.id !== selectedId))
    setEdges((eds) => eds.filter((e) => e.source !== selectedId && e.target !== selectedId))
    setSelectedId(null)
  }, [selectedId, setNodes, setEdges])

  const resetHighlights = useCallback(() => {
    setNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, status: undefined } })))
    setEdges((eds) => eds.map((e) => ({ ...e, animated: false })))
    setRun(null)
  }, [setNodes, setEdges])

  // --- execution ----------------------------------------------------------
  const findStartNode = useCallback(
    () => nodes.find((n) => !edges.some((e) => e.target === n.id)),
    [nodes, edges],
  )

  const runFlow = useCallback(async () => {
    setError(null)
    setNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, status: undefined } })))
    setEdges((eds) => eds.map((e) => ({ ...e, animated: false })))
    if (!nodes.length) return setError('Add at least one decision node first.')
    const start = findStartNode()
    if (!start) return setError('No start node - a node without incoming edges is the start.')
    const graph = {
      nodes: nodes.map((n) => ({
        id: n.id,
        data: { label: n.data.label, prompt: n.data.prompt },
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        label: e.label,
      })),
    }
    try {
      const { runId } = await startRun(graph, start.id)
      setRun({ runId, status: 'queued', path: [] })
    } catch (err) {
      setError(err.message)
    }
  }, [nodes, edges, findStartNode, setNodes, setEdges])

  // Poll the run record until it finishes, then paint the executed path.
  useEffect(() => {
    if (!run?.runId || ['succeeded', 'failed'].includes(run.status)) return
    let cancelled = false
    let timer
    const poll = async () => {
      try {
        const record = await getRun(run.runId)
        if (cancelled) return
        if (record.status === 'succeeded') {
          setRun({ ...run, status: 'succeeded', path: record.path })
          setNodes((nds) =>
            nds.map((n) => ({
              ...n,
              data: {
                ...n.data,
                status: record.path.some((p) => p.nodeId === n.id) ? 'succeeded' : undefined,
              },
            })),
          )
          setEdges((eds) =>
            eds.map((e) => {
              const used = record.path.some(
                (p) =>
                  p.nodeId === e.source && (e.sourceHandle === p.answer || (e.label ?? '').toLowerCase() === p.answer),
              )
              return { ...e, animated: used }
            }),
          )
          setHistory((h) =>
            [{ at: new Date().toLocaleTimeString(), runId: run.runId, status: 'succeeded', path: record.path }, ...h].slice(0, 20),
          )
        } else if (record.status === 'failed') {
          setRun({ ...run, status: 'failed', path: record.path, error: record.error })
          setHistory((h) =>
            [{ at: new Date().toLocaleTimeString(), runId: run.runId, status: 'failed', error: record.error, path: record.path }, ...h].slice(0, 20),
          )
        } else {
          timer = setTimeout(poll, 600)
        }
      } catch {
        timer = setTimeout(poll, 1200)
      }
    }
    poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [run, setNodes, setEdges])

  // --- save / load / export / import --------------------------------------
  const saveSlot = useCallback(() => {
    const name = (slotName || 'draft').trim()
    localStorage.setItem(SLOT_PREFIX + name, JSON.stringify({ nodes, edges }))
    setSlotName('')
  }, [nodes, edges, slotName])

  const loadSlot = useCallback(() => {
    const values = Object.keys(localStorage)
      .filter((k) => k.startsWith(SLOT_PREFIX))
      .map((k) => k.slice(SLOT_PREFIX.length))
    if (!values.length) return setError('No saved workflows yet.')
    const name = slotName.trim() || values[values.length - 1]
    try {
      const data = JSON.parse(localStorage.getItem(SLOT_PREFIX + name))
      if (data?.nodes?.length) {
        setNodes(data.nodes)
        setEdges(data.edges ?? [])
        setSelectedId(null)
      } else setError(`Slot "${name}" is empty.`)
    } catch {
      setError(`Could not read slot "${name}".`)
    }
  }, [nodes, edges, slotName, setNodes, setEdges])

  const exportJson = useCallback(() => {
    const blob = new Blob([JSON.stringify({ nodes, edges }, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'flow.json'
    a.click()
    URL.revokeObjectURL(url)
  }, [nodes, edges])

  const importJson = useCallback(async (file) => {
    try {
      const data = JSON.parse(await file.text())
      if (!data?.nodes?.length) throw new Error('no nodes')
      if (data.edges.some((e) => !['yes', 'no'].includes(e.type))) {
        data.edges = data.edges.map((e) => ({
          ...e,
          type: e.sourceHandle === 'no' ? 'no' : 'yes',
          label: (e.sourceHandle === 'no' ? 'NO' : 'YES'),
        }))
      }
      setNodes(data.nodes.map((n) => ({ ...n, type: n.type || 'decision' })))
      setEdges(
        data.edges.map((e) => ({
          ...e,
          markerEnd: branchMarker(e.type === 'yes' ? 'yes' : 'no'),
        })),
      )
      setSelectedId(null)
      setError(null)
    } catch {
      setError('Invalid flow JSON - import failed.')
    }
  }, [setNodes, setEdges])

  const selected = nodes.find((n) => n.id === selectedId)

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <header className="flex items-center gap-2 border-b border-zinc-200 bg-white px-4 py-2">
        <h1 className="mr-2 text-sm font-bold tracking-tight">AI Decision Flow</h1>
        <Button size="sm" onClick={addNode} variant="secondary">
          + Add decision
        </Button>
        <Button size="sm" onClick={runFlow} disabled={run?.status === 'queued' || run?.status === 'running'}>
          <Play /> Run flow
        </Button>
        {run?.status === 'failed' && (
          <Button size="sm" variant="secondary" onClick={runFlow}>
            <RotateCcw /> Retry
          </Button>
        )}
        <div className="ml-2 flex items-center gap-1 text-xs">
          <input
            className="h-7 w-28 rounded-md border border-zinc-300 px-2 text-xs outline-none focus:border-zinc-900"
            placeholder="slot name"
            value={slotName}
            onChange={(e) => setSlotName(e.target.value)}
          />
          <Button size="sm" variant="outline" onClick={saveSlot} title="Save current workflow to a slot">
            <Save /> Save
          </Button>
          <Button size="sm" variant="outline" onClick={loadSlot} title="Load workflow from a slot">
            <FolderOpen /> Load
          </Button>
          <Button size="sm" variant="outline" onClick={exportJson} title="Export workflow JSON">
            <Download /> JSON
          </Button>
          <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()} title="Import workflow JSON">
            <Upload /> Import
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) importJson(file)
              e.target.value = ''
            }}
          />
          {run && <Button size="sm" variant="ghost" onClick={resetHighlights}><Trash2 /> Clear run</Button>}
        </div>
        <div className="ml-auto text-xs text-zinc-400">
          {run?.status === 'queued' && <span className="font-semibold text-amber-600">queued...</span>}
          {run?.status === 'running' && <span className="font-semibold text-amber-600">running... (watch Inngest dev server)</span>}
          {run?.status === 'succeeded' && (
            <span className="font-semibold text-emerald-600">
              done: {run.path.length} node{run.path.length === 1 ? '' : 's'}
            </span>
          )}
          {run?.status === 'failed' && <span className="font-semibold text-red-600">failed: {run.error}</span>}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* canvas */}
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={18} />
            <Controls />
            <MiniMap pannable zoomable className="!bg-white" />
            {error && (
              <div className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-700 shadow-sm">
                {error}
              </div>
            )}
          </ReactFlow>
        </div>

        {/* right panel: editor + logs */}
        <aside className="flex w-80 flex-col gap-3 overflow-y-auto border-l border-zinc-200 p-3">
          {selected ? (
            <div className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Edit node</div>
              <label className="block text-xs text-zinc-500">
                Label
                <input
                  className="mt-1 w-full rounded-md border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-zinc-900"
                  value={selected.data.label || ''}
                  onChange={(e) => updateSelected({ label: e.target.value })}
                />
              </label>
              <label className="block text-xs text-zinc-500">
                Prompt (the model answers YES or NO)
                <textarea
                  className="mt-1 min-h-20 w-full resize-y rounded-md border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-zinc-900"
                  value={selected.data.prompt || ''}
                  onChange={(e) => updateSelected({ prompt: e.target.value })}
                />
              </label>
              <Button size="sm" variant="destructive" onClick={deleteSelected}>
                <Trash2 /> Delete node
              </Button>
              <p className="pt-1 text-[11px] leading-relaxed text-zinc-400">
                Drag from the green (YES) or red (NO) handle to the next node. A node with no
                incoming edges is the start of the flow.
              </p>
            </div>
          ) : (
            <div className="text-xs leading-relaxed text-zinc-400">
              Select a node to edit its prompt and label.
            </div>
          )}

          <div className="mt-auto space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Execution logs</div>
              {history.length > 0 && (
                <button className="text-[11px] text-zinc-400 underline" onClick={() => setHistory([])}>
                  clear
                </button>
              )}
            </div>
            {history.length === 0 ? (
              <div className="text-xs text-zinc-300">No runs yet. Hit "Run flow".</div>
            ) : (
              <ol className="space-y-2">
                {history.map((entry) => (
                  <li key={entry.runId} className="rounded-md border border-zinc-200 p-2 text-xs">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-zinc-400">{entry.at}</span>
                      <span
                        className={
                          entry.status === 'succeeded'
                            ? 'font-bold text-emerald-600'
                            : 'font-bold text-red-600'
                        }
                      >
                        {entry.status.toUpperCase()}
                      </span>
                    </div>
                    {entry.path?.map((p) => (
                      <div key={p.index} className="flex items-center gap-1 py-0.5">
                        <span className="font-mono text-[10px] text-zinc-400">#{p.index + 1}</span>
                        <span className="flex-1 truncate">{p.label || p.nodeId}</span>
                        <span
                          className={
                            p.answer === 'yes'
                              ? 'font-bold text-green-700'
                              : 'font-bold text-red-700'
                          }
                        >
                          {p.answer}
                        </span>
                      </div>
                    ))}
                    {entry.error && <div className="mt-1 text-red-600">{entry.error}</div>}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
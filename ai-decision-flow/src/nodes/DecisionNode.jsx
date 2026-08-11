import { Handle, Position } from '@xyflow/react'
import { cn } from '#/lib/utils'

// One decision step of the workflow. The model answers the prompt with YES or
// NO; the two source handles carry that answer out to the matching edge.
// YES sits on the top-right handle, NO on the bottom-right handle.
export default function DecisionNode({ data, selected }) {
  const status = data.status || 'idle'
  return (
    <div
      className={cn(
        'relative w-56 rounded-xl border border-zinc-200 bg-white px-3 py-2.5 shadow-sm',
        selected && 'ring-2 ring-zinc-900',
        status === 'running' && 'ring-2 ring-amber-400',
        status === 'succeeded' && 'ring-2 ring-emerald-500',
      )}
    >
      <Handle type="target" position={Position.Left} className="!size-2.5 !border-2 !border-white !bg-zinc-900" />

      <div className="mb-1 truncate text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
        {data.label || 'Decision'}
      </div>
      <div className="text-sm leading-snug text-zinc-800">{data.prompt}</div>

      <div className="pointer-events-none absolute right-1.5 top-[30%] text-[10px] font-bold text-green-700">YES</div>
      <div className="pointer-events-none absolute right-1.5 top-[63%] text-[10px] font-bold text-red-700">NO</div>
      <Handle id="yes" type="source" position={Position.Right} className="!top-[38%] !size-2.5 !border-2 !border-white !bg-green-600" />
      <Handle id="no" type="source" position={Position.Right} className="!top-[70%] !size-2.5 !border-2 !border-white !bg-red-600" />

      {status === 'running' && (
        <span className="absolute -top-2.5 right-2 rounded-full bg-amber-400 px-1.5 py-0.5 text-[10px] font-bold text-amber-950">
          RUNNING
        </span>
      )}
      {status === 'succeeded' && (
        <span className="absolute -top-2.5 right-2 rounded-full bg-emerald-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
          DONE
        </span>
      )}
    </div>
  )
}
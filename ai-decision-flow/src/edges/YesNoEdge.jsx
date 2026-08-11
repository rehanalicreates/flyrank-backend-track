import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react'

// Two custom edge types, one per branch: type "yes" (solid green) and
// type "no" (dashed red). Each renders its branch label on the line.
export default function YesNoEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  type,
}) {
  const isYes = type === 'yes'
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: isYes ? '#16a34a' : '#dc2626',
          strokeWidth: 2,
          strokeDasharray: isYes ? undefined : '6 4',
        }}
      />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan absolute -translate-x-1/2 -translate-y-1/2 rounded-full px-1.5 py-0.5 text-[10px] font-bold text-white shadow-sm"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            background: isYes ? '#16a34a' : '#dc2626',
          }}
        >
          {isYes ? 'YES' : 'NO'}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}
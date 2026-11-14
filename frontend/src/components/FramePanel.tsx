import { useAppState } from '../hooks/useAppState'
import FlagsPanel from './FlagsPanel'
import FrameMeta from './FrameMeta'
import PixelReadout from './PixelReadout'

export default function FramePanel() {
  const { sequence, currentFrame, frameA, frameB, params } = useAppState()
  if (!sequence || !currentFrame) return null
  const isDiff = params.view === 'diff'

  return (
    <aside className="side" aria-label="Frame details">
      <h2>{isDiff ? 'Difference operands' : 'Frame'}</h2>
      {isDiff ? (
        <>
          {frameA && <FrameMeta frame={frameA.frame} title="A" />}
          {frameB && <FrameMeta frame={frameB.frame} title="B" />}
        </>
      ) : (
        <FrameMeta frame={currentFrame.frame} title="Current" />
      )}
      <PixelReadout />
      <FlagsPanel />
      <p className="muted small">
        {sequence.meta.n_exposures_total} exposures · {sequence.meta.collections.join(', ') || 'no collections'}
        {sequence.meta.pipeline_tags.length > 0 && ` · pipeline ${sequence.meta.pipeline_tags.join(', ')}`}
      </p>
    </aside>
  )
}

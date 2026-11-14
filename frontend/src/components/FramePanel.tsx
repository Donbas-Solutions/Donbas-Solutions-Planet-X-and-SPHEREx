import { useAppState } from '../hooks/useAppState'

interface Props {
  showFlags: boolean
  onShowFlagsChange: (show: boolean) => void
}

export default function FramePanel({ showFlags, onShowFlagsChange }: Props) {
  const { currentFrame, selectedPixel } = useAppState()
  if (!currentFrame) return null
  const { frame } = currentFrame

  return (
    <aside className="side" aria-label="Frame details">
      <h2>Frame</h2>
      <dl className="meta">
        <dt>Dates (UTC)</dt>
        <dd>{frame.date_range.join(' … ')}</dd>
        <dt>Detectors</dt>
        <dd>{frame.detectors.map((d) => `D${d}`).join(', ')}</dd>
        <dt>λ</dt>
        <dd>{frame.lambda_um.join('–')} µm</dd>
        <dt>Exposures</dt>
        <dd>{frame.n_exposures}</dd>
        {selectedPixel && (
          <>
            <dt>Pixel</dt>
            <dd>
              x {selectedPixel.x}, y {selectedPixel.y}
            </dd>
          </>
        )}
      </dl>
      {frame.warnings.length > 0 && (
        <ul className="warnings">
          {frame.warnings.map((w) => (
            <li key={w} className="warn">
              {w}
            </li>
          ))}
        </ul>
      )}
      <label>
        <input type="checkbox" checked={showFlags} onChange={(e) => onShowFlagsChange(e.target.checked)} /> Flags
        overlay (bad, saturation)
      </label>
    </aside>
  )
}

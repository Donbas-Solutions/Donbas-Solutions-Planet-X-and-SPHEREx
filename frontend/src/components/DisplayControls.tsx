import { useAppState } from '../hooks/useAppState'
import type { StretchKind, ViewMode } from '../lib/urlState'
import { MAX_ZOOM, type Zoom } from './Viewer'

export interface Range {
  vmin: number
  vmax: number
}

interface Props {
  zoom: Zoom
  onZoomChange: (zoom: Zoom) => void
  showMarkers: boolean
  onShowMarkersChange: (show: boolean) => void
  range: Range
  bounds: Range
  onRangeChange: (range: Range | null) => void
  diffRange: number | null
  diffBound: number
  onDiffRangeChange: (r: number | null) => void
}

const ZOOMS: readonly Zoom[] = ['fit', 1, 2, 3, 4, 6, MAX_ZOOM]
const STRETCHES: readonly StretchKind[] = ['asinh', 'linear', 'log']

function fmt(v: number): string {
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toPrecision(3)
}

export default function DisplayControls(props: Props) {
  const { zoom, onZoomChange, showMarkers, onShowMarkersChange, range, bounds, onRangeChange } = props
  const { diffRange, diffBound, onDiffRangeChange } = props
  const { params, setParams } = useAppState()
  const isDiff = params.view === 'diff'
  const step = (bounds.vmax - bounds.vmin) / 500 || 1e-6

  const setView = (view: ViewMode) => setParams({ view })

  return (
    <section className="display-controls" aria-label="Display">
      <fieldset className="segmented">
        <legend className="visually-hidden">View</legend>
        <button type="button" aria-pressed={!isDiff} onClick={() => setView('blink')}>
          Blink
        </button>
        <button type="button" aria-pressed={isDiff} onClick={() => setView('diff')}>
          Difference B − A
        </button>
      </fieldset>
      <label>
        Zoom
        <select
          value={String(zoom)}
          onChange={(e) => onZoomChange(e.target.value === 'fit' ? 'fit' : Number(e.target.value))}
        >
          {ZOOMS.map((z) => (
            <option key={z} value={String(z)}>
              {z === 'fit' ? 'Fit' : `${z}×`}
            </option>
          ))}
        </select>
      </label>
      <label>
        <input type="checkbox" checked={showMarkers} onChange={(e) => onShowMarkersChange(e.target.checked)} /> Expected
        position
      </label>
      {isDiff ? (
        <label>
          Range ±
          <input
            type="range"
            min={diffBound / 100}
            max={diffBound}
            step={diffBound / 500}
            value={diffRange ?? diffBound / 4}
            onChange={(e) => onDiffRangeChange(Number(e.target.value))}
          />
          <span className="muted">{fmt(diffRange ?? diffBound / 4)}</span>
          <button type="button" onClick={() => onDiffRangeChange(null)}>
            Auto
          </button>
        </label>
      ) : (
        <>
          <label>
            Stretch
            <select value={params.stretch} onChange={(e) => setParams({ stretch: e.target.value as StretchKind })}>
              {STRETCHES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Min
            <input
              type="range"
              min={bounds.vmin}
              max={bounds.vmax}
              step={step}
              value={range.vmin}
              onChange={(e) => onRangeChange({ vmin: Math.min(Number(e.target.value), range.vmax - step), vmax: range.vmax })}
            />
            <span className="muted">{fmt(range.vmin)}</span>
          </label>
          <label>
            Max
            <input
              type="range"
              min={bounds.vmin}
              max={bounds.vmax}
              step={step}
              value={range.vmax}
              onChange={(e) => onRangeChange({ vmin: range.vmin, vmax: Math.max(Number(e.target.value), range.vmin + step) })}
            />
            <span className="muted">{fmt(range.vmax)}</span>
          </label>
          <button type="button" onClick={() => onRangeChange(null)}>
            Reset
          </button>
        </>
      )}
    </section>
  )
}

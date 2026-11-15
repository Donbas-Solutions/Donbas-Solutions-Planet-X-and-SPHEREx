import { useMemo, useState } from 'react'
import { useAppState } from '../../hooks/useAppState'
import { useGaiaOverlay } from '../../hooks/useGaiaOverlay'
import { useHipsLayers } from '../../hooks/useHipsLayers'
import { HIPS_LAYERS } from '../../lib/hips'
import AladinPanel, { type SkyMarker } from '../AladinPanel'

const NO_MARKERS: readonly SkyMarker[] = []
/** The context view is wider than the blinked field, so the surroundings are visible. */
const CONTEXT_FOV_FACTOR = 3

/** Other surveys of the same field (FR-19). An image-server outage affects only this panel. */
export default function ContextPanel() {
  const { sequence } = useAppState()
  const status = useHipsLayers()
  const gaia = useGaiaOverlay()
  const [chosen, setChosen] = useState<string | null>(null)

  const markers = useMemo<readonly SkyMarker[]>(
    () =>
      gaia.status === 'ready'
        ? gaia.field.stars.map((s) => ({ id: s.source_id, ra: s.ra, dec: s.dec }))
        : NO_MARKERS,
    [gaia],
  )

  if (!sequence) return null
  const isChecking = HIPS_LAYERS.some((l) => (status[l.id] ?? 'checking') === 'checking')
  const up = HIPS_LAYERS.filter((l) => status[l.id] === 'up')
  const layer = up.find((l) => l.id === chosen) ?? up[0]

  if (!layer) {
    return isChecking ? (
      <p className="muted" aria-live="polite">
        Checking the sky-survey image servers…
      </p>
    ) : (
      <p className="warn" aria-live="polite">
        No sky-survey image server answers right now (CDS and the IRSA mirror), so there is no context view. The
        SPHEREx frames above are not affected.
      </p>
    )
  }

  const { grid } = sequence
  return (
    <div className="context">
      <p className="muted">
        The same field in another survey, {CONTEXT_FOV_FACTOR}× wider than the frames above, north up and east left.
        It helps to tell what a source is; it is not part of the blink.
      </p>
      <label>
        Survey
        <select value={layer.id} onChange={(e) => setChosen(e.target.value)}>
          {HIPS_LAYERS.map((l) => {
            const state = status[l.id] ?? 'checking'
            return (
              <option key={l.id} value={l.id} disabled={state !== 'up'}>
                {l.label}
                {state === 'down' ? ' (server not answering)' : state === 'checking' ? ' (checking…)' : ''}
              </option>
            )
          })}
        </select>
      </label>
      <p className="muted small">
        {layer.note}
        {markers.length > 0 && ' Diamonds: the Gaia DR3 stars of the overlay, at the date of the middle frame.'}
      </p>
      <AladinPanel
        ra={grid.ra}
        dec={grid.dec}
        fovDeg={(grid.fov_arcmin / 60) * CONTEXT_FOV_FACTOR}
        surveyUrl={layer.url}
        markers={markers}
        markerLabel="Gaia DR3"
      />
    </div>
  )
}

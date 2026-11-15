import type { GaiaStar } from '../api/types'
import { useAppState } from '../hooks/useAppState'
import type { GaiaLoad } from '../hooks/useGaiaOverlay'
import { isMover, MOVER_MIN_SHIFT_PX, pmPositionAngleDeg, totalPmMasyr } from '../lib/gaia'

const MAX_LISTED = 3

interface Props {
  load: GaiaLoad
}

function describe(star: GaiaStar): string {
  const pa = pmPositionAngleDeg(star)
  const g = star.g === null ? '' : `, G ${star.g.toFixed(1)}`
  const toward = pa === null ? '' : ` toward PA ${pa.toFixed(0)}°`
  return `Gaia DR3 ${star.source_id}${g}, ${(totalPmMasyr(star) / 1000).toFixed(2)}″/yr${toward}`
}

/** What the Gaia markers show, or why there are none. */
export default function GaiaStatus({ load }: Props) {
  const { sequence } = useAppState()
  if (load.status === 'off' || !sequence) return null
  if (load.status === 'loading') {
    return (
      <p className="muted small" aria-live="polite">
        Loading Gaia DR3 stars…
      </p>
    )
  }
  if (load.status === 'unavailable') {
    return (
      <p className="warn small" aria-live="polite">
        {load.message}
      </p>
    )
  }
  const { stars } = load.field
  const movers = stars.filter((s) => isMover(s, sequence.grid, load.spanYears))
  const listed = movers.slice(0, MAX_LISTED).map(describe).join('; ')
  return (
    <p className="muted small" aria-live="polite">
      <span className="gaia-key" aria-hidden="true" /> Gaia DR3: {stars.length} known{' '}
      {stars.length === 1 ? 'star' : 'stars'} in this field (the brightest, G ≤ 19), each drawn where its catalog
      proper motion puts it on the frame date.{' '}
      {movers.length === 0
        ? `None moves ≥ ${MOVER_MIN_SHIFT_PX} px during this sequence.`
        : `${movers.length} ${movers.length === 1 ? 'moves' : 'move'} ≥ ${MOVER_MIN_SHIFT_PX} px during this sequence (larger marker): ${listed}${movers.length > MAX_LISTED ? '; …' : ''}.`}
    </p>
  )
}

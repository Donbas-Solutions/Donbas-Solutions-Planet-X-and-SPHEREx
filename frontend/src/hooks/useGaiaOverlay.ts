import { useEffect, useState } from 'react'
import { fetchOverlays } from '../api/overlays'
import type { Grid } from '../api/types'
import { sequenceSpan, type GaiaField } from '../lib/gaia'
import { useAppState } from './useAppState'

export type GaiaLoad =
  | { status: 'off' }
  | { status: 'loading' }
  | { status: 'ready'; field: GaiaField; spanYears: number }
  | { status: 'unavailable'; message: string }

interface Request {
  grid: Grid
  mjd: number
  spanYears: number
}

async function load(request: Request, signal: AbortSignal): Promise<GaiaLoad> {
  const overlays = await fetchOverlays(request.grid, request.mjd, signal)
  if (overlays.unavailable.includes('gaia')) {
    return { status: 'unavailable', message: 'The Gaia archive did not answer. Untick and tick the box to try again.' }
  }
  return { status: 'ready', field: { stars: overlays.gaia, refMjd: request.mjd }, spanYears: request.spanYears }
}

/** Gaia DR3 stars of the sequence's field (FR-18), fetched once per sequence while the overlay is switched on. */
export function useGaiaOverlay(): GaiaLoad {
  const { sequence, params } = useAppState()
  const span = sequence ? sequenceSpan(sequence.frames) : null
  const request: Request | null =
    params.gaia && sequence && span ? { grid: sequence.grid, mjd: span.midMjd, spanYears: span.years } : null
  const key = request ? JSON.stringify(request) : null
  const [result, setResult] = useState<{ key: string; load: GaiaLoad } | null>(null)

  useEffect(() => {
    if (key === null) return
    const ac = new AbortController()
    load(JSON.parse(key) as Request, ac.signal).then(
      (loaded) => setResult({ key, load: loaded }),
      (e: unknown) => {
        if (ac.signal.aborted) return
        const reason = e instanceof Error ? e.message : String(e)
        setResult({ key, load: { status: 'unavailable', message: `Gaia stars are unavailable: ${reason}.` } })
      },
    )
    return () => ac.abort()
  }, [key])

  if (key === null) return { status: 'off' }
  return result?.key === key ? result.load : { status: 'loading' }
}

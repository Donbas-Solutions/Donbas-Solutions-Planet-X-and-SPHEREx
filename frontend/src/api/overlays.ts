import { FOV_MAX_ARCMIN, FOV_MIN_ARCMIN } from '../lib/urlState'
import type { Grid, Overlays } from './types'

function isOverlays(v: unknown): v is Overlays {
  return (
    typeof v === 'object' &&
    v !== null &&
    'gaia' in v &&
    Array.isArray(v.gaia) &&
    'unavailable' in v &&
    Array.isArray(v.unavailable)
  )
}

/** Catalog sources of the frame grid's field at their positions on `mjd` (docs/api.md). */
export async function fetchOverlays(grid: Grid, mjd: number, signal: AbortSignal): Promise<Overlays> {
  const fov = Math.min(FOV_MAX_ARCMIN, Math.max(FOV_MIN_ARCMIN, grid.fov_arcmin))
  const params = new URLSearchParams({
    ra: String(grid.ra),
    dec: String(grid.dec),
    fov: String(fov),
    mjd: String(mjd),
  })
  let res: Response
  try {
    res = await fetch(new URL(`/api/overlays?${params}`, window.location.href), { signal })
  } catch (e) {
    if (signal.aborted) throw e
    throw new Error('the live server is not reachable')
  }
  if (res.status === 501) throw new Error('this server has no catalog overlays yet')
  const body: unknown = res.ok && res.headers.get('content-type')?.includes('json') ? await res.json() : null
  if (body === null) throw new Error('the live server is not reachable')
  if (!isOverlays(body)) throw new Error('the response is not an overlay list')
  return body
}

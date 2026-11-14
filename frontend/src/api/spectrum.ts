import type { Spectrum } from './types'
import type { ProperMotion } from '../lib/urlState'

function isSpectrum(v: unknown): v is Spectrum {
  return typeof v === 'object' && v !== null && 'points' in v && Array.isArray(v.points)
}

export function liveSpectrumUrl(ra: number, dec: number, pm: ProperMotion | null): URL {
  const params = new URLSearchParams({ ra: String(ra), dec: String(dec) })
  if (pm) {
    params.set('pmra', String(pm.pmra))
    params.set('pmdec', String(pm.pmdec))
    params.set('ref_epoch', String(pm.epoch))
  }
  return new URL(`/api/spectrum?${params}`, window.location.href)
}

export async function fetchSpectrum(url: URL, signal: AbortSignal): Promise<Spectrum> {
  let res: Response
  try {
    res = await fetch(url, { signal })
  } catch (e) {
    if (signal.aborted) throw e
    throw new Error('the server is unreachable')
  }
  if (res.status === 501) throw new Error('live spectra are not available on this server yet')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const body: unknown = res.headers.get('content-type')?.includes('json') ? await res.json() : null
  if (!isSpectrum(body)) throw new Error('the response is not a spectrum')
  return body
}

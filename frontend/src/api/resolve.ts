/** Mirror of `ResolveResult` in backend/app/models.py (not yet in types.ts, which Track A owns). */
export interface ResolveResult {
  name: string
  /** ICRS degrees at ref_epoch */
  ra: number
  dec: number
  /** Julian year */
  ref_epoch: number
  /** mas/yr, includes cos(dec) */
  pmra: number | null
  pmdec: number | null
  parallax: number | null
  source: string
}

export type ResolveOutcome =
  | { ok: true; result: ResolveResult }
  | { ok: false; reason: 'not_found' | 'unavailable'; detail: string }

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isNumberOrNull = (v: unknown): v is number | null => v === null || v === undefined || isNumber(v)

function parseResolveResult(v: unknown): ResolveResult | null {
  if (!isRecord(v)) return null
  const { name, ra, dec, ref_epoch, pmra, pmdec, parallax, source } = v
  if (typeof name !== 'string' || !isNumber(ra) || !isNumber(dec) || !isNumber(ref_epoch)) return null
  if (!isNumberOrNull(pmra) || !isNumberOrNull(pmdec) || !isNumberOrNull(parallax)) return null
  if (!(ra >= 0 && ra < 360 && dec >= -90 && dec <= 90)) return null
  return {
    name,
    ra,
    dec,
    ref_epoch,
    pmra: pmra ?? null,
    pmdec: pmdec ?? null,
    parallax: parallax ?? null,
    source: typeof source === 'string' ? source : 'unknown',
  }
}

/** Rejects only on abort; every other failure is an outcome the UI can show. */
export async function resolveName(name: string, signal: AbortSignal): Promise<ResolveOutcome> {
  let res: Response
  try {
    res = await fetch(`/api/resolve?${new URLSearchParams({ name })}`, { signal })
  } catch (e) {
    if (signal.aborted) throw e
    return { ok: false, reason: 'unavailable', detail: 'the server is unreachable' }
  }
  if (res.status === 404) return { ok: false, reason: 'not_found', detail: `“${name}” was not found` }
  if (!res.ok) return { ok: false, reason: 'unavailable', detail: `HTTP ${res.status}` }
  const result = parseResolveResult(await res.json().catch(() => null))
  if (!result) return { ok: false, reason: 'unavailable', detail: 'unexpected response' }
  return { ok: true, result }
}

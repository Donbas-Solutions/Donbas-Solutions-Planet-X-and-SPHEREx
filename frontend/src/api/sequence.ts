import type { JobStatus, Sequence } from './types'

export interface SequenceQuery {
  ra: number
  dec: number
  fovArcmin: number
  pm: { pmra: number; pmdec: number; epoch: number } | null
}

export interface JobProgress {
  stage: string
  done: number
  total: number
}

/** An HTTP or network failure with a message that can be shown to the user as is. */
export class ApiError extends Error {
  readonly status: number | null
  constructor(message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export interface LiveSequence {
  seq: Sequence
  /** Base for relative frame URLs. */
  base: URL
}

const POLL_FIRST_MS = 1000
const POLL_MAX_MS = 3000

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const id = window.setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      window.clearTimeout(id)
      reject(signal.reason)
    })
  })
}

function detailOf(body: unknown): string | null {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const { detail } = body
    if (typeof detail === 'string') return detail
  }
  return null
}

async function getJson(url: URL, signal: AbortSignal): Promise<{ status: number; body: unknown }> {
  let res: Response
  try {
    res = await fetch(url, { signal })
  } catch (e) {
    if (signal.aborted) throw e
    throw new ApiError('The SPHEREx Blink server is unreachable.', null)
  }
  const isJson = res.headers.get('content-type')?.includes('json') ?? false
  const body: unknown = isJson ? await res.json().catch(() => null) : null
  if (res.ok && !isJson) throw new ApiError('The SPHEREx Blink server is unreachable.', null)
  if (res.ok) return { status: res.status, body }

  const detail = detailOf(body)
  if (res.status === 404) throw new ApiError(detail ?? 'Not found.', 404)
  if (res.status === 422) throw new ApiError(`The request was rejected: ${detail ?? 'invalid parameters'}.`, 422)
  if (res.status === 501) throw new ApiError('Live archive requests are not available on this server yet.', 501)
  if (res.status >= 500) {
    throw new ApiError(`The server or the IRSA archive is unavailable right now (HTTP ${res.status}).`, res.status)
  }
  throw new ApiError(`Request failed (HTTP ${res.status}${detail ? `: ${detail}` : ''}).`, res.status)
}

/** `true` when /api/health answers with JSON: on static hosting the path serves index.html instead. */
export async function isBackendOnline(signal: AbortSignal): Promise<boolean> {
  try {
    await getJson(new URL('/api/health', window.location.href), signal)
    return true
  } catch (e) {
    if (signal.aborted) throw e
    return false
  }
}

function sequenceUrl(q: SequenceQuery): URL {
  const params = new URLSearchParams({
    ra: String(q.ra),
    dec: String(q.dec),
    fov: String(q.fovArcmin),
    // All detectors: switching detectors in the UI then filters loaded frames instead of refetching (FR-4).
    det: 'all',
    mode: 'visit_stack',
  })
  if (q.pm) {
    params.set('pmra', String(q.pm.pmra))
    params.set('pmdec', String(q.pm.pmdec))
    params.set('ref_epoch', String(q.pm.epoch))
  }
  return new URL(`/api/sequence?${params}`, window.location.href)
}

function isSequence(v: unknown): v is Sequence {
  return typeof v === 'object' && v !== null && 'frames' in v && Array.isArray(v.frames) && 'grid' in v
}

function isJobStatus(v: unknown): v is JobStatus {
  return typeof v === 'object' && v !== null && 'status' in v && 'progress' in v
}

/**
 * GET /api/sequence; on 202 polls /api/jobs/{id} (1 s, backing off to 3 s) until done or error.
 * Cancel by aborting `signal`: there is no server-side cancel, the job simply stops being polled.
 */
export async function fetchLiveSequence(
  q: SequenceQuery,
  signal: AbortSignal,
  onProgress: (p: JobProgress) => void,
): Promise<LiveSequence> {
  const url = sequenceUrl(q)
  const first = await getJson(url, signal)
  if (isSequence(first.body)) return { seq: first.body, base: url }

  const jobId =
    typeof first.body === 'object' && first.body !== null && 'job_id' in first.body ? first.body.job_id : null
  if (first.status !== 202 || typeof jobId !== 'string') throw new ApiError('Unexpected answer from the server.', null)

  const jobUrl = new URL(`/api/jobs/${encodeURIComponent(jobId)}`, window.location.href)
  let delayMs = POLL_FIRST_MS
  for (;;) {
    await sleep(delayMs, signal)
    delayMs = Math.min(POLL_MAX_MS, delayMs * 1.5)
    const { body } = await getJson(jobUrl, signal)
    if (!isJobStatus(body)) throw new ApiError('Unexpected job status from the server.', null)
    onProgress(body.progress)
    if (body.status === 'error') throw new ApiError(body.error ?? 'The request failed on the server.', null)
    if (body.status === 'done') {
      if (body.result) return { seq: body.result, base: jobUrl }
      const again = await getJson(url, signal)
      if (isSequence(again.body)) return { seq: again.body, base: url }
      throw new ApiError('The job finished but no sequence came back.', null)
    }
  }
}

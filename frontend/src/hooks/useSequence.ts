import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, fetchLiveSequence, type JobProgress, type SequenceQuery } from '../api/sequence'
import type { Sequence } from '../api/types'
import { loadFrames, loadSequence, type LoadedFrame } from '../lib/frames'
import { findPreset, type PresetId } from '../lib/presets'

export type SequenceLoad =
  | { status: 'idle' }
  | { status: 'loading'; message: string; progress: JobProgress | null; canCancel: boolean }
  | { status: 'ready'; seq: Sequence; frames: readonly LoadedFrame[]; notice: string | null }
  | { status: 'empty'; message: string }
  | { status: 'error'; message: string; canRetry: boolean }
  | { status: 'cancelled' }

export type LoadableSource =
  | { kind: 'manifest'; url: string; isPrebaked: boolean }
  | { kind: 'live'; query: SequenceQuery; fallbackPreset: PresetId | null }

const NO_COVERAGE = 'SPHEREx has no images here yet. Try a test target, or a different position.'

function prebakedUrl(id: PresetId): string {
  return `${import.meta.env.BASE_URL}prebaked/${id}/sequence.json`
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

/** The server or the archive is down, as opposed to a bad request: worth falling back to a prebaked bundle. */
function isOutage(e: unknown): boolean {
  return e instanceof ApiError && (e.status === null || e.status === 501 || e.status >= 500)
}

async function run(
  source: LoadableSource,
  signal: AbortSignal,
  report: (load: SequenceLoad) => void,
): Promise<SequenceLoad> {
  let seq: Sequence
  let base: URL
  let notice: string | null = null

  if (source.kind === 'manifest') {
    report({ status: 'loading', message: 'Loading the sequence…', progress: null, canCancel: false })
    try {
      ;({ seq, base } = await loadSequence(source.url, signal))
    } catch (e) {
      if (signal.aborted) throw e
      const message = source.isPrebaked
        ? `The prebaked bundle for this test target is not available (${errorMessage(e)}).`
        : errorMessage(e)
      return { status: 'error', message, canRetry: true }
    }
  } else {
    report({ status: 'loading', message: 'Asking the archive…', progress: null, canCancel: true })
    try {
      ;({ seq, base } = await fetchLiveSequence(source.query, signal, (progress) =>
        report({ status: 'loading', message: 'Preparing the sequence…', progress, canCancel: true }),
      ))
    } catch (e) {
      if (signal.aborted) throw e
      if (e instanceof ApiError && e.status === 404) return { status: 'empty', message: NO_COVERAGE }
      const preset = source.fallbackPreset ? findPreset(source.fallbackPreset) : undefined
      if (!preset || !isOutage(e)) return { status: 'error', message: errorMessage(e), canRetry: true }
      ;({ seq, base } = await loadSequence(prebakedUrl(preset.id), signal))
      notice = `Live data is unavailable (${errorMessage(e)}) Showing the prebaked bundle for ${preset.name}.`
    }
  }

  if (seq.frames.length === 0) return { status: 'empty', message: NO_COVERAGE }
  const frames = await loadFrames(seq, base, signal, (done, total) =>
    report({ status: 'loading', message: 'Downloading frames…', progress: { stage: 'frames', done, total }, canCancel: true }),
  )
  return { status: 'ready', seq, frames, notice }
}

/** Loads a sequence (static bundle or live job) and all its frames; `null` = nothing to load. */
export function useSequence(source: LoadableSource | null): {
  load: SequenceLoad
  retry: () => void
  cancel: () => void
} {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ key: string; load: SequenceLoad } | null>(null)
  const controller = useRef<AbortController | null>(null)
  // Callers rebuild `source` on every render; its serialization is the stable identity the load depends on.
  const id = source ? JSON.stringify(source) : null
  const key = `${attempt}:${id}`

  useEffect(() => {
    if (id === null) return
    const current = JSON.parse(id) as LoadableSource
    const ac = new AbortController()
    controller.current = ac
    const settle = (load: SequenceLoad) => {
      if (!ac.signal.aborted) setResult({ key, load })
    }
    run(current, ac.signal, settle).then(settle, (e: unknown) => {
      if (ac.signal.aborted) return
      console.error(e)
      settle({ status: 'error', message: errorMessage(e), canRetry: true })
    })
    return () => ac.abort()
  }, [id, key])

  const retry = useCallback(() => setAttempt((a) => a + 1), [])
  const cancel = useCallback(() => {
    controller.current?.abort()
    setResult({ key, load: { status: 'cancelled' } })
  }, [key])

  if (source === null) return { load: { status: 'idle' }, retry, cancel }
  const load: SequenceLoad =
    result?.key === key ? result.load : { status: 'loading', message: 'Starting…', progress: null, canCancel: false }
  return { load, retry, cancel }
}

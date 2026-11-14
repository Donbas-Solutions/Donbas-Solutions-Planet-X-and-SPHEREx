import { useCallback, useEffect, useState } from 'react'
import type { Sequence } from '../api/types'
import { loadFrame, loadSequence, type LoadedFrame } from '../lib/frames'

export type SequenceLoad =
  | { status: 'loading' }
  | { status: 'ready'; seq: Sequence; frames: readonly LoadedFrame[] }
  | { status: 'error'; message: string }

const LOADING: SequenceLoad = { status: 'loading' }

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

async function loadAll(manifestUrl: string, signal: AbortSignal): Promise<SequenceLoad> {
  const { seq, base } = await loadSequence(manifestUrl, signal)
  const frames = await Promise.all(seq.frames.map((f) => loadFrame(f, base, signal)))
  return { status: 'ready', seq, frames }
}

export function useSequence(manifestUrl: string): { load: SequenceLoad; retry: () => void } {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ key: string; load: SequenceLoad } | null>(null)
  const key = `${attempt}:${manifestUrl}`

  useEffect(() => {
    const ac = new AbortController()
    const settle = (load: SequenceLoad) => {
      if (!ac.signal.aborted) setResult({ key, load })
    }
    loadAll(manifestUrl, ac.signal).then(settle, (e: unknown) => {
      if (!ac.signal.aborted) console.error(e)
      settle({ status: 'error', message: errorMessage(e) })
    })
    return () => ac.abort()
  }, [manifestUrl, key])

  const retry = useCallback(() => setAttempt((a) => a + 1), [])
  return { load: result?.key === key ? result.load : LOADING, retry }
}

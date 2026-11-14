import { useEffect, useEffectEvent, useState } from 'react'
import { resolveName, type ResolveOutcome, type ResolveResult } from '../api/resolve'

export type ResolveLoad = { status: 'idle' } | { status: 'resolving' } | { status: 'failed'; message: string }

function failureMessage(outcome: Extract<ResolveOutcome, { ok: false }>): string {
  return outcome.reason === 'not_found'
    ? `Not found: ${outcome.detail}. Check the spelling or enter coordinates.`
    : `Name lookup is unavailable right now (${outcome.detail}). Enter RA/Dec coordinates instead, or pick a test target.`
}

/** Resolves `name` (null = nothing to do) and hands a successful result to `onResolved`. */
export function useNameResolution(name: string | null, onResolved: (r: ResolveResult) => void): ResolveLoad {
  const [failure, setFailure] = useState<{ name: string; message: string } | null>(null)
  const handleResolved = useEffectEvent(onResolved)

  useEffect(() => {
    if (name === null) return
    const ac = new AbortController()
    resolveName(name, ac.signal).then(
      (outcome) => {
        if (ac.signal.aborted) return
        if (outcome.ok) handleResolved(outcome.result)
        else setFailure({ name, message: failureMessage(outcome) })
      },
      () => {},
    )
    return () => ac.abort()
  }, [name])

  if (name === null) return { status: 'idle' }
  return failure?.name === name ? { status: 'failed', message: failure.message } : { status: 'resolving' }
}

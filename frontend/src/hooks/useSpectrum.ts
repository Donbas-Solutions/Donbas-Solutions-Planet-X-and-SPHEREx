import { useEffect, useState } from 'react'
import { fetchSpectrum, liveSpectrumUrl } from '../api/spectrum'
import type { Sequence, Spectrum } from '../api/types'
import { presetNear } from '../lib/presets'
import type { SequenceSource } from '../lib/urlState'
import { useAppState, type TargetInfo } from './useAppState'

export type SpectrumOrigin = 'live' | 'bundle'

export type SpectrumLoad =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; spectrum: Spectrum; origin: SpectrumOrigin; notice: string | null }
  | { status: 'unavailable'; message: string }

interface Candidate {
  url: string
  origin: SpectrumOrigin
}

/** Order from docs/api.md: live endpoint → the bundle's `meta.spectrum` → unavailable. */
function candidates(source: SequenceSource, seq: Sequence | null, target: TargetInfo | null): Candidate[] {
  if (source.kind === 'manifest') {
    if (!seq?.meta.spectrum) return []
    const base = new URL(source.url, window.location.href)
    return [{ url: new URL(seq.meta.spectrum, base).href, origin: 'bundle' }]
  }
  if (source.kind !== 'live' || !target) return []
  const list: Candidate[] = [{ url: liveSpectrumUrl(target.ra, target.dec, target.pm).href, origin: 'live' }]
  const preset = presetNear(target.ra, target.dec)
  if (preset) {
    const url = new URL(`${import.meta.env.BASE_URL}prebaked/${preset.id}/spectrum.json`, window.location.href)
    list.push({ url: url.href, origin: 'bundle' })
  }
  return list
}

function reason(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

async function loadFirst(list: readonly Candidate[], signal: AbortSignal): Promise<SpectrumLoad> {
  const failures: string[] = []
  for (const c of list) {
    try {
      const spectrum = await fetchSpectrum(new URL(c.url), signal)
      const notice = failures.length > 0 ? `Live spectrum unavailable (${failures.join('; ')}); showing the bundled one.` : null
      return { status: 'ready', spectrum, origin: c.origin, notice }
    } catch (e) {
      if (signal.aborted) throw e
      failures.push(reason(e))
    }
  }
  return { status: 'unavailable', message: `The spectrum could not be loaded (${failures.join('; ')}).` }
}

/** The target's spectrum (one point per exposure); also the source of the light curve. */
export function useSpectrum(): SpectrumLoad {
  const { source, sequence, target } = useAppState()
  const list = candidates(source, sequence, target)
  const key = JSON.stringify(list)
  const [result, setResult] = useState<{ key: string; load: SpectrumLoad } | null>(null)

  useEffect(() => {
    const current = JSON.parse(key) as Candidate[]
    if (current.length === 0) return
    const ac = new AbortController()
    loadFirst(current, ac.signal).then(
      (load) => setResult({ key, load }),
      (e: unknown) => {
        if (!ac.signal.aborted) setResult({ key, load: { status: 'unavailable', message: reason(e) } })
      },
    )
    return () => ac.abort()
  }, [key])

  if (!sequence) return { status: 'idle' }
  if (list.length === 0) {
    const message =
      source.kind === 'manifest'
        ? 'This sequence has no bundled spectrum.'
        : 'Spectra of a position need the live server, which is not reachable.'
    return { status: 'unavailable', message }
  }
  return result?.key === key ? result.load : { status: 'loading' }
}

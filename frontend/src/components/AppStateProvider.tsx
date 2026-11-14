import { useCallback, useMemo, useState, type ReactNode } from 'react'
import type { ResolveResult } from '../api/resolve'
import type { PixelPos } from '../api/types'
import type { LoadedFrame } from '../lib/frames'
import { buildPlaylist } from '../lib/playlist'
import { findPreset, PRESET_EPOCH } from '../lib/presets'
import type { SequenceSource, ViewParams } from '../lib/urlState'
import { AppStateContext, type AppState, type TargetInfo } from '../hooks/useAppState'
import { useNameResolution } from '../hooks/useNameResolution'
import { useSequence, type SequenceLoad } from '../hooks/useSequence'
import type { SetViewParams } from '../hooks/useViewParams'

interface Props {
  params: ViewParams
  setParams: SetViewParams
  source: SequenceSource
  children: ReactNode
}

const NO_FRAMES: readonly LoadedFrame[] = []

function targetFromParams(p: ViewParams): TargetInfo | null {
  const preset = p.target ? findPreset(p.target) : undefined
  if (preset) {
    const { name, ra, dec, pmra, pmdec } = preset
    return { name, ra, dec, pm: { pmra, pmdec, epoch: PRESET_EPOCH } }
  }
  if (p.ra !== null && p.dec !== null) return { name: p.name, ra: p.ra, dec: p.dec, pm: p.pm }
  return null
}

export default function AppStateProvider({ params, setParams, source, children }: Props) {
  const manifest = useSequence(source.kind === 'manifest' ? source.url : null)

  const handleResolved = useCallback(
    (r: ResolveResult) =>
      setParams({
        ra: r.ra,
        dec: r.dec,
        pm: r.pmra !== null && r.pmdec !== null ? { pmra: r.pmra, pmdec: r.pmdec, epoch: r.ref_epoch } : null,
      }),
    [setParams],
  )
  const resolution = useNameResolution(source.kind === 'resolve' ? source.name : null, handleResolved)

  const [frameIndex, setFrameIndex] = useState(0)
  const [selectedPixel, setSelectedPixel] = useState<PixelPos | null>(null)

  const load = useMemo<SequenceLoad>(() => {
    switch (source.kind) {
      case 'manifest': {
        const l = manifest.load ?? { status: 'loading', message: 'Loading…' }
        if (l.status === 'error' && source.isPrebaked) {
          return { status: 'error', message: `The prebaked bundle for this test target is not available (${l.message}).` }
        }
        return l
      }
      case 'resolve':
        return resolution.status === 'failed'
          ? { status: 'error', message: resolution.message }
          : { status: 'loading', message: `Looking up “${source.name}”…` }
      case 'live':
        return {
          status: 'error',
          message: 'Live SPHEREx archive requests are not connected yet. Pick a test target to see real data.',
        }
    }
  }, [source, manifest.load, resolution])

  const value = useMemo<AppState>(() => {
    const sequence = load.status === 'ready' ? load.seq : null
    const frames = load.status === 'ready' ? load.frames : NO_FRAMES
    const playlist = buildPlaylist(frames, params.det)
    const list = playlist.frames
    const index = Math.min(Math.max(frameIndex, 0), Math.max(list.length - 1, 0))
    const fromSequence: TargetInfo | null = sequence
      ? { name: sequence.meta.target_name, ra: sequence.grid.ra, dec: sequence.grid.dec, pm: null }
      : null
    return {
      params,
      setParams,
      source,
      load,
      retry: manifest.retry,
      sequence,
      frames,
      playlist,
      target: targetFromParams(params) ?? fromSequence,
      frameIndex: index,
      currentFrame: list[index] ?? null,
      frameA: list.find((f) => f.frame.id === params.a) ?? list[0] ?? null,
      frameB: list.find((f) => f.frame.id === params.b) ?? list[list.length - 1] ?? null,
      selectedPixel,
      setFrameIndex,
      setSelectedPixel,
    }
  }, [params, setParams, source, load, manifest.retry, frameIndex, selectedPixel])

  return <AppStateContext value={value}>{children}</AppStateContext>
}

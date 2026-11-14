import { useCallback, useMemo, useState, type ReactNode } from 'react'
import type { ResolveResult } from '../api/resolve'
import type { PixelPos } from '../api/types'
import type { LoadedFrame } from '../lib/frames'
import { buildPlaylist } from '../lib/playlist'
import { findPreset, PRESET_EPOCH, presetNear } from '../lib/presets'
import type { SequenceSource, ViewParams } from '../lib/urlState'
import { AppStateContext, type AppState, type TargetInfo } from '../hooks/useAppState'
import { useNameResolution } from '../hooks/useNameResolution'
import { useSequence, type LoadableSource, type SequenceLoad } from '../hooks/useSequence'
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

function loadableSource(s: SequenceSource): LoadableSource | null {
  switch (s.kind) {
    case 'manifest':
      return s
    case 'live':
      return {
        kind: 'live',
        query: { ra: s.ra, dec: s.dec, fovArcmin: s.fovArcmin, pm: s.pm },
        fallbackPreset: presetNear(s.ra, s.dec)?.id ?? null,
      }
    case 'resolve':
    case 'landing':
      return null
  }
}

export default function AppStateProvider({ params, setParams, source, children }: Props) {
  const sequence = useSequence(loadableSource(source))

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
    if (source.kind !== 'resolve') return sequence.load
    return resolution.status === 'failed'
      ? { status: 'error', message: resolution.message, canRetry: false }
      : { status: 'loading', message: `Looking up “${source.name}”…`, progress: null, canCancel: false }
  }, [source, sequence.load, resolution])

  const value = useMemo<AppState>(() => {
    const seq = load.status === 'ready' ? load.seq : null
    const frames = load.status === 'ready' ? load.frames : NO_FRAMES
    const playlist = buildPlaylist(frames, params.det)
    const list = playlist.frames
    const index = Math.min(Math.max(frameIndex, 0), Math.max(list.length - 1, 0))
    const fromSequence: TargetInfo | null = seq
      ? { name: seq.meta.target_name, ra: seq.grid.ra, dec: seq.grid.dec, pm: null }
      : null
    return {
      params,
      setParams,
      source,
      load,
      retry: sequence.retry,
      cancel: sequence.cancel,
      sequence: seq,
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
  }, [params, setParams, source, load, sequence.retry, sequence.cancel, frameIndex, selectedPixel])

  return <AppStateContext value={value}>{children}</AppStateContext>
}

import { useMemo, useState } from 'react'
import type { Stretch } from '../api/types'
import { useAppState } from '../hooks/useAppState'
import { useGaiaOverlay } from '../hooks/useGaiaOverlay'
import { prefersReducedMotion, usePlayback } from '../hooks/usePlayback'
import { usePlayerKeys } from '../hooks/usePlayerKeys'
import { BLUE_ORANGE, GREY } from '../lib/colormap'
import { diffFrames } from '../lib/diff'
import { overlayLayers } from '../lib/flags'
import { gaiaMarkers, type GaiaMarker } from '../lib/gaia'
import { detectorKey, detectorLabel, missingDetectors } from '../lib/playlist'
import { finitePercentiles } from '../lib/stats'
import DiffLegend from './DiffLegend'
import DisplayControls, { type Range } from './DisplayControls'
import GaiaStatus from './GaiaStatus'
import TransportControls from './TransportControls'
import Viewer, { type Marker, type Zoom } from './Viewer'

interface Props {
  isCompact?: boolean
}

function gaiaMarker(m: GaiaMarker, variant: Marker['variant'], when: string): Marker {
  const id = `${variant}-${m.star.source_id}`
  return { id, px: m.px, variant, title: `Gaia DR3 ${m.star.source_id}: catalog position ${when}` }
}

export default function Player({ isCompact = false }: Props) {
  const { sequence, frames, playlist, frameIndex, setFrameIndex, currentFrame, frameA, frameB, params } =
    useAppState()
  const [isPlaying, setIsPlaying] = useState(() => !prefersReducedMotion())
  const [isAbBlink, setIsAbBlink] = useState(false)
  const [isLooping, setIsLooping] = useState(true)
  const [zoom, setZoom] = useState<Zoom>('fit')
  const [showMarkers, setShowMarkers] = useState(true)
  const [range, setRange] = useState<Range | null>(null)
  const [diffRange, setDiffRange] = useState<number | null>(null)
  const gaia = useGaiaOverlay()

  const list = playlist.frames
  const n = list.length
  const isDiff = params.view === 'diff'
  const indexA = frameA ? list.indexOf(frameA) : 0
  const indexB = frameB ? list.indexOf(frameB) : n - 1

  usePlayback(isPlaying && !isDiff && n > 1, params.fps, () => {
    if (isAbBlink) setFrameIndex(frameIndex === indexA ? indexB : indexA)
    else if (frameIndex + 1 < n) setFrameIndex(frameIndex + 1)
    else if (isLooping) setFrameIndex(0)
    else setIsPlaying(false)
  })

  const step = (delta: number) => {
    if (isDiff || n === 0) return
    setIsPlaying(false)
    setIsAbBlink(false)
    setFrameIndex((i) => (i + delta + n) % n)
  }
  const togglePlay = () => {
    if (!isDiff && n > 1) setIsPlaying((p) => !p)
  }
  const toggleAb = () => {
    if (isDiff || n < 2) return
    if (!isAbBlink) {
      setFrameIndex(indexA)
      setIsPlaying(true)
    }
    setIsAbBlink((v) => !v)
  }
  usePlayerKeys({ onTogglePlay: togglePlay, onStep: step, onToggleAb: toggleAb })

  const bounds = useMemo<Range | null>(() => {
    if (!sequence) return null
    const [lo = 0, hi = 1] = finitePercentiles(frames.map((f) => f.data), [0.5, 99.9]) ?? []
    return { vmin: Math.min(lo, sequence.stretch.vmin), vmax: Math.max(hi, sequence.stretch.vmax) }
  }, [sequence, frames])

  const overlays = useMemo(
    () => (sequence ? overlayLayers(sequence.flag_bits, params.flags) : []),
    [sequence, params.flags],
  )

  const diff = useMemo(() => (isDiff && frameA && frameB ? diffFrames(frameA, frameB) : null), [isDiff, frameA, frameB])

  const intensityStretch = useMemo<Stretch | null>(
    () =>
      sequence && {
        ...sequence.stretch,
        kind: params.stretch,
        vmin: range?.vmin ?? sequence.stretch.vmin,
        vmax: range?.vmax ?? sequence.stretch.vmax,
      },
    [sequence, params.stretch, range],
  )

  if (!sequence || !currentFrame || !bounds || !intensityStretch) return null

  const diffAuto = diff?.ok ? diff.diff.autoRange : 1
  const diffHalf = diffRange ?? diffAuto
  const diffStretch: Stretch = { kind: 'linear', vmin: -diffHalf, vmax: diffHalf, a: 1 }

  const markers: Marker[] = []
  if (gaia.status === 'ready') {
    const at = (mjd: number) => gaiaMarkers(gaia.field, sequence.grid, mjd, gaia.spanYears)
    if (isDiff && diff?.ok) {
      const { earlier, later } = diff.diff
      const moved = at(earlier.frame.mjd_mid).filter((m) => m.isMover)
      markers.push(...moved.map((m) => gaiaMarker(m, 'gaia-earlier', `on ${earlier.frame.label}`)))
      markers.push(
        ...at(later.frame.mjd_mid).map((m) =>
          gaiaMarker(m, m.isMover ? 'gaia-mover' : 'gaia', `on ${later.frame.label}`),
        ),
      )
    } else {
      const when = `on ${currentFrame.frame.label}`
      markers.push(
        ...at(currentFrame.frame.mjd_mid).map((m) => gaiaMarker(m, m.isMover ? 'gaia-mover' : 'gaia', when)),
      )
    }
  }
  if (showMarkers) {
    const title = 'Expected position from catalog proper motion (not a detection)'
    if (isDiff && diff?.ok) {
      const { earlier, later } = diff.diff
      if (earlier.frame.expected_px) markers.push({ id: 'e', px: earlier.frame.expected_px, variant: 'earlier', title: `${title}, ${earlier.frame.label}` })
      if (later.frame.expected_px) markers.push({ id: 'l', px: later.frame.expected_px, variant: 'later', title: `${title}, ${later.frame.label}` })
    } else if (currentFrame.frame.expected_px) {
      markers.push({ id: 'x', px: currentFrame.frame.expected_px, variant: 'expected', title })
    }
  }

  const name = sequence.meta.target_name ?? 'Field'
  const { frame } = currentFrame
  const missing = missingDetectors(frame.detectors, playlist.key)
  const abTag = frame.id === frameA?.frame.id ? ' · A' : frame.id === frameB?.frame.id ? ' · B' : ''

  return (
    <div className="player">
      {!playlist.isRequested && (
        <p className="warn">
          This sequence has no frames for the chosen detectors; showing {detectorLabel(playlist.key)} instead.
        </p>
      )}
      {isDiff && diff && !diff.ok && <p className="error">{diff.error}</p>}
      {isDiff && diff?.ok ? (
        <Viewer
          image={diff.diff}
          stretch={diffStretch}
          colormap={BLUE_ORANGE}
          overlays={overlays}
          zoom={zoom}
          markers={markers}
          ariaLabel={`${name}: difference ${diff.diff.later.frame.label} minus ${diff.diff.earlier.frame.label}`}
        />
      ) : (
        <Viewer
          image={{ data: currentFrame.data, flags: currentFrame.flags, shape: frame.shape }}
          stretch={intensityStretch}
          colormap={GREY}
          overlays={overlays}
          zoom={zoom}
          markers={markers}
          ariaLabel={`${name}: ${frame.label}, ${frame.date_range.join(' to ')} UTC`}
        />
      )}
      {!isDiff && (
        <p className="frame-caption" aria-live={isPlaying ? 'off' : 'polite'}>
          <strong>{frame.label}</strong>
          {abTag} · {frame.date_range.join(' … ')} UTC · {detectorLabel(detectorKey(frame.detectors))}
          {missing.length > 0 && (
            <span className="warn"> · no {missing.map((d) => `D${d}`).join(', ')} in this visit</span>
          )}
        </p>
      )}
      {isDiff && diff?.ok && <DiffLegend diff={diff.diff} range={diffHalf} />}
      <GaiaStatus load={gaia} />
      <TransportControls
        isPlaying={isPlaying && !isDiff}
        isAbBlink={isAbBlink}
        isLooping={isLooping}
        isDiff={isDiff}
        onTogglePlay={togglePlay}
        onStep={step}
        onToggleAb={toggleAb}
        onLoopChange={setIsLooping}
        onSeek={(i) => {
          setIsPlaying(false)
          setFrameIndex(i)
        }}
      />
      {!isCompact && (
        <DisplayControls
          zoom={zoom}
          onZoomChange={setZoom}
          showMarkers={showMarkers}
          onShowMarkersChange={setShowMarkers}
          range={{ vmin: intensityStretch.vmin, vmax: intensityStretch.vmax }}
          bounds={bounds}
          onRangeChange={setRange}
          diffRange={diffRange}
          diffBound={diffAuto * 4}
          onDiffRangeChange={setDiffRange}
        />
      )}
      {!isCompact && (
        <p className="muted shortcuts">
          Keys: Space play/pause · ←/→ step · B A/B blink. Speed is capped at 3 frames/s (flashing-content safety).
        </p>
      )}
    </div>
  )
}

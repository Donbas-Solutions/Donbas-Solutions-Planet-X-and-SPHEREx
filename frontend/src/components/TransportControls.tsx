import { useAppState } from '../hooks/useAppState'
import { FPS_MAX, FPS_MIN } from '../lib/urlState'

interface Props {
  isPlaying: boolean
  isAbBlink: boolean
  isLooping: boolean
  isDiff: boolean
  onTogglePlay: () => void
  onStep: (delta: number) => void
  onToggleAb: () => void
  onLoopChange: (loop: boolean) => void
  onSeek: (index: number) => void
}

export default function TransportControls({
  isPlaying,
  isAbBlink,
  isLooping,
  isDiff,
  onTogglePlay,
  onStep,
  onToggleAb,
  onLoopChange,
  onSeek,
}: Props) {
  const { playlist, frameIndex, frameA, frameB, params, setParams } = useAppState()
  const frames = playlist.frames
  const n = frames.length
  const current = frames[frameIndex]

  const frameOptions = frames.map((f) => (
    <option key={f.frame.id} value={f.frame.id}>
      {f.frame.label}
    </option>
  ))

  return (
    <section className="transport" aria-label="Player">
      {!isDiff && (
        <div className="transport-row">
          <button type="button" onClick={() => onStep(-1)} aria-label="Previous frame" disabled={n < 2}>
            ◀
          </button>
          <button type="button" onClick={onTogglePlay} disabled={n < 2} className="play">
            {isPlaying ? '⏸ Pause' : '▶ Play'}
          </button>
          <button type="button" onClick={() => onStep(1)} aria-label="Next frame" disabled={n < 2}>
            ▶
          </button>
          <label className="grow">
            <span className="visually-hidden">Frame</span>
            <input
              type="range"
              min={0}
              max={Math.max(n - 1, 0)}
              step={1}
              value={frameIndex}
              onChange={(e) => onSeek(Number(e.target.value))}
              aria-valuetext={current ? `${current.frame.label}, frame ${frameIndex + 1} of ${n}` : undefined}
            />
          </label>
          <span className="muted frame-count">
            {frameIndex + 1} / {n}
          </span>
        </div>
      )}
      <div className="transport-row">
        {!isDiff && (
          <>
            <button type="button" aria-pressed={isAbBlink} onClick={onToggleAb} disabled={n < 2}>
              A/B blink
            </button>
            <label>
              <input type="checkbox" checked={isLooping} onChange={(e) => onLoopChange(e.target.checked)} /> Loop
            </label>
            <label>
              Speed
              <input
                type="range"
                min={FPS_MIN}
                max={FPS_MAX}
                step={0.5}
                value={params.fps}
                onChange={(e) => setParams({ fps: Number(e.target.value) })}
              />
              <span className="muted">{params.fps} fps</span>
            </label>
          </>
        )}
        <label>
          A
          <select value={frameA?.frame.id ?? ''} onChange={(e) => setParams({ a: e.target.value })}>
            {frameOptions}
          </select>
        </label>
        <label>
          B
          <select value={frameB?.frame.id ?? ''} onChange={(e) => setParams({ b: e.target.value })}>
            {frameOptions}
          </select>
        </label>
      </div>
    </section>
  )
}

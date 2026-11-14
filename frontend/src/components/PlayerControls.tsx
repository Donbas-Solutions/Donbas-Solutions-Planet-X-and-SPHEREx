import { useAppState } from '../hooks/useAppState'

export default function PlayerControls() {
  const { frames, frameIndex, setFrameIndex } = useAppState()
  const n = frames.length
  if (n === 0) return null

  const step = (d: number) => setFrameIndex((i) => (i + d + n) % n)

  return (
    <section className="controls" aria-label="Player">
      <button type="button" onClick={() => step(-1)} aria-label="Previous frame">
        ◀
      </button>
      <label>
        <span className="visually-hidden">Frame</span>
        <select value={frameIndex} onChange={(e) => setFrameIndex(Number(e.target.value))}>
          {frames.map((f, i) => (
            <option key={f.frame.id} value={i}>
              {f.frame.label}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={() => step(1)} aria-label="Next frame">
        ▶
      </button>
      <span className="muted" aria-live="polite">
        {frameIndex + 1} / {n}
      </span>
    </section>
  )
}

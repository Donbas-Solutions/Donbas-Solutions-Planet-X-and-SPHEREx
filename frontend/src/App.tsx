// Phase 0 skeleton: proves manifest → Float32 frames → canvas works end to end.
// Track B replaces this with the real player (see docs/agent-prompt.md).
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { Sequence } from './api/types'
import { flagMask, loadFrame, loadSequence, renderFrame, type LoadedFrame } from './lib/frames'

const AladinPanel = lazy(() => import('./components/AladinPanel'))

const ZOOM = 5
const DEFAULT_MANIFEST = '/mock/sequence.json'

export default function App() {
  const manifestUrl = new URLSearchParams(window.location.search).get('manifest') ?? DEFAULT_MANIFEST
  const [seq, setSeq] = useState<Sequence | null>(null)
  const [frames, setFrames] = useState<LoadedFrame[]>([])
  const [index, setIndex] = useState(0)
  const [showFlags, setShowFlags] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    let cancelled = false
    loadSequence(manifestUrl)
      .then(async ({ seq, base }) => {
        const loaded = await Promise.all(seq.frames.map((f) => loadFrame(f, base)))
        if (!cancelled) {
          setSeq(seq)
          setFrames(loaded)
        }
      })
      .catch((e: unknown) => !cancelled && setError(String(e)))
    return () => {
      cancelled = true
    }
  }, [manifestUrl])

  const overlayMask = useMemo(() => (seq ? flagMask(seq.flag_bits, ['bad', 'saturation']) : 0), [seq])
  const current = frames[index]

  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d')
    if (!ctx || !seq || !current) return
    renderFrame(ctx, current, seq.stretch, { overlayMask: showFlags ? overlayMask : 0 })
  }, [seq, current, showFlags, overlayMask])

  if (error) return <main className="app"><p className="error">{error}</p></main>
  if (!seq || !current) return <main className="app"><p>Loading {manifestUrl}…</p></main>

  const [ny, nx] = current.frame.shape
  const exp = current.frame.expected_px
  const step = (d: number) => setIndex((i) => (i + d + frames.length) % frames.length)

  return (
    <main className="app">
      <header>
        <h1>SPHEREx Blink</h1>
        <span className="muted">
          {seq.meta.target_name ?? `${seq.grid.ra.toFixed(4)}, ${seq.grid.dec.toFixed(4)}`}
          {seq.meta.mock && <span className="badge">mock data</span>}
        </span>
      </header>

      <section className="controls">
        <button onClick={() => step(-1)}>◀ Prev</button>
        <select value={index} onChange={(e) => setIndex(Number(e.target.value))}>
          {frames.map((f, i) => (
            <option key={f.frame.id} value={i}>{f.frame.label}</option>
          ))}
        </select>
        <button onClick={() => step(1)}>Next ▶</button>
        <label>
          <input type="checkbox" checked={showFlags} onChange={(e) => setShowFlags(e.target.checked)} /> Flags overlay
        </label>
      </section>

      <div className="viewer" style={{ width: nx * ZOOM, height: ny * ZOOM }}>
        <canvas ref={canvasRef} width={nx} height={ny} style={{ width: nx * ZOOM, height: ny * ZOOM }} />
        {exp && (
          <div
            className="marker"
            title="Expected position (proper motion)"
            style={{ left: (exp.x + 0.5) * ZOOM, top: (ny - 1 - exp.y + 0.5) * ZOOM }}
          />
        )}
      </div>

      <dl className="meta">
        <dt>Dates</dt><dd>{current.frame.date_range.join(' … ')}</dd>
        <dt>Detectors</dt><dd>{current.frame.detectors.map((d) => `D${d}`).join(', ')}</dd>
        <dt>λ</dt><dd>{current.frame.lambda_um.join('–')} µm</dd>
        <dt>Exposures</dt><dd>{current.frame.n_exposures}</dd>
        {current.frame.warnings.length > 0 && (<><dt>Warnings</dt><dd className="warn">{current.frame.warnings.join('; ')}</dd></>)}
      </dl>

      <Suspense fallback={<p className="muted">Loading Aladin…</p>}>
        <AladinPanel ra={seq.grid.ra} dec={seq.grid.dec} fovDeg={(seq.grid.fov_arcmin / 60) * 3} />
      </Suspense>
    </main>
  )
}

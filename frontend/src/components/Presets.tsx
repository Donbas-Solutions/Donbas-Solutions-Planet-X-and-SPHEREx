import { useAppState } from '../hooks/useAppState'
import { PRESETS } from '../lib/presets'

export default function Presets() {
  const { params, setParams } = useAppState()
  return (
    <nav className="presets" aria-label="Test targets">
      <span className="muted">Test targets:</span>
      {PRESETS.map((p) => (
        <button
          key={p.id}
          type="button"
          aria-pressed={params.target === p.id}
          title={p.test === 'motion' ? 'Proper-motion test' : 'Brightness-variability test'}
          onClick={() =>
            setParams(
              { target: p.id, name: null, ra: null, dec: null, pm: null, manifest: null, a: null, b: null },
              'push',
            )
          }
        >
          {p.name}
        </button>
      ))}
    </nav>
  )
}

import { useAppState } from '../../hooks/useAppState'
import { useSpectrum } from '../../hooks/useSpectrum'
import { positionCaveat } from '../../lib/spectrum'
import { sourceKey } from '../../lib/urlState'
import LightCurveChart from './LightCurveChart'
import './charts.css'

export default function LightCurvePanel() {
  const { params, source, target, sequence, selectedPixel } = useAppState()
  const load = useSpectrum()

  switch (load.status) {
    case 'idle':
      return <p className="muted">The light curve appears once a sequence is loaded.</p>
    case 'loading':
      return (
        <p className="muted" aria-live="polite">
          Loading the photometry…
        </p>
      )
    case 'unavailable':
      return <p className="muted">{load.message}</p>
    case 'ready':
      break
  }

  const name = target?.name ?? sequence?.meta.target_name ?? 'the target'
  const caveat = positionCaveat(params.target, target)

  return (
    <div className="chart-panel">
      <p className="muted">
        Flux of {name} over time, per detector. Within one detector each exposure samples a different wavelength of the
        band, so part of the scatter between exposures is the spectrum, not variability: compare visits by their means.
        {selectedPixel && load.origin === 'bundle' && ' Light curves of other clicked sources need the live server.'}
      </p>
      {load.notice && <p className="warn">{load.notice}</p>}
      {caveat && <p className="warn">{caveat}</p>}
      <LightCurveChart key={sourceKey(source)} spectrum={load.spectrum} targetName={name} />
    </div>
  )
}

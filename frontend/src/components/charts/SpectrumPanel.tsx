import { useAppState } from '../../hooks/useAppState'
import { useSpectrum } from '../../hooks/useSpectrum'
import { SPECTRUM_CAVEATS } from '../../lib/spectrum'
import { sourceKey } from '../../lib/urlState'
import SpectrumChart from './SpectrumChart'
import './charts.css'

export default function SpectrumPanel() {
  const { params, source, target, selectedPixel } = useAppState()
  const load = useSpectrum()

  switch (load.status) {
    case 'idle':
      return <p className="muted">The spectrum appears once a sequence is loaded.</p>
    case 'loading':
      return (
        <p className="muted" aria-live="polite">
          Loading the spectrum…
        </p>
      )
    case 'unavailable':
      return <p className="muted">{load.message}</p>
    case 'ready':
      break
  }

  const name = target?.name ?? 'the target'
  const caveat = params.target ? SPECTRUM_CAVEATS[params.target] : undefined

  return (
    <div className="chart-panel">
      <p className="muted">
        Forced photometry of {name} at its proper-motion-propagated position, one point per exposure. SPHEREx sees a
        different wavelength at each place on a detector, so every exposure samples its own λ.
        {selectedPixel && load.origin === 'bundle' && ' Spectra of other clicked sources need the live server.'}
      </p>
      {load.notice && <p className="warn">{load.notice}</p>}
      {caveat && <p className="warn">{caveat}</p>}
      <SpectrumChart key={sourceKey(source)} spectrum={load.spectrum} targetName={name} />
    </div>
  )
}

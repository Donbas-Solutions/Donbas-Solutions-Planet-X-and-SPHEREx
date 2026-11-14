import type { Frame } from '../api/types'
import Term from './Term'

interface Props {
  frame: Frame
  title: string
}

export default function FrameMeta({ frame, title }: Props) {
  return (
    <div className="frame-meta">
      <h3>
        {title}: {frame.label}
      </h3>
      <dl className="meta">
        <dt>
          <Term id="visit">Visit</Term> dates (UTC)
        </dt>
        <dd>{frame.date_range.join(' … ')}</dd>
        <dt>MJD (mid)</dt>
        <dd>{frame.mjd_mid.toFixed(2)}</dd>
        <dt>
          <Term id="detector">Detectors</Term>
        </dt>
        <dd>{frame.detectors.map((d) => `D${d}`).join(', ')}</dd>
        <dt>λ</dt>
        <dd>
          {frame.lambda_um[0].toFixed(2)}–{frame.lambda_um[1].toFixed(2)} µm
        </dd>
        <dt>Exposures</dt>
        <dd>{frame.n_exposures}</dd>
      </dl>
      {frame.warnings.length > 0 && (
        <ul className="warnings" aria-label={`Warnings for ${frame.label}`}>
          {frame.warnings.map((w) => (
            <li key={`${w.code}:${w.message}`} className="warn">
              ⚠ {w.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

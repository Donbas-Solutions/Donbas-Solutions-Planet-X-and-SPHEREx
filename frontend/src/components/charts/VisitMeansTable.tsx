import type { VisitMean } from '../../lib/lightcurve'

interface Props {
  means: readonly VisitMean[]
}

function note(m: VisitMean): string {
  if (m.fluxUjy === null) return m.nSaturated > 0 ? 'saturated' : 'masked by flags'
  const notes = [
    m.isLambdaComplete ? '' : 'incomplete λ',
    m.nSaturated > 0 ? `${m.nSaturated} saturated excluded` : '',
    m.nMeasured === 1 ? 'one exposure: formal error only' : '',
  ]
  return notes.filter(Boolean).join('; ')
}

export default function VisitMeansTable({ means }: Props) {
  return (
    <details>
      <summary>Visit means per detector ({means.length})</summary>
      <div className="chart-table">
        <table>
          <thead>
            <tr>
              <th scope="col">Detector</th>
              <th scope="col">Visit</th>
              <th scope="col">λ (µm)</th>
              <th scope="col">Mean flux (µJy)</th>
              <th scope="col">1σ (µJy)</th>
              <th scope="col">Measured / all</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {means.map((m) => (
              <tr key={`${m.detector}:${m.visit.id}`}>
                <td>D{m.detector}</td>
                <td>{m.visit.label}</td>
                <td>
                  {m.lambdaMin.toFixed(2)}–{m.lambdaMax.toFixed(2)}
                </td>
                <td>{m.fluxUjy !== null ? m.fluxUjy.toFixed(1) : '—'}</td>
                <td>{m.errUjy !== null ? m.errUjy.toFixed(1) : '—'}</td>
                <td>
                  {m.nMeasured} / {m.nMeasured + m.nSaturated + m.nFlagged}
                </td>
                <td>{note(m)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

import { useMemo } from 'react'
import type { SpectrumPoint } from '../../api/types'
import { mjdToIsoDate, pointStatus, type VisitInfo } from '../../lib/spectrum'

interface Props {
  points: readonly SpectrumPoint[]
  visitById: ReadonlyMap<string, VisitInfo>
}

const STATUS_TEXT = { measured: '', saturated: 'saturated', flagged: 'masked by flags' } as const

export default function SpectrumTable({ points, visitById }: Props) {
  const rows = useMemo(() => [...points].sort((a, b) => a.lambda_um - b.lambda_um), [points])
  return (
    <details>
      <summary>Data table ({points.length} exposures)</summary>
      <div className="chart-table">
        <table>
          <thead>
            <tr>
              <th scope="col">λ (µm)</th>
              <th scope="col">Flux (µJy)</th>
              <th scope="col">1σ (µJy)</th>
              <th scope="col">Date (UTC)</th>
              <th scope="col">Detector</th>
              <th scope="col">Visit</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => {
              const status = pointStatus(p)
              const isMeasured = status === 'measured'
              return (
                <tr key={`${p.visit}:${p.detector}:${p.mjd}:${i}`}>
                  <td>{p.lambda_um.toFixed(4)}</td>
                  <td>{isMeasured ? p.flux_ujy?.toFixed(1) : '—'}</td>
                  <td>{isMeasured ? (p.err_ujy?.toFixed(1) ?? '—') : '—'}</td>
                  <td>{mjdToIsoDate(p.mjd)}</td>
                  <td>D{p.detector}</td>
                  <td>{visitById.get(p.visit)?.label ?? p.visit}</td>
                  <td>{STATUS_TEXT[status]}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </details>
  )
}

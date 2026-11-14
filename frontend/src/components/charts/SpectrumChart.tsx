import { useMemo, useState } from 'react'
import type { Spectrum, SpectrumPoint } from '../../api/types'
import { extent, pad, type ScaleKind } from '../../lib/chart'
import {
  defaultVisitSlots,
  detectorBands,
  MAX_VISIT_SERIES,
  mjdToIsoDate,
  pointStatus,
  prefersLogScale,
  toggleSlot,
  visitsOf,
  type VisitInfo,
} from '../../lib/spectrum'
import PointChart, { type ChartPoint } from './PointChart'
import SpectrumTable from './SpectrumTable'
import StatusLegend from './StatusLegend'

interface Props {
  spectrum: Spectrum
  targetName: string
}

function fluxText(p: SpectrumPoint): string {
  switch (pointStatus(p)) {
    case 'saturated':
      return 'saturated — no value'
    case 'flagged':
      return 'masked by flags — no value'
    case 'measured':
      return `${p.flux_ujy?.toFixed(1)}${p.err_ujy !== null ? ` ± ${p.err_ujy.toFixed(1)}` : ''} µJy`
  }
}

function toChartPoint(p: SpectrumPoint, i: number, slot: number, visit: VisitInfo | undefined): ChartPoint {
  return {
    key: `${p.visit}:${p.detector}:${p.mjd}:${i}`,
    x: p.lambda_um,
    y: pointStatus(p) === 'measured' ? p.flux_ujy : null,
    err: p.err_ujy,
    status: pointStatus(p),
    slot,
    tooltip: [
      `λ ${p.lambda_um.toFixed(3)} µm`,
      fluxText(p),
      `${mjdToIsoDate(p.mjd)} UTC · D${p.detector}`,
      `visit ${visit?.label ?? p.visit} (${p.visit})`,
    ],
  }
}

export default function SpectrumChart({ spectrum, targetName }: Props) {
  const { points } = spectrum
  const visits = useMemo(() => visitsOf(points), [points])
  const [slots, setSlots] = useState(() => defaultVisitSlots(visits))
  const [yScale, setYScale] = useState<ScaleKind>(() => (prefersLogScale(points) ? 'log' : 'linear'))

  const xDomain = useMemo(() => pad(extent(points.map((p) => p.lambda_um)) ?? [0.75, 5], 0.02), [points])
  const bands = useMemo(
    () => detectorBands(points).map((b) => ({ from: b.lambdaMin, to: b.lambdaMax, label: `D${b.detector}` })),
    [points],
  )
  const visitById = useMemo(() => new Map(visits.map((v) => [v.id, v])), [visits])

  const shown = useMemo(
    () =>
      points.flatMap((p, i) => {
        const slot = slots.indexOf(p.visit)
        return slot < 0 ? [] : [toChartPoint(p, i, slot, visitById.get(p.visit))]
      }),
    [points, slots, visitById],
  )

  const counts = {
    measured: shown.filter((p) => p.status === 'measured').length,
    saturated: shown.filter((p) => p.status === 'saturated').length,
    flagged: shown.filter((p) => p.status === 'flagged').length,
    nonpositive: yScale === 'log' ? shown.filter((p) => p.y !== null && p.y <= 0).length : 0,
  }
  const allSaturated = points.length > 0 && points.every((p) => pointStatus(p) === 'saturated' || p.flux_ujy === null)
  const isFull = !slots.includes(null)

  return (
    <>
      <div className="chart-toolbar">
        <fieldset>
          <legend>Visits</legend>
          {visits.map((v) => {
            const slot = slots.indexOf(v.id)
            const isOn = slot >= 0
            return (
              <label key={v.id}>
                <input
                  type="checkbox"
                  checked={isOn}
                  disabled={!isOn && isFull}
                  onChange={() => setSlots((s) => toggleSlot(s, v.id))}
                />
                <span className={isOn ? `swatch series-${slot + 1}` : 'swatch'} aria-hidden="true" />
                {v.label} <span className="muted">({v.count})</span>
              </label>
            )
          })}
        </fieldset>
        <fieldset>
          <legend>Flux axis</legend>
          {(['linear', 'log'] as const).map((k) => (
            <label key={k}>
              <input type="radio" name="spectrum-scale" checked={yScale === k} onChange={() => setYScale(k)} />
              {k}
            </label>
          ))}
        </fieldset>
      </div>
      {visits.length > MAX_VISIT_SERIES && (
        <p className="muted">Up to {MAX_VISIT_SERIES} visits at a time, so the colours stay distinguishable.</p>
      )}
      {allSaturated && (
        <p className="warn">
          No flux can be measured for this source: every exposure is saturated or masked. Saturated points are shown
          without values.
        </p>
      )}

      <PointChart
        points={shown}
        xDomain={xDomain}
        xLabel="Wavelength at the source (µm)"
        yLabel="Flux density (µJy)"
        yScale={yScale}
        bands={bands}
        ariaLabel={`Spectrum of ${targetName}: ${counts.measured} measured points, ${counts.saturated} saturated, ${counts.flagged} masked by flags. The data table below lists every point.`}
      />
      <StatusLegend {...counts} />
      <SpectrumTable points={points} visitById={visitById} />
    </>
  )
}

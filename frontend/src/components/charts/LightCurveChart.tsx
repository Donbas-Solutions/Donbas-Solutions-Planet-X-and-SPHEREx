import { useMemo, useState } from 'react'
import type { Spectrum, SpectrumPoint } from '../../api/types'
import { extent, pad, type ScaleKind } from '../../lib/chart'
import { amplitudes, detectorId, detectorsByMeasured, visitMeans, type VisitMean } from '../../lib/lightcurve'
import {
  detectorBands,
  MAX_VISIT_SERIES,
  mjdToIsoDate,
  pointStatus,
  prefersLogScale,
  slotsFor,
  toggleSlot,
  visitsOf,
} from '../../lib/spectrum'
import PointChart, { type ChartPoint } from './PointChart'
import StatusLegend from './StatusLegend'
import VisitMeansTable from './VisitMeansTable'

interface Props {
  spectrum: Spectrum
  targetName: string
}

type Mode = 'exposures' | 'visits'

/** Visit labels collide when there are many bins (deep fields); the shading alone still shows them. */
const MAX_BAND_LABELS = 6

function exposurePoint(p: SpectrumPoint, i: number, slot: number): ChartPoint {
  const status = pointStatus(p)
  const flux =
    status === 'measured'
      ? `${p.flux_ujy?.toFixed(1)}${p.err_ujy !== null ? ` ± ${p.err_ujy.toFixed(1)}` : ''} µJy`
      : status === 'saturated'
        ? 'saturated — no value'
        : 'masked by flags — no value'
  return {
    key: `${p.visit}:${p.detector}:${p.mjd}:${i}`,
    x: p.mjd,
    y: status === 'measured' ? p.flux_ujy : null,
    err: p.err_ujy,
    status,
    slot,
    tooltip: [`${mjdToIsoDate(p.mjd)} UTC · D${p.detector}`, flux, `λ ${p.lambda_um.toFixed(3)} µm`],
  }
}

function meanPoint(m: VisitMean, slot: number): ChartPoint {
  const n = m.nMeasured + m.nSaturated + m.nFlagged
  const flux =
    m.fluxUjy !== null
      ? `${m.fluxUjy.toFixed(1)} ± ${m.errUjy?.toFixed(1)} µJy (mean of ${m.nMeasured} of ${n})`
      : m.nSaturated > 0
        ? `saturated in ${m.nSaturated} of ${n} exposures — no value`
        : `all ${n} exposures masked — no value`
  return {
    key: `${m.detector}:${m.visit.id}`,
    x: m.mjdMid,
    y: m.fluxUjy,
    err: m.errUjy,
    status: m.fluxUjy !== null ? 'measured' : m.nSaturated > 0 ? 'saturated' : 'flagged',
    slot,
    tooltip: [
      `D${m.detector} · visit ${m.visit.label}`,
      flux,
      `λ ${m.lambdaMin.toFixed(2)}–${m.lambdaMax.toFixed(2)} µm`,
    ],
  }
}

export default function LightCurveChart({ spectrum, targetName }: Props) {
  const { points } = spectrum
  const visits = useMemo(() => visitsOf(points), [points])
  const means = useMemo(() => visitMeans(points, visits), [points, visits])
  const amps = useMemo(() => amplitudes(means), [means])
  const bandsByDetector = useMemo(() => new Map(detectorBands(points).map((b) => [b.detector, b])), [points])
  const detectorIds = useMemo(() => detectorsByMeasured(points), [points])
  const sortedDetectorIds = useMemo(() => [...detectorIds].sort((a, b) => a.localeCompare(b)), [detectorIds])

  const [slots, setSlots] = useState(() => slotsFor(detectorIds))
  const [mode, setMode] = useState<Mode>('exposures')
  const [yScale, setYScale] = useState<ScaleKind>(() => (prefersLogScale(points) ? 'log' : 'linear'))

  const xDomain = useMemo(() => pad(extent(points.map((p) => p.mjd)) ?? [0, 1], 0.03), [points])
  const bands = useMemo(() => {
    const showLabels = visits.length <= MAX_BAND_LABELS
    return visits.map((v) => {
      const span = extent(points.filter((p) => p.visit === v.id).map((p) => p.mjd)) ?? [v.mjdStart, v.mjdStart]
      return { from: span[0], to: span[1], label: showLabels ? v.label : '' }
    })
  }, [points, visits])

  const shown = useMemo(() => {
    if (mode === 'visits') {
      return means.flatMap((m) => {
        const slot = slots.indexOf(detectorId(m.detector))
        return slot < 0 ? [] : [meanPoint(m, slot)]
      })
    }
    return points.flatMap((p, i) => {
      const slot = slots.indexOf(detectorId(p.detector))
      return slot < 0 ? [] : [exposurePoint(p, i, slot)]
    })
  }, [mode, means, points, slots])

  const counts = {
    measured: shown.filter((p) => p.status === 'measured').length,
    saturated: shown.filter((p) => p.status === 'saturated').length,
    flagged: shown.filter((p) => p.status === 'flagged').length,
    nonpositive: yScale === 'log' ? shown.filter((p) => p.y !== null && p.y <= 0).length : 0,
  }
  const selectedDetectors = new Set(slots.flatMap((s) => (s ? [s] : [])))
  const shownAmps = amps.filter((a) => selectedDetectors.has(detectorId(a.detector)))
  const isFull = !slots.includes(null)
  const noneMeasured = points.every((p) => pointStatus(p) !== 'measured')

  return (
    <>
      <div className="chart-toolbar">
        <fieldset>
          <legend>Detectors</legend>
          {sortedDetectorIds.map((id) => {
            const slot = slots.indexOf(id)
            const isOn = slot >= 0
            const band = bandsByDetector.get(Number(id.slice(1)))
            return (
              <label key={id}>
                <input
                  type="checkbox"
                  checked={isOn}
                  disabled={!isOn && isFull}
                  onChange={() => setSlots((s) => toggleSlot(s, id))}
                />
                <span className={isOn ? `swatch series-${slot + 1}` : 'swatch'} aria-hidden="true" />
                {id}
                {band && (
                  <span className="muted">
                    {' '}
                    {band.lambdaMin.toFixed(2)}–{band.lambdaMax.toFixed(2)} µm
                  </span>
                )}
              </label>
            )
          })}
        </fieldset>
        <fieldset>
          <legend>Points</legend>
          <label>
            <input type="radio" name="lightcurve-mode" checked={mode === 'exposures'} onChange={() => setMode('exposures')} />
            each exposure
          </label>
          <label>
            <input type="radio" name="lightcurve-mode" checked={mode === 'visits'} onChange={() => setMode('visits')} />
            visit means
          </label>
        </fieldset>
        <fieldset>
          <legend>Flux axis</legend>
          {(['linear', 'log'] as const).map((k) => (
            <label key={k}>
              <input type="radio" name="lightcurve-scale" checked={yScale === k} onChange={() => setYScale(k)} />
              {k}
            </label>
          ))}
        </fieldset>
      </div>
      {detectorIds.length > MAX_VISIT_SERIES && (
        <p className="muted">Up to {MAX_VISIT_SERIES} detectors at a time, so the colours stay distinguishable.</p>
      )}
      {noneMeasured && (
        <p className="warn">
          No flux can be measured for this source: every exposure is saturated or masked, so there is no light curve to
          draw. The points below only show when SPHEREx looked.
        </p>
      )}

      <PointChart
        points={shown}
        xDomain={xDomain}
        xLabel="Date (UTC)"
        yLabel="Flux density (µJy)"
        yScale={yScale}
        bands={bands}
        formatX={mjdToIsoDate}
        ariaLabel={`Light curve of ${targetName}: ${counts.measured} ${mode === 'visits' ? 'visit means' : 'measured exposures'}, ${counts.saturated} saturated, ${counts.flagged} masked. The table below lists the visit means.`}
      />
      <StatusLegend {...counts} measuredLabel={mode === 'visits' ? 'visit means, with 1σ errors' : undefined} />
      {shownAmps.length > 0 && (
        <ul className="chart-legend" aria-label="Variability amplitude">
          {shownAmps.map((a) => (
            <li key={a.detector}>
              D{a.detector}: brightest − faintest visit mean = {a.deltaUjy.toFixed(1)} ± {a.errUjy.toFixed(1)} µJy (
              {(a.deltaUjy / a.errUjy).toFixed(1)}σ, {a.nVisits} visits)
            </li>
          ))}
        </ul>
      )}
      <VisitMeansTable means={means} />
    </>
  )
}

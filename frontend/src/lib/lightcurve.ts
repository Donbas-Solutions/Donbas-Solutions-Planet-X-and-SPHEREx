import type { SpectrumPoint } from '../api/types'
import { pointStatus, type VisitInfo } from './spectrum'

export interface VisitMean {
  visit: VisitInfo
  detector: number
  mjdMid: number
  /** Inverse-variance weighted mean of the measured exposures; null when none has a value. */
  fluxUjy: number | null
  /** The larger of the formal error and the error from the exposures' spread. */
  errUjy: number | null
  nMeasured: number
  nSaturated: number
  nFlagged: number
  lambdaMin: number
  lambdaMax: number
}

export interface Amplitude {
  detector: number
  deltaUjy: number
  errUjy: number
  nVisits: number
}

export function detectorId(detector: number): string {
  return `D${detector}`
}

/** Detector ids, those with the most measured points first. */
export function detectorsByMeasured(points: readonly SpectrumPoint[]): string[] {
  const counts = new Map<number, number>()
  for (const p of points) {
    counts.set(p.detector, (counts.get(p.detector) ?? 0) + (pointStatus(p) === 'measured' ? 1 : 0))
  }
  return [...counts]
    .sort(([da, na], [db, nb]) => nb - na || da - db)
    .map(([d]) => detectorId(d))
}

/**
 * Standard error from the spread of the exposures. Within a visit each exposure sees a different λ of the band (LVF),
 * so the spread is often far larger than the formal photometric errors; the mean's error must not ignore it.
 */
function scatterError(fluxes: readonly number[]): number {
  const n = fluxes.length
  if (n < 2) return 0
  const mean = fluxes.reduce((s, f) => s + f, 0) / n
  const variance = fluxes.reduce((s, f) => s + (f - mean) ** 2, 0) / (n - 1)
  return Math.sqrt(variance / n)
}

export function visitMeans(points: readonly SpectrumPoint[], visits: readonly VisitInfo[]): VisitMean[] {
  const groups = new Map<string, SpectrumPoint[]>()
  for (const p of points) {
    const key = `${p.detector}|${p.visit}`
    const group = groups.get(key)
    if (group) group.push(p)
    else groups.set(key, [p])
  }
  const order = new Map(visits.map((v, i) => [v.id, i]))
  const means: VisitMean[] = []
  for (const group of groups.values()) {
    const first = group[0]
    const visit = first ? visits.find((v) => v.id === first.visit) : undefined
    if (!first || !visit) continue
    let sumW = 0
    let sumWF = 0
    const fluxes: number[] = []
    const counts = { measured: 0, saturated: 0, flagged: 0 }
    for (const p of group) {
      const status = pointStatus(p)
      counts[status]++
      if (status === 'measured' && p.flux_ujy !== null && p.err_ujy !== null && p.err_ujy > 0) {
        const w = 1 / p.err_ujy ** 2
        sumW += w
        sumWF += w * p.flux_ujy
        fluxes.push(p.flux_ujy)
      }
    }
    means.push({
      visit,
      detector: first.detector,
      mjdMid: group.reduce((s, p) => s + p.mjd, 0) / group.length,
      fluxUjy: sumW > 0 ? sumWF / sumW : null,
      errUjy: sumW > 0 ? Math.max(1 / Math.sqrt(sumW), scatterError(fluxes)) : null,
      nMeasured: counts.measured,
      nSaturated: counts.saturated,
      nFlagged: counts.flagged,
      lambdaMin: Math.min(...group.map((p) => p.lambda_um)),
      lambdaMax: Math.max(...group.map((p) => p.lambda_um)),
    })
  }
  return means.sort((a, b) => a.detector - b.detector || (order.get(a.visit.id) ?? 0) - (order.get(b.visit.id) ?? 0))
}

/** Brightest minus faintest visit mean per detector, with the error of that difference. */
export function amplitudes(means: readonly VisitMean[]): Amplitude[] {
  const byDetector = new Map<number, VisitMean[]>()
  for (const m of means) {
    if (m.fluxUjy === null || m.errUjy === null) continue
    byDetector.set(m.detector, [...(byDetector.get(m.detector) ?? []), m])
  }
  const result: Amplitude[] = []
  for (const [detector, list] of byDetector) {
    if (list.length < 2) continue
    const sorted = [...list].sort((a, b) => (a.fluxUjy ?? 0) - (b.fluxUjy ?? 0))
    const lo = sorted[0]
    const hi = sorted[sorted.length - 1]
    if (!lo || !hi || lo.fluxUjy === null || hi.fluxUjy === null) continue
    result.push({
      detector,
      deltaUjy: hi.fluxUjy - lo.fluxUjy,
      errUjy: Math.hypot(lo.errUjy ?? 0, hi.errUjy ?? 0),
      nVisits: list.length,
    })
  }
  return result.sort((a, b) => a.detector - b.detector)
}

import type { SpectrumPoint } from '../api/types'
import { chi2SurvivalP } from './chi2'
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
  /** λ range of the measured exposures (of all exposures when none is measured). */
  lambdaMin: number
  lambdaMax: number
  isLambdaComplete: boolean
}

export interface Variability {
  detector: number
  nVisits: number
  /** Measured visits left out for incomplete λ coverage. */
  nExcluded: number
  chi2: number
  dof: number
  /** Chance of a χ² this large from a constant source with these errors. */
  pValue: number
  /** Brightest minus faintest visit mean; grows with the number of visits even for a constant source. */
  rangeUjy: number
  rangeErrUjy: number
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
    const lambdas: number[] = []
    const counts = { measured: 0, saturated: 0, flagged: 0 }
    for (const p of group) {
      const status = pointStatus(p)
      counts[status]++
      if (status === 'measured' && p.flux_ujy !== null && p.err_ujy !== null && p.err_ujy > 0) {
        const w = 1 / p.err_ujy ** 2
        sumW += w
        sumWF += w * p.flux_ujy
        fluxes.push(p.flux_ujy)
        lambdas.push(p.lambda_um)
      }
    }
    const lambdaSource = lambdas.length > 0 ? lambdas : group.map((p) => p.lambda_um)
    means.push({
      visit,
      detector: first.detector,
      mjdMid: group.reduce((s, p) => s + p.mjd, 0) / group.length,
      fluxUjy: sumW > 0 ? sumWF / sumW : null,
      errUjy: sumW > 0 ? Math.max(1 / Math.sqrt(sumW), scatterError(fluxes)) : null,
      nMeasured: counts.measured,
      nSaturated: counts.saturated,
      nFlagged: counts.flagged,
      lambdaMin: Math.min(...lambdaSource),
      lambdaMax: Math.max(...lambdaSource),
      isLambdaComplete: true,
    })
  }
  markLambdaCoverage(means)
  return means.sort((a, b) => a.detector - b.detector || (order.get(a.visit.id) ?? 0) - (order.get(b.visit.id) ?? 0))
}

/**
 * SR-1: visit means are comparable only at similar λ. Per detector, the widest measured visit is the reference; a
 * visit is complete when its range overlaps at least 80 % of the reference (the backend's `incomplete_lambda` rule).
 */
function markLambdaCoverage(means: VisitMean[]): void {
  const byDetector = new Map<number, VisitMean[]>()
  for (const m of means) {
    if (m.fluxUjy !== null) byDetector.set(m.detector, [...(byDetector.get(m.detector) ?? []), m])
  }
  for (const list of byDetector.values()) {
    const ref = list.reduce((a, b) => (b.lambdaMax - b.lambdaMin > a.lambdaMax - a.lambdaMin ? b : a))
    const refSpan = ref.lambdaMax - ref.lambdaMin
    if (refSpan <= 0) continue
    for (const m of list) {
      const overlap = Math.min(m.lambdaMax, ref.lambdaMax) - Math.max(m.lambdaMin, ref.lambdaMin)
      m.isLambdaComplete = overlap >= MIN_LAMBDA_OVERLAP * refSpan
    }
  }
}

const MIN_LAMBDA_OVERLAP = 0.8

/**
 * χ² of the visit means against a constant (their weighted mean), over visits with complete λ coverage. Unlike
 * max − min, it does not grow with the number of visits under pure noise.
 */
export function variability(means: readonly VisitMean[]): Variability[] {
  const byDetector = new Map<number, VisitMean[]>()
  for (const m of means) {
    if (m.fluxUjy === null || m.errUjy === null || m.errUjy <= 0) continue
    byDetector.set(m.detector, [...(byDetector.get(m.detector) ?? []), m])
  }
  const result: Variability[] = []
  for (const [detector, all] of byDetector) {
    const list = all.filter((m) => m.isLambdaComplete)
    if (list.length < 2) continue
    const fluxes = list.map((m) => m.fluxUjy ?? 0)
    const errs = list.map((m) => m.errUjy ?? 1)
    const weights = errs.map((e) => 1 / e ** 2)
    const sumW = weights.reduce((s, w) => s + w, 0)
    const mean = fluxes.reduce((s, f, i) => s + f * (weights[i] ?? 0), 0) / sumW
    const chi2 = fluxes.reduce((s, f, i) => s + ((f - mean) / (errs[i] ?? 1)) ** 2, 0)
    const dof = list.length - 1
    const hi = list.reduce((a, b) => ((b.fluxUjy ?? 0) > (a.fluxUjy ?? 0) ? b : a))
    const lo = list.reduce((a, b) => ((b.fluxUjy ?? 0) < (a.fluxUjy ?? 0) ? b : a))
    result.push({
      detector,
      nVisits: list.length,
      nExcluded: all.length - list.length,
      chi2,
      dof,
      pValue: chi2SurvivalP(chi2, dof),
      rangeUjy: (hi.fluxUjy ?? 0) - (lo.fluxUjy ?? 0),
      rangeErrUjy: Math.hypot(hi.errUjy ?? 0, lo.errUjy ?? 0),
    })
  }
  return result.sort((a, b) => a.detector - b.detector)
}

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

/** LVF bands and channel count as in backend/app/pipeline/sequence.py; channels are equal steps in log λ. */
const DETECTOR_BANDS_UM: Readonly<Record<number, readonly [number, number]>> = {
  1: [0.75, 1.11],
  2: [1.11, 1.64],
  3: [1.64, 2.42],
  4: [2.42, 3.82],
  5: [3.82, 4.42],
  6: [4.42, 5.0],
}
const LVF_CHANNELS = 17
/** Per exposure, in quadrature: repeatability and aperture systematics the formal errors leave out. */
const CALIBRATION_FLOOR = 0.05
/** |d ln F / d ln λ| assumed for a point with no λ-neighbour in its own visit (a steep stellar continuum). */
const DEFAULT_LOG_SLOPE = 4
/** Matches backend/app/pipeline/variability.py; judge the strongest of several visit pairs against 5σ. */
export const MATCHED_SIGNIFICANT_SIGMA = 5

export interface MatchedChange {
  detector: number
  earlier: VisitInfo
  later: VisitInfo
  /** Later / earlier flux at matched λ. */
  ratio: number
  /** |ln ratio| over its error. */
  significance: number
  nPairs: number
  lambdaMin: number
  lambdaMax: number
}

interface Sample {
  logLambda: number
  flux: number
  err: number
}

function localSlope(samples: readonly Sample[], i: number): number | null {
  const own = samples[i]
  if (!own) return null
  const slopes = [samples[i - 1], samples[i + 1]].flatMap((n) =>
    n && n.logLambda !== own.logLambda ? [Math.abs(Math.log(n.flux / own.flux) / (n.logLambda - own.logLambda))] : [],
  )
  return slopes.length > 0 ? Math.max(...slopes) : null
}

function compareVisits(detector: number, earlier: readonly Sample[], later: readonly Sample[]) {
  const [lo, hi] = DETECTOR_BANDS_UM[detector] ?? [1, Math.E]
  const width = Math.log(hi / lo) / LVF_CHANNELS
  let sumW = 0
  let sumWR = 0
  const lambdas: number[] = []
  earlier.forEach((a, i) => {
    let j = -1
    let best = Infinity
    later.forEach((b, k) => {
      const d = Math.abs(b.logLambda - a.logLambda)
      if (d < best) {
        best = d
        j = k
      }
    })
    const b = later[j]
    if (!b || best > width) return
    const slopes = [localSlope(earlier, i), localSlope(later, j)].flatMap((s) => (s === null ? [] : [s]))
    const slope = slopes.length > 0 ? Math.max(...slopes) : DEFAULT_LOG_SLOPE
    const variance = (a.err / a.flux) ** 2 + (b.err / b.flux) ** 2 + 2 * CALIBRATION_FLOOR ** 2 + (slope * best) ** 2
    sumW += 1 / variance
    sumWR += Math.log(b.flux / a.flux) / variance
    lambdas.push(Math.exp(a.logLambda))
  })
  if (sumW === 0) return null
  const mean = sumWR / sumW
  return {
    ratio: Math.exp(mean),
    significance: Math.abs(mean) * Math.sqrt(sumW),
    nPairs: lambdas.length,
    lambdaMin: Math.min(...lambdas),
    lambdaMax: Math.max(...lambdas),
  }
}

/**
 * Within a visit every exposure samples its own λ, so visit means mix the spectrum with variability. Each exposure
 * is paired with the nearest-λ exposure of another visit (≤ 1 LVF channel apart) and only those ratios are compared.
 * Returns the most significant visit pair per detector.
 */
export function strongestMatchedChanges(
  points: readonly SpectrumPoint[],
  visits: readonly VisitInfo[],
): MatchedChange[] {
  const byDetector = new Map<number, Map<string, Sample[]>>()
  for (const p of points) {
    const usable = pointStatus(p) === 'measured' && p.flux_ujy !== null && p.err_ujy !== null
    if (!usable || p.flux_ujy === null || p.err_ujy === null || p.err_ujy <= 0 || p.flux_ujy <= 0) continue
    const visitsOfDetector = byDetector.get(p.detector) ?? new Map<string, Sample[]>()
    byDetector.set(p.detector, visitsOfDetector)
    const list = visitsOfDetector.get(p.visit) ?? []
    visitsOfDetector.set(p.visit, list)
    list.push({ logLambda: Math.log(p.lambda_um), flux: p.flux_ujy, err: p.err_ujy })
  }
  const result: MatchedChange[] = []
  for (const [detector, byVisit] of byDetector) {
    const ordered = visits.filter((v) => byVisit.has(v.id))
    const byLambda = (v: VisitInfo) => [...(byVisit.get(v.id) ?? [])].sort((a, b) => a.logLambda - b.logLambda)
    const sorted = new Map(ordered.map((v) => [v.id, byLambda(v)]))
    const changes = ordered.flatMap((earlier, i) =>
      ordered.slice(i + 1).flatMap((later) => {
        const c = compareVisits(detector, sorted.get(earlier.id) ?? [], sorted.get(later.id) ?? [])
        return c ? [{ detector, earlier, later, ...c }] : []
      }),
    )
    const best = changes.reduce<MatchedChange | null>((a, c) => (!a || c.significance > a.significance ? c : a), null)
    if (best) result.push(best)
  }
  return result.sort((a, b) => a.detector - b.detector)
}

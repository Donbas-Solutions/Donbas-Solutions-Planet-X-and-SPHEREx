import type { Frame, SpectrumPoint } from '../api/types'
import { presetNear, type PresetId } from './presets'

export type PointStatus = 'measured' | 'saturated' | 'flagged'

export interface VisitInfo {
  id: string
  /** The visit's name in the player; else the UTC month of its first point (the day too if months collide). */
  label: string
  mjdStart: number
  count: number
}

/** The scatter palette validates for all pairs only up to three series (colour-blind safety). */
export const MAX_VISIT_SERIES = 3

const MJD_UNIX_EPOCH = 40587

export function mjdToIsoDate(mjd: number): string {
  return new Date((mjd - MJD_UNIX_EPOCH) * 86_400_000).toISOString().slice(0, 10)
}

/** A point is plotted only with a flux; saturated ones are labelled as such, the rest are masked by FLAGS. */
export function pointStatus(p: SpectrumPoint): PointStatus {
  if (p.saturated) return 'saturated'
  return p.flux_ujy === null ? 'flagged' : 'measured'
}

/** `v2` → "2026-03" from the label of the visit's combined frame, so charts and player name a visit alike. */
function frameVisitLabels(frames: readonly Frame[]): Map<string, string> {
  const labels = new Map<string, string>()
  for (const f of frames) {
    const [visit = '', kind] = f.id.split('-')
    if (kind === 'all') labels.set(visit, f.label.split(' · ')[0] ?? f.label)
  }
  return labels
}

export function visitsOf(points: readonly SpectrumPoint[], frames: readonly Frame[] = []): VisitInfo[] {
  const byId = new Map<string, { mjdStart: number; count: number }>()
  for (const p of points) {
    const v = byId.get(p.visit)
    if (v) {
      v.mjdStart = Math.min(v.mjdStart, p.mjd)
      v.count++
    } else {
      byId.set(p.visit, { mjdStart: p.mjd, count: 1 })
    }
  }
  const visits = [...byId].map(([id, v]) => ({ id, date: mjdToIsoDate(v.mjdStart), ...v }))
  const perMonth = new Map<string, number>()
  for (const v of visits) perMonth.set(v.date.slice(0, 7), (perMonth.get(v.date.slice(0, 7)) ?? 0) + 1)
  const fromFrames = frameVisitLabels(frames)
  return visits
    .map(({ date, ...v }) => {
      const fromPoints = (perMonth.get(date.slice(0, 7)) ?? 0) > 1 ? date : date.slice(0, 7)
      return { ...v, label: fromFrames.get(v.id) ?? fromPoints }
    })
    .sort((a, b) => a.mjdStart - b.mjdStart)
}

/** Colour slots: index = palette slot, value = series id (visit or detector); the first ids fill the slots. */
export function slotsFor(ids: readonly string[]): (string | null)[] {
  return Array.from({ length: MAX_VISIT_SERIES }, (_, i) => ids[i] ?? null)
}

/** Every visit, or the first and last (longest baseline). */
export function defaultVisitSlots(visits: readonly VisitInfo[]): (string | null)[] {
  const chosen = visits.length <= MAX_VISIT_SERIES ? visits : [visits[0], visits[visits.length - 1]]
  return slotsFor(chosen.flatMap((v) => (v ? [v.id] : [])))
}

/** Toggling keeps the other series in their slots, so their colours never change. */
export function toggleSlot(slots: readonly (string | null)[], id: string): (string | null)[] {
  if (slots.includes(id)) return slots.map((s) => (s === id ? null : s))
  const free = slots.indexOf(null)
  if (free < 0) return [...slots]
  return slots.map((s, i) => (i === free ? id : s))
}

/** Log flux when the measured fluxes span more than two decades. */
export function prefersLogScale(points: readonly SpectrumPoint[]): boolean {
  const positive = points.flatMap((p) => (p.flux_ujy !== null && p.flux_ujy > 0 ? [p.flux_ujy] : []))
  if (positive.length < 2) return false
  return Math.max(...positive) / Math.min(...positive) > 100
}

export interface DetectorBand {
  detector: number
  lambdaMin: number
  lambdaMax: number
}

export function detectorBands(points: readonly SpectrumPoint[]): DetectorBand[] {
  const bands = new Map<number, DetectorBand>()
  for (const p of points) {
    const b = bands.get(p.detector)
    if (b) {
      b.lambdaMin = Math.min(b.lambdaMin, p.lambda_um)
      b.lambdaMax = Math.max(b.lambdaMax, p.lambda_um)
    } else {
      bands.set(p.detector, { detector: p.detector, lambdaMin: p.lambda_um, lambdaMax: p.lambda_um })
    }
  }
  return [...bands.values()].sort((a, b) => a.detector - b.detector)
}

const POSITION_CAVEATS: Partial<Record<PresetId, string>> = {
  wise0855:
    'At this position the aperture is blended with a field star: below 1.6 µm the flux is the field star’s, and at ' +
    '≥ 3.8 µm it is only an upper bound for WISE 0855. Not a measurement of WISE 0855 itself.',
}

/** Caveats describe the sky position (e.g. a blended aperture), so they apply to typed coordinates and live data too. */
export function positionCaveat(presetId: PresetId | null, position: { ra: number; dec: number } | null): string | null {
  const id = presetId ?? (position ? presetNear(position.ra, position.dec)?.id : undefined)
  return (id && POSITION_CAVEATS[id]) ?? null
}

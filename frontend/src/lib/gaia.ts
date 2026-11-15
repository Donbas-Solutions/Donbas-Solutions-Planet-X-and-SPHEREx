import type { Frame, GaiaStar, Grid, PixelPos } from '../api/types'
import { skyToPixel } from './wcs'

const DAYS_PER_JULIAN_YEAR = 365.25
const MAS_PER_DEG = 3.6e6
const RAD_PER_DEG = Math.PI / 180
/** A star is shown as moving when its proper motion carries it at least this far during the sequence. */
export const MOVER_MIN_SHIFT_PX = 0.25

/** Stars at their positions on `refMjd`; other epochs are reached with their proper motions. */
export interface GaiaField {
  stars: readonly GaiaStar[]
  refMjd: number
}

export interface GaiaMarker {
  star: GaiaStar
  px: PixelPos
  isMover: boolean
}

export interface SequenceSpan {
  /** The middle of the sequence: the step from it to any frame is the shortest. */
  midMjd: number
  years: number
}

export function sequenceSpan(frames: readonly Frame[]): SequenceSpan | null {
  if (frames.length === 0) return null
  const epochs = frames.map((f) => f.mjd_mid)
  const first = Math.min(...epochs)
  const last = Math.max(...epochs)
  return { midMjd: Math.round(((first + last) / 2) * 100) / 100, years: (last - first) / DAYS_PER_JULIAN_YEAR }
}

export function totalPmMasyr(star: GaiaStar): number {
  return star.pmra === null || star.pmdec === null ? 0 : Math.hypot(star.pmra, star.pmdec)
}

/** Position angle of the motion, degrees east of north. */
export function pmPositionAngleDeg(star: GaiaStar): number | null {
  if (star.pmra === null || star.pmdec === null) return null
  return (Math.atan2(star.pmra, star.pmdec) / RAD_PER_DEG + 360) % 360
}

export function isMover(star: GaiaStar, grid: Grid, spanYears: number): boolean {
  return ((totalPmMasyr(star) / 1000) * spanYears) / grid.pixscale_arcsec >= MOVER_MIN_SHIFT_PX
}

/**
 * Linear step from the reference epoch. The backend did the rigorous propagation from Gaia's epoch 2016.0 to
 * `refMjd`; over the remaining ≤ 1 yr the linear step is off by < 0.001″ even for Barnard's Star.
 */
function positionAt(star: GaiaStar, refMjd: number, mjd: number): { ra: number; dec: number } {
  if (star.pmra === null || star.pmdec === null) return star
  const years = (mjd - refMjd) / DAYS_PER_JULIAN_YEAR
  return {
    ra: star.ra + (star.pmra * years) / MAS_PER_DEG / Math.cos(star.dec * RAD_PER_DEG),
    dec: star.dec + (star.pmdec * years) / MAS_PER_DEG,
  }
}

/** Stars that fall on the frame at `mjd`, in catalog order (brightest first). */
export function gaiaMarkers(field: GaiaField, grid: Grid, mjd: number, spanYears: number): GaiaMarker[] {
  const markers: GaiaMarker[] = []
  for (const star of field.stars) {
    const { ra, dec } = positionAt(star, field.refMjd, mjd)
    const px = skyToPixel(grid, ra, dec)
    if (!px || px.x < -0.5 || px.y < -0.5 || px.x >= grid.npix - 0.5 || px.y >= grid.npix - 0.5) continue
    markers.push({ star, px, isMover: isMover(star, grid, spanYears) })
  }
  return markers
}

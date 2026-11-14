import type { FlagGroup, Stretch } from '../api/types'
import { formatDegrees, parseAngle } from './coords'
import { findPreset, type PresetId } from './presets'

export const FOV_MIN_ARCMIN = 2
export const FOV_MAX_ARCMIN = 30
export const FOV_DEFAULT_ARCMIN = 10
export const FPS_MIN = 0.5
export const FPS_MAX = 3
export const FPS_DEFAULT = 2
export const DETECTOR_IDS = [1, 2, 3, 4, 5, 6] as const

export type ViewMode = 'blink' | 'diff'
export type StretchKind = Stretch['kind']
export type OverlayGroup = Exclude<FlagGroup, 'info'>
export type DetectorChoice = 'all' | readonly number[]

export interface ProperMotion {
  /** mas/yr, includes cos(dec) */
  pmra: number
  /** mas/yr */
  pmdec: number
  /** Julian year of the position */
  epoch: number
}

/** Page URL state (docs/spec.md §5.3). Precedence: target > name > ra/dec. */
export interface ViewParams {
  target: PresetId | null
  name: string | null
  ra: number | null
  dec: number | null
  fovArcmin: number
  det: DetectorChoice
  view: ViewMode
  a: string | null
  b: string | null
  fps: number
  stretch: StretchKind
  flags: readonly OverlayGroup[]
  pm: ProperMotion | null
  manifest: string | null
}

export const DEFAULT_PARAMS: ViewParams = {
  target: null,
  name: null,
  ra: null,
  dec: null,
  fovArcmin: FOV_DEFAULT_ARCMIN,
  det: 'all',
  view: 'blink',
  a: null,
  b: null,
  fps: FPS_DEFAULT,
  stretch: 'asinh',
  flags: [],
  pm: null,
  manifest: null,
}

const VIEWS: readonly ViewMode[] = ['blink', 'diff']
const STRETCHES: readonly StretchKind[] = ['asinh', 'linear', 'log']
const OVERLAY_GROUPS: readonly OverlayGroup[] = ['saturation', 'bad', 'artifact']
const MAX_TEXT = 200

function oneOf<T extends string>(value: string, allowed: readonly T[]): T | undefined {
  return allowed.find((a) => a === value)
}

export function clampFov(fovArcmin: number): number {
  return Math.min(FOV_MAX_ARCMIN, Math.max(FOV_MIN_ARCMIN, fovArcmin))
}

function parseDetectors(raw: string): DetectorChoice | undefined {
  if (raw === 'all') return 'all'
  const ids = raw.split(',').map((s) => Number(s.trim()))
  if (ids.length === 0 || ids.some((d) => !Number.isInteger(d) || d < 1 || d > 6)) return undefined
  const unique = [...new Set(ids)].sort((x, y) => x - y)
  return unique.length === DETECTOR_IDS.length ? 'all' : unique
}

function isSafeUrl(raw: string): boolean {
  try {
    const url = new URL(raw, window.location.href)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

/** Invalid values fall back to the default and add a notice; unknown params are ignored. */
export function parseViewParams(search: string): { params: ViewParams; notices: string[] } {
  const q = new URLSearchParams(search)
  const p: ViewParams = { ...DEFAULT_PARAMS }
  const notices: string[] = []
  const invalid = (key: string, why: string) => notices.push(`Ignored “${key}”: ${why}.`)

  const target = q.get('target')
  if (target !== null) {
    const preset = findPreset(target)
    if (preset) p.target = preset.id
    else invalid('target', 'unknown test target')
  }

  const name = q.get('name')?.trim()
  if (name) p.name = name.slice(0, MAX_TEXT)

  const raRaw = q.get('ra')
  const decRaw = q.get('dec')
  if (raRaw !== null || decRaw !== null) {
    const ra = raRaw === null ? null : parseAngle(raRaw, 'ra')
    const dec = decRaw === null ? null : parseAngle(decRaw, 'dec')
    if (!ra || !dec) invalid('ra/dec', 'both are needed')
    else if (!ra.ok) invalid('ra', ra.error)
    else if (!dec.ok) invalid('dec', dec.error)
    else {
      p.ra = ra.value
      p.dec = dec.value
    }
  }

  const fov = q.get('fov')
  if (fov !== null) {
    const v = Number(fov)
    if (!Number.isFinite(v)) invalid('fov', 'not a number')
    else {
      p.fovArcmin = clampFov(v)
      if (p.fovArcmin !== v) notices.push(`Field of view limited to ${FOV_MIN_ARCMIN}–${FOV_MAX_ARCMIN}′ (got ${v}′).`)
    }
  }

  const det = q.get('det')
  if (det !== null) {
    const d = parseDetectors(det)
    if (d) p.det = d
    else invalid('det', 'use “all” or detectors 1–6')
  }

  const view = q.get('view')
  if (view !== null) {
    const v = oneOf(view, VIEWS)
    if (v) p.view = v
    else invalid('view', 'use blink or diff')
  }

  p.a = q.get('a')?.slice(0, MAX_TEXT) || null
  p.b = q.get('b')?.slice(0, MAX_TEXT) || null

  const fps = q.get('fps')
  if (fps !== null) {
    const v = Number(fps)
    if (!Number.isFinite(v)) invalid('fps', 'not a number')
    else {
      p.fps = Math.min(FPS_MAX, Math.max(FPS_MIN, v))
      if (p.fps !== v) notices.push(`Playback speed limited to ${FPS_MIN}–${FPS_MAX} fps (flashing-content safety).`)
    }
  }

  const stretch = q.get('stretch')
  if (stretch !== null) {
    const s = oneOf(stretch, STRETCHES)
    if (s) p.stretch = s
    else invalid('stretch', 'use asinh, linear or log')
  }

  const flags = q.get('flags')
  if (flags) {
    const groups = flags.split(',').map((g) => oneOf(g.trim(), OVERLAY_GROUPS))
    if (groups.every((g) => g !== undefined)) p.flags = [...new Set(groups)]
    else invalid('flags', 'use saturation, bad, artifact')
  }

  const pmra = q.get('pmra')
  const pmdec = q.get('pmdec')
  if (pmra !== null || pmdec !== null) {
    const epoch = Number(q.get('epoch') ?? 2000)
    const values = [Number(pmra), Number(pmdec), epoch]
    if (pmra === null || pmdec === null || !values.every(Number.isFinite)) {
      invalid('pmra/pmdec/epoch', 'need two numbers in mas/yr and a Julian year')
    } else p.pm = { pmra: Number(pmra), pmdec: Number(pmdec), epoch }
  }

  const manifest = q.get('manifest')
  if (manifest !== null) {
    if (isSafeUrl(manifest)) p.manifest = manifest
    else invalid('manifest', 'not an http(s) URL')
  }

  return { params: p, notices }
}

/** Canonical query string (with `?`, or empty); params that hold their default are omitted. */
export function viewParamsToSearch(p: ViewParams): string {
  const q = new URLSearchParams()
  if (p.target) q.set('target', p.target)
  if (p.name) q.set('name', p.name)
  if (p.ra !== null && p.dec !== null) {
    q.set('ra', formatDegrees(p.ra))
    q.set('dec', formatDegrees(p.dec))
  }
  if (p.fovArcmin !== FOV_DEFAULT_ARCMIN) q.set('fov', String(p.fovArcmin))
  if (p.det !== 'all') q.set('det', p.det.join(','))
  if (p.view !== 'blink') q.set('view', p.view)
  if (p.a) q.set('a', p.a)
  if (p.b) q.set('b', p.b)
  if (p.fps !== FPS_DEFAULT) q.set('fps', String(p.fps))
  if (p.stretch !== 'asinh') q.set('stretch', p.stretch)
  if (p.flags.length > 0) q.set('flags', p.flags.join(','))
  if (p.pm) {
    q.set('pmra', String(p.pm.pmra))
    q.set('pmdec', String(p.pm.pmdec))
    q.set('epoch', String(p.pm.epoch))
  }
  if (p.manifest) q.set('manifest', p.manifest)
  const s = q.toString()
  return s ? `?${s}` : ''
}

export type SequenceSource =
  | { kind: 'landing' }
  | { kind: 'manifest'; url: string; isPrebaked: boolean }
  | { kind: 'resolve'; name: string }
  | { kind: 'live'; ra: number; dec: number; fovArcmin: number; pm: ProperMotion | null }

/**
 * Where the sequence comes from. A `name` that already has `ra`/`dec` next to it was resolved earlier, so the
 * stored position is used and the name is only a label: shared links keep working when SIMBAD is down.
 */
export function sequenceSource(p: ViewParams, base: string): SequenceSource {
  if (p.manifest) return { kind: 'manifest', url: p.manifest, isPrebaked: false }
  if (p.target) return { kind: 'manifest', url: `${base}prebaked/${p.target}/sequence.json`, isPrebaked: true }
  if (p.ra !== null && p.dec !== null) {
    // Same precision as the URL: the backend caches by exact position, so a reload must ask for the same numbers.
    const ra = Number(formatDegrees(p.ra))
    const dec = Number(formatDegrees(p.dec))
    return { kind: 'live', ra, dec, fovArcmin: p.fovArcmin, pm: p.pm }
  }
  if (p.name) return { kind: 'resolve', name: p.name }
  return { kind: 'landing' }
}

export function sourceKey(s: SequenceSource): string {
  return JSON.stringify(s)
}

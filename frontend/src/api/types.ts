// API contract types. Source of truth: docs/api.md and backend/app/models.py — keep in sync.

export type FrameKind = 'visit_stack' | 'exposure' | 'diff' | 'allwise'
export type FlagGroup = 'bad' | 'saturation' | 'artifact' | 'info'
export type WarningCode = 'saturated' | 'few_exposures' | 'incomplete_lambda'

export interface Grid {
  ra: number
  dec: number
  fov_arcmin: number
  npix: number
  pixscale_arcsec: number
  wcs: Record<string, string | number>
}

export interface Stretch {
  kind: 'asinh' | 'linear' | 'log'
  vmin: number
  vmax: number
  a: number
}

/** 0-based pixel position; y row 0 = south (FITS order). */
export interface PixelPos {
  x: number
  y: number
}

export interface Frame {
  id: string
  kind: FrameKind
  label: string
  mjd_mid: number
  date_range: [string, string]
  detectors: number[]
  lambda_um: [number, number]
  n_exposures: number
  /** float32 LE array URL, relative to the manifest URL (or an absolute path). */
  data: string
  /** uint32 LE OR-combined FLAGS array URL, same shape. */
  flags: string | null
  /** [ny, nx] */
  shape: [number, number]
  expected_px: PixelPos | null
  warnings: FrameWarning[]
}

/** `code` is stable and meant for grouping and counting; `message` is for display. */
export interface FrameWarning {
  code: WarningCode
  message: string
}

export interface FlagBit {
  bit: number
  name: string
  description: string
  group: FlagGroup
  mask_in_stack: boolean
}

export interface SequenceMeta {
  target_name: string | null
  collections: string[]
  n_exposures_total: number
  generated_at: string
  pipeline_tags: string[]
  mock: boolean
  /** Spectrum of the target, relative to the manifest URL (or an absolute path); absent = none bundled. */
  spectrum?: string | null
}

export interface Sequence {
  grid: Grid
  stretch: Stretch
  flag_bits: FlagBit[]
  frames: Frame[]
  meta: SequenceMeta
}

/** Saturated points have `flux_ujy: null`: label them, never plot a value (SR-6). */
export interface SpectrumPoint {
  lambda_um: number
  flux_ujy: number | null
  err_ujy: number | null
  mjd: number
  detector: number
  visit: string
  saturated: boolean
  flags: number
}

export interface Spectrum {
  points: SpectrumPoint[]
}

export interface JobStatus {
  status: 'queued' | 'running' | 'done' | 'error'
  progress: { stage: string; done: number; total: number }
  result?: Sequence | null
  error?: string | null
}

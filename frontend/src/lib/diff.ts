import type { LoadedFrame } from './frames'
import { missingDetectors } from './playlist'
import type { GridImage } from './render'
import { finitePercentiles } from './stats'

export interface DiffImage extends GridImage {
  earlier: LoadedFrame
  later: LoadedFrame
  /** Half-width of the symmetric display range, from the 99.5th percentile of |diff|. */
  autoRange: number
  warnings: readonly string[]
}

export type DiffResult = { ok: true; diff: DiffImage } | { ok: false; error: string }

/** Later − earlier (by mjd_mid). NaN in either input stays NaN; flags are the OR of both inputs. */
export function diffFrames(a: LoadedFrame, b: LoadedFrame): DiffResult {
  const [earlier, later] = a.frame.mjd_mid <= b.frame.mjd_mid ? [a, b] : [b, a]
  const [ny, nx] = earlier.frame.shape
  const [lny, lnx] = later.frame.shape
  if (ny !== lny || nx !== lnx) return { ok: false, error: 'The two frames are not on the same grid.' }
  const isCombined = earlier.frame.detectors.length > 1 && later.frame.detectors.length > 1
  if (!isCombined && earlier.frame.detectors.join() !== later.frame.detectors.join()) {
    return { ok: false, error: 'Difference needs two frames from the same detectors.' }
  }

  const n = ny * nx
  const data = new Float32Array(n)
  for (let i = 0; i < n; i++) data[i] = (later.data[i] ?? Number.NaN) - (earlier.data[i] ?? Number.NaN)

  let flags: Uint32Array | null = null
  if (earlier.flags || later.flags) {
    flags = new Uint32Array(n)
    for (let i = 0; i < n; i++) flags[i] = ((earlier.flags?.[i] ?? 0) | (later.flags?.[i] ?? 0)) >>> 0
  }

  const abs = data.map(Math.abs)
  const [p] = finitePercentiles([abs], [99.5]) ?? [1]
  const warnings = [...new Set([...earlier.frame.warnings, ...later.frame.warnings].map((w) => w.message))]
  for (const f of [earlier, later]) {
    const missing = missingDetectors(f.frame.detectors)
    if (missing.length > 0) {
      warnings.push(`${f.frame.label} has no ${missing.map((d) => `D${d}`).join(', ')}: the two stacks differ in λ.`)
    }
  }
  if (earlier.frame.lambda_um.join() !== later.frame.lambda_um.join()) {
    warnings.push('The two frames cover different wavelength ranges: part of the difference may be spectral.')
  }
  if (earlier.frame.id === later.frame.id) warnings.push('A and B are the same frame.')

  return {
    ok: true,
    diff: { data, flags, shape: [ny, nx], earlier, later, autoRange: p && p > 0 ? p : 1, warnings },
  }
}

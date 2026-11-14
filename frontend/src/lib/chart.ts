export type ScaleKind = 'linear' | 'log'

export interface Scale {
  kind: ScaleKind
  domain: readonly [number, number]
  range: readonly [number, number]
  ticks: readonly number[]
  map: (v: number) => number
}

/** [min, max] of the finite values; null when there are none. */
export function extent(values: Iterable<number>): [number, number] | null {
  let lo = Infinity
  let hi = -Infinity
  for (const v of values) {
    if (!Number.isFinite(v)) continue
    if (v < lo) lo = v
    if (v > hi) hi = v
  }
  return lo <= hi ? [lo, hi] : null
}

export function pad(domain: readonly [number, number], fraction: number): [number, number] {
  const [lo, hi] = domain
  const span = hi - lo || Math.abs(hi) || 1
  return [lo - span * fraction, hi + span * fraction]
}

export function niceTicks(lo: number, hi: number, count: number): number[] {
  if (!(hi > lo)) return [lo]
  const raw = (hi - lo) / Math.max(count, 1)
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = ([1, 2, 5, 10].find((m) => m * power >= raw) ?? 10) * power
  const ticks: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
    ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v)
  }
  return ticks
}

export function logTicks(lo: number, hi: number): number[] {
  if (!(lo > 0) || !(hi > lo)) return []
  const first = Math.floor(Math.log10(lo))
  const last = Math.ceil(Math.log10(hi))
  const decades = last - first
  const mantissas = decades <= 3 ? [1, 2, 5] : [1]
  const ticks: number[] = []
  for (let e = first; e <= last; e++) {
    for (const m of mantissas) {
      const v = m * 10 ** e
      if (v >= lo && v <= hi) ticks.push(v)
    }
  }
  return ticks
}

export function makeScale(
  kind: ScaleKind,
  domain: readonly [number, number],
  range: readonly [number, number],
  tickCount = 5,
): Scale {
  const [d0, d1] = domain
  const [r0, r1] = range
  if (kind === 'log') {
    const l0 = Math.log10(d0)
    const span = Math.log10(d1) - l0 || 1
    return {
      kind,
      domain,
      range,
      ticks: logTicks(d0, d1),
      map: (v) => r0 + ((Math.log10(v) - l0) / span) * (r1 - r0),
    }
  }
  const span = d1 - d0 || 1
  return { kind, domain, range, ticks: niceTicks(d0, d1, tickCount), map: (v) => r0 + ((v - d0) / span) * (r1 - r0) }
}

export function formatTick(v: number): string {
  if (v === 0) return '0'
  const abs = Math.abs(v)
  if (abs >= 1e5 || abs < 1e-2) return v.toExponential(0).replace('e+', 'e')
  return String(Number(v.toPrecision(3)))
}

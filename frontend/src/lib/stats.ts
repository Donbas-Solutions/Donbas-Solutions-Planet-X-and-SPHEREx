const MAX_SAMPLES = 200_000

/** Percentiles (0–100) of the finite values of several arrays; strided sampling keeps big sequences cheap. */
export function finitePercentiles(arrays: readonly Float32Array[], ps: readonly number[]): number[] | null {
  const total = arrays.reduce((n, a) => n + a.length, 0)
  const stride = Math.max(1, Math.ceil(total / MAX_SAMPLES))
  const values: number[] = []
  for (const a of arrays) {
    for (let i = 0; i < a.length; i += stride) {
      const v = a[i] ?? Number.NaN
      if (Number.isFinite(v)) values.push(v)
    }
  }
  if (values.length === 0) return null
  values.sort((x, y) => x - y)
  return ps.map((p) => values[Math.min(values.length - 1, Math.round((p / 100) * (values.length - 1)))] ?? 0)
}

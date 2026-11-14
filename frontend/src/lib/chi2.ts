const LANCZOS = [
  676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905,
  -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
]

function logGamma(z: number): number {
  if (z < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - logGamma(1 - z)
  const x = z - 1
  let sum = 0.99999999999980993
  LANCZOS.forEach((c, i) => {
    sum += c / (x + i + 1)
  })
  const t = x + LANCZOS.length - 0.5
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(sum)
}

const EPS = 1e-14
const MAX_ITER = 500

/** Regularized upper incomplete gamma Q(a, x): series below a + 1, continued fraction above (Numerical Recipes). */
function upperGammaQ(a: number, x: number): number {
  if (x <= 0) return 1
  const front = Math.exp(-x + a * Math.log(x) - logGamma(a))
  if (x < a + 1) {
    let term = 1 / a
    let sum = term
    for (let n = 1; n < MAX_ITER && Math.abs(term) > Math.abs(sum) * EPS; n++) {
      term *= x / (a + n)
      sum += term
    }
    return 1 - sum * front
  }
  let b = x + 1 - a
  let c = 1 / Number.MIN_VALUE
  let d = 1 / b
  let h = d
  for (let i = 1; i < MAX_ITER; i++) {
    const an = -i * (i - a)
    b += 2
    d = an * d + b
    if (Math.abs(d) < Number.MIN_VALUE) d = Number.MIN_VALUE
    c = b + an / c
    if (Math.abs(c) < Number.MIN_VALUE) c = Number.MIN_VALUE
    d = 1 / d
    const delta = d * c
    h *= delta
    if (Math.abs(delta - 1) < EPS) break
  }
  return front * h
}

/** Probability that a χ² with `dof` degrees of freedom is at least `chi2`. */
export function chi2SurvivalP(chi2: number, dof: number): number {
  return Math.min(Math.max(upperGammaQ(dof / 2, chi2 / 2), 0), 1)
}

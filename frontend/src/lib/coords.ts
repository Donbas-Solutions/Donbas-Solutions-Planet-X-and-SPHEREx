export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string }

export interface SkyPosition {
  /** ICRS degrees */
  ra: number
  dec: number
}

const NUMBER = /[+-]?(?:\d+(?:\.\d*)?|\.\d+)/g
const SEPARATORS = /^[\s:hmsd°'′"″]*$/i
const COORDINATE_CHARS = /^[\d\s.,:+\-hmsd°'′"″]+$/i

/** True when the text could only be coordinates (digits, signs and h/m/s/d separators), not an object name. */
export function looksLikeCoordinates(input: string): boolean {
  return /\d/.test(input) && COORDINATE_CHARS.test(input.trim())
}

/**
 * One angle: decimal degrees, or sexagesimal `17 57 48.5` / `17:57:48.5` / `17h57m48.5s`.
 * Sexagesimal (or `h`-suffixed) RA is in hours. Dec is always degrees.
 */
export function parseAngle(raw: string, kind: 'ra' | 'dec'): Parsed<number> {
  const label = kind === 'ra' ? 'RA' : 'Dec'
  const tokens = raw.match(NUMBER) ?? []
  if (tokens.length === 0 || tokens.length > 3) return { ok: false, error: `${label}: expected 1 or 3 numbers` }
  if (!SEPARATORS.test(raw.replace(NUMBER, ''))) return { ok: false, error: `${label}: unexpected characters` }

  const [first = '', ...rest] = tokens
  if (rest.some((t) => /^[+-]/.test(t))) return { ok: false, error: `${label}: only the first number may have a sign` }
  // The sign comes from the text: Number('-00') is -0, which loses it.
  const isNegative = first.startsWith('-')
  if (kind === 'ra' && isNegative) return { ok: false, error: 'RA must be positive' }

  const parts = tokens.map((t) => Math.abs(Number(t)))
  if (parts.some((p) => !Number.isFinite(p))) return { ok: false, error: `${label}: not a number` }
  const [whole = 0, minutes = 0, seconds = 0] = parts
  if (parts.length > 1 && !Number.isInteger(whole)) return { ok: false, error: `${label}: degrees/hours must be whole` }
  if (parts.length > 2 && !Number.isInteger(minutes)) return { ok: false, error: `${label}: minutes must be whole` }
  if (minutes >= 60 || seconds >= 60) return { ok: false, error: `${label}: minutes and seconds must be < 60` }

  const isHours = kind === 'ra' && (parts.length > 1 || /h/i.test(raw))
  const magnitude = (whole + minutes / 60 + seconds / 3600) * (isHours ? 15 : 1)
  const value = isNegative ? -magnitude : magnitude

  if (kind === 'ra' && !(value >= 0 && value < 360)) return { ok: false, error: 'RA must be in 0–360° (0–24h)' }
  if (kind === 'dec' && !(value >= -90 && value <= 90)) return { ok: false, error: 'Dec must be in −90…+90°' }
  return { ok: true, value }
}

/** "RA Dec" in one string: 2 decimal numbers, 6 sexagesimal numbers, or two parts separated by a comma. */
export function parseCoordinates(input: string): Parsed<SkyPosition> {
  let raRaw: string
  let decRaw: string
  const comma = input.indexOf(',')
  if (comma >= 0) {
    raRaw = input.slice(0, comma)
    decRaw = input.slice(comma + 1)
  } else {
    const tokens = [...input.matchAll(NUMBER)]
    const split = tokens.length === 2 ? 1 : tokens.length === 6 ? 3 : null
    const decStart = split === null ? undefined : tokens[split]?.index
    if (decStart === undefined) {
      return { ok: false, error: 'Enter RA and Dec in the same format: 2 decimal or 6 sexagesimal numbers' }
    }
    raRaw = input.slice(0, decStart)
    decRaw = input.slice(decStart)
  }
  const ra = parseAngle(raRaw, 'ra')
  if (!ra.ok) return ra
  const dec = parseAngle(decRaw, 'dec')
  if (!dec.ok) return dec
  return { ok: true, value: { ra: ra.value, dec: dec.value } }
}

export function formatDegrees(deg: number): string {
  return String(Number(deg.toFixed(6)))
}

export type Rgb = readonly [number, number, number]

/** 256 RGB triplets, index = round(255 * t). */
export type Colormap = Uint8ClampedArray

function fromStops(stops: readonly (readonly [number, Rgb])[]): Colormap {
  const lut = new Uint8ClampedArray(256 * 3)
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    const hi = stops.findIndex(([s]) => s >= t)
    const [t1, c1] = stops[Math.max(hi, 1)] ?? stops[stops.length - 1] ?? [1, [255, 255, 255]]
    const [t0, c0] = stops[Math.max(hi, 1) - 1] ?? [0, [0, 0, 0]]
    const f = t1 === t0 ? 0 : (t - t0) / (t1 - t0)
    for (let k = 0; k < 3; k++) lut[i * 3 + k] = (c0[k] ?? 0) + f * ((c1[k] ?? 0) - (c0[k] ?? 0))
  }
  return lut
}

export const GREY: Colormap = fromStops([
  [0, [0, 0, 0]],
  [1, [255, 255, 255]],
])

/** Colour-blind-safe diverging map (blue → near-white → orange), never red–green. */
export const BLUE_ORANGE: Colormap = fromStops([
  [0, [33, 102, 172]],
  [0.5, [247, 247, 247]],
  [1, [230, 97, 1]],
])

/** No data: a colour that neither map produces. */
export const NAN_COLOR: Rgb = [110, 30, 140]

export function colormapCss(lut: Colormap, steps = 9): string {
  const parts: string[] = []
  for (let s = 0; s < steps; s++) {
    const i = Math.round((s / (steps - 1)) * 255) * 3
    parts.push(`rgb(${lut[i] ?? 0} ${lut[i + 1] ?? 0} ${lut[i + 2] ?? 0})`)
  }
  return `linear-gradient(to right, ${parts.join(', ')})`
}

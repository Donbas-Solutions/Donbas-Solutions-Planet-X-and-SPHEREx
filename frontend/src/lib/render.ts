import type { Stretch } from '../api/types'
import { NAN_COLOR, type Colormap, type Rgb } from './colormap'

/** A float image on the common grid: row-major [ny, nx], row 0 = south. */
export interface GridImage {
  data: Float32Array
  flags: Uint32Array | null
  shape: readonly [number, number]
}

/** Map a value to 0..1 with a shared stretch; vmin === vmax maps everything to 0. */
export function stretchValue(v: number, s: Stretch): number {
  const span = s.vmax - s.vmin
  const t = span > 0 ? Math.min(1, Math.max(0, (v - s.vmin) / span)) : 0
  switch (s.kind) {
    case 'linear':
      return t
    case 'log':
      return Math.log10(1 + 1000 * t) / 3
    case 'asinh':
      return Math.asinh(t / s.a) / Math.asinh(1 / s.a)
  }
}

export interface RenderOptions {
  overlayMask?: number
  overlayColor?: Rgb
}

/**
 * Draw at 1 canvas pixel per data pixel (scale up with CSS + image-rendering: pixelated).
 * Data row 0 is south, canvas row 0 is top, so rows are flipped to get north up.
 */
export function renderImage(
  ctx: CanvasRenderingContext2D,
  img: GridImage,
  stretch: Stretch,
  lut: Colormap,
  { overlayMask = 0, overlayColor = [255, 60, 60] }: RenderOptions = {},
): void {
  const [ny, nx] = img.shape
  const out = ctx.createImageData(nx, ny)
  const px = out.data
  const { data, flags } = img
  for (let row = 0; row < ny; row++) {
    const src = (ny - 1 - row) * nx
    for (let col = 0; col < nx; col++) {
      const v = data[src + col] ?? Number.NaN
      const o = (row * nx + col) * 4
      let r: number, g: number, b: number
      if (Number.isFinite(v)) {
        const i = Math.round(255 * stretchValue(v, stretch)) * 3
        r = lut[i] ?? 0
        g = lut[i + 1] ?? 0
        b = lut[i + 2] ?? 0
      } else {
        ;[r, g, b] = NAN_COLOR
      }
      if (overlayMask && flags && ((flags[src + col] ?? 0) & overlayMask) !== 0) {
        r = (r + overlayColor[0]) >> 1
        g = (g + overlayColor[1]) >> 1
        b = (b + overlayColor[2]) >> 1
      }
      px[o] = r
      px[o + 1] = g
      px[o + 2] = b
      px[o + 3] = 255
    }
  }
  ctx.putImageData(out, 0, 0)
}

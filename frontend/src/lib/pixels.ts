import type { PixelPos } from '../api/types'

/** Fractional position (0..1, from the top-left of the north-up display) of a pixel center. */
export interface DisplayFraction {
  left: number
  top: number
}

/** Data row 0 is south and the display is north up, so the row axis is flipped here and only here. */
export function pixelToDisplay(px: PixelPos, shape: readonly [number, number]): DisplayFraction {
  const [ny, nx] = shape
  return { left: (px.x + 0.5) / nx, top: (ny - 1 - px.y + 0.5) / ny }
}

/** Inverse of `pixelToDisplay`, snapped to the pixel under the point; null outside the frame. */
export function displayToPixel(f: DisplayFraction, shape: readonly [number, number]): PixelPos | null {
  const [ny, nx] = shape
  const x = Math.floor(f.left * nx)
  const row = Math.floor(f.top * ny)
  if (x < 0 || x >= nx || row < 0 || row >= ny) return null
  return { x, y: ny - 1 - row }
}

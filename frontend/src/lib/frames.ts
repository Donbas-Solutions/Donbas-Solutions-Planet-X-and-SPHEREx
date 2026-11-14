import type { FlagBit, FlagGroup, Frame, Sequence, Stretch } from '../api/types'

export interface LoadedFrame {
  frame: Frame
  data: Float32Array
  flags: Uint32Array | null
}

export async function loadSequence(manifestUrl: string, signal?: AbortSignal): Promise<{ seq: Sequence; base: URL }> {
  const base = new URL(manifestUrl, window.location.href)
  const res = await fetch(base, { signal })
  if (!res.ok) throw new Error(`Manifest ${base.pathname}: HTTP ${res.status}`)
  if (!res.headers.get('content-type')?.includes('json')) {
    throw new Error(`Manifest ${base.pathname}: not found (the server did not return JSON)`)
  }
  return { seq: (await res.json()) as Sequence, base }
}

async function fetchBinary(url: URL, expectedBytes: number, signal?: AbortSignal): Promise<ArrayBuffer> {
  const res = await fetch(url, { signal })
  if (!res.ok) throw new Error(`${url.pathname}: HTTP ${res.status}`)
  const buf = await res.arrayBuffer()
  if (buf.byteLength !== expectedBytes) {
    throw new Error(`${url.pathname}: ${buf.byteLength} bytes, expected ${expectedBytes}`)
  }
  return buf
}

/** Typed arrays use platform byte order; every browser platform we target is little-endian. */
export async function loadFrame(frame: Frame, base: URL, signal?: AbortSignal): Promise<LoadedFrame> {
  const [ny, nx] = frame.shape
  const bytes = ny * nx * 4
  const [data, flags] = await Promise.all([
    fetchBinary(new URL(frame.data, base), bytes, signal),
    frame.flags ? fetchBinary(new URL(frame.flags, base), bytes, signal) : Promise.resolve(null),
  ])
  return { frame, data: new Float32Array(data), flags: flags ? new Uint32Array(flags) : null }
}

/** Bitmask of all planes in the given groups. */
export function flagMask(bits: FlagBit[], groups: FlagGroup[]): number {
  let mask = 0
  for (const b of bits) if (groups.includes(b.group)) mask = (mask | (1 << b.bit)) >>> 0
  return mask
}

/** Map a value to 0..1 with the shared sequence stretch. */
export function stretchValue(v: number, s: Stretch): number {
  const t = Math.min(1, Math.max(0, (v - s.vmin) / (s.vmax - s.vmin)))
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
  nanColor?: [number, number, number]
  overlayColor?: [number, number, number]
}

/**
 * Draw a frame at 1 canvas pixel per data pixel (scale up with CSS + image-rendering: pixelated).
 * Data row 0 is south, canvas row 0 is top, so rows are flipped to get north up.
 */
export function renderFrame(ctx: CanvasRenderingContext2D, lf: LoadedFrame, s: Stretch, opts: RenderOptions = {}) {
  const [ny, nx] = lf.frame.shape
  const { overlayMask = 0, nanColor = [70, 0, 90], overlayColor = [255, 60, 60] } = opts
  const img = ctx.createImageData(nx, ny)
  const out = img.data
  for (let row = 0; row < ny; row++) {
    const src = (ny - 1 - row) * nx
    for (let col = 0; col < nx; col++) {
      const v = lf.data[src + col] ?? Number.NaN
      const o = (row * nx + col) * 4
      let r: number, g: number, b: number
      if (Number.isFinite(v)) {
        r = g = b = Math.round(255 * stretchValue(v, s))
      } else {
        ;[r, g, b] = nanColor
      }
      if (overlayMask && lf.flags && ((lf.flags[src + col] ?? 0) & overlayMask) !== 0) {
        r = (r + overlayColor[0]) >> 1
        g = (g + overlayColor[1]) >> 1
        b = (b + overlayColor[2]) >> 1
      }
      out[o] = r
      out[o + 1] = g
      out[o + 2] = b
      out[o + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
}

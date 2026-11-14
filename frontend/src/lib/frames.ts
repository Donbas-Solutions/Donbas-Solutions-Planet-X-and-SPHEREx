import type { FlagBit, FlagGroup, Frame, Sequence } from '../api/types'

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

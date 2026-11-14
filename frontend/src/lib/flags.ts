import type { FlagBit, FlagGroup } from '../api/types'
import type { Rgb } from './colormap'
import type { OverlayGroup } from './urlState'

/** Drawing order: the first group that matches a pixel wins its colour. */
export const OVERLAY_GROUPS: readonly OverlayGroup[] = ['saturation', 'bad', 'artifact']

export const GROUP_LABEL: Record<FlagGroup, string> = {
  saturation: 'Saturated / non-linear',
  bad: 'Bad data',
  artifact: 'Artifacts (ghosts, crosstalk, streaks)',
  info: 'Informational',
}

/** Chosen to stay apart from the grey and blue–orange maps and from the NaN colour. */
export const GROUP_COLOR: Record<OverlayGroup, Rgb> = {
  saturation: [255, 221, 0],
  bad: [235, 45, 45],
  artifact: [0, 190, 255],
}

/** Bitmask of all planes in the given groups. Flag arrays are uint32, so masks stay unsigned via `>>> 0`. */
export function flagMask(bits: readonly FlagBit[], groups: readonly FlagGroup[]): number {
  let mask = 0
  for (const b of bits) if (groups.includes(b.group)) mask = (mask | (1 << b.bit)) >>> 0
  return mask
}

export function bitsInGroup(bits: readonly FlagBit[], group: FlagGroup): FlagBit[] {
  return bits.filter((b) => b.group === group).sort((a, b) => a.bit - b.bit)
}

export function countFlagged(flags: Uint32Array | null, mask: number): number {
  if (!flags || mask === 0) return 0
  let n = 0
  for (const v of flags) if ((v & mask) !== 0) n++
  return n
}

/** Names of the bits set in one pixel's flag word, in bit order. */
export function flagNames(bits: readonly FlagBit[], value: number): FlagBit[] {
  return bits.filter((b) => ((value >>> b.bit) & 1) === 1).sort((a, b) => a.bit - b.bit)
}

export interface OverlayLayer {
  mask: number
  color: Rgb
}

export function overlayLayers(bits: readonly FlagBit[], groups: readonly OverlayGroup[]): OverlayLayer[] {
  return OVERLAY_GROUPS.filter((g) => groups.includes(g))
    .map((g) => ({ mask: flagMask(bits, [g]), color: GROUP_COLOR[g] }))
    .filter((l) => l.mask !== 0)
}

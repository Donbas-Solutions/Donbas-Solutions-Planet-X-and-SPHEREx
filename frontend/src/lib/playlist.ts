import type { Frame } from '../api/types'
import type { LoadedFrame } from './frames'
import type { DetectorChoice } from './urlState'

const ALL_DETECTORS = '1,2,3,4,5,6'
const BLINKABLE: readonly Frame['kind'][] = ['visit_stack', 'exposure']

export function detectorKey(detectors: readonly number[]): string {
  return [...detectors].sort((a, b) => a - b).join(',')
}

export function detectorLabel(key: string): string {
  return key === ALL_DETECTORS ? 'all detectors' : key.split(',').map((d) => `D${d}`).join('+')
}

/** Detectors of the playlist's set that this frame lacks, e.g. a visit with no D1 and D4 exposures. */
export function missingDetectors(detectors: readonly number[], playlistKey: string): number[] {
  return playlistKey
    .split(',')
    .map(Number)
    .filter((d) => !detectors.includes(d))
}

/**
 * A frame with several detectors is a combined stack. A visit with exposures from only one detector would make its
 * combined stack look like a single-detector one; the pipeline has not produced such a visit so far.
 */
function isCombined(frame: Frame): boolean {
  return frame.detectors.length > 1
}

export interface Playlist {
  frames: readonly LoadedFrame[]
  /** Detector set of the playlist; combined stacks of some visits may lack part of it. */
  key: string
  /** False when the requested detectors are not in this sequence and another set is shown instead. */
  isRequested: boolean
  availableKeys: readonly string[]
}

/**
 * Frames that may be blinked together: one detector set, in time order. Mixing detectors would show
 * λ differences as fake brightness changes (CLAUDE.md → Science rules). Combined stacks share one playlist keyed
 * by the union of their detectors (the requested set), so a visit lacking some detectors is kept with a warning
 * instead of being dropped.
 */
export function buildPlaylist(all: readonly LoadedFrame[], det: DetectorChoice): Playlist {
  const blinkable = all.filter((f) => BLINKABLE.includes(f.frame.kind))
  const combined = blinkable.filter((f) => isCombined(f.frame))
  const combinedKey =
    combined.length > 0 ? detectorKey([...new Set(combined.flatMap((f) => f.frame.detectors))]) : null
  const keyOf = (frame: Frame) => (isCombined(frame) && combinedKey ? combinedKey : detectorKey(frame.detectors))

  const availableKeys = [...new Set(blinkable.map((f) => keyOf(f.frame)))]
  const wanted = det === 'all' ? (combinedKey ?? ALL_DETECTORS) : detectorKey(det)
  const isRequested = availableKeys.includes(wanted)
  const key = isRequested ? wanted : (combinedKey ?? availableKeys[0] ?? wanted)
  const frames = blinkable
    .filter((f) => keyOf(f.frame) === key)
    .sort((a, b) => a.frame.mjd_mid - b.frame.mjd_mid)
  return { frames, key, isRequested, availableKeys }
}
